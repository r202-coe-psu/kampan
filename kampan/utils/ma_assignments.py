"""อีเมลแจ้งการมอบหมายผู้รับผิดชอบ MA: ผู้รับผิดชอบที่ถูกเพิ่มใหม่ในรายการย่อยได้อีเมล 1 ฉบับ

- ใช้ ReminderLog kind ``assigned`` (dedupe_key = รายการย่อย + สมาชิก) กันส่งซ้ำ และเป็นประวัติที่หน้ารายละเอียด
- ส่งผ่านคิว RQ เดียวกับอีเมลเตือน (``ma_send_emails.send_reminder_job``) ไม่ส่งตรงจาก request
- แบบร่างไม่ส่ง: ส่งเมื่อบันทึกเป็น MA จริงครั้งแรก (หรือเมื่อเผยแพร่แบบร่าง) เพราะ snapshot ของแบบร่างเป็นค่าว่าง
  ทุกคนในรายการจึงนับเป็น "เพิ่มใหม่"
"""

import datetime
import logging

import mongoengine as me

from kampan import models
from kampan.utils import ma_send_emails
from kampan.utils.reminders import STOPPED_STATUSES

logger = logging.getLogger(__name__)

JOB_TIMEOUT = 600


def snapshot_responsibles(procurement) -> dict:
    """ผู้รับผิดชอบของแต่ละรายการย่อยก่อนแก้ ``{item_id: {member_id}}`` (MA ใหม่และแบบร่างคืนค่าว่าง)

    เรียกก่อนแก้ไขอะไรใน procurement เพราะฟอร์มแก้ object ของรายการย่อยที่โหลดไว้โดยตรง
    """
    if procurement.pk is None or procurement.status == "draft":
        return {}
    return {item.pk: set(item.get_responsible_ids()) for item in procurement.get_items()}


def enqueue_email_job(log, settings) -> None:
    """ใส่งานส่งอีเมลของ log เข้าคิว (เทสต์ patch ฟังก์ชันนี้ ไม่ส่งจริง)"""
    from kampan.web import redis_rq

    redis_rq.redis_queue.queue.enqueue(
        ma_send_emails.send_reminder_job,
        args=(str(log.id), dict(settings)),
        job_timeout=JOB_TIMEOUT,
    )


def _recipient(member) -> list[str]:
    if not isinstance(member, models.OrganizationUserRole) or member.status == "disactive":
        return []
    email = (member.user.email if member.user else None) or member.email
    return [email] if email else []


def notify_new_assignments(procurement, items, before: dict, assigned_by, settings) -> list:
    """สร้าง log + ใส่คิวอีเมลให้ผู้รับผิดชอบที่เพิ่งถูกเพิ่มในแต่ละรายการ (ไม่อยู่ใน ``before`` ของรายการนั้น)

    แบบร่างไม่ส่ง · ไม่เคยทำให้การบันทึกล้ม: เข้าคิวไม่สำเร็จ log เป็น failed และไม่ retry เอง
    """
    if procurement.status in STOPPED_STATUSES:
        # แบบร่าง / ไม่ต่ออายุ / ต่ออายุแล้ว ไม่ส่งอีเมลมอบหมาย
        return []
    logs = []
    now = datetime.datetime.now()
    for item in items:
        previous = before.get(item.pk, set())
        for member in item.responsible_by or []:
            member_id = getattr(member, "id", None)
            if member_id is None or member_id in previous:
                continue
            log = models.ReminderLog(
                organization=procurement.organization,
                procurement=procurement,
                item=item,
                kind="assigned",
                trigger_date=datetime.datetime.combine(now.date(), datetime.time.min),
                offset="assigned",
                recipients=_recipient(member),
                status="queued",
                dedupe_key=f"{item.pk}:assigned:{member_id}",
                created_by=assigned_by,
                created_date=now,
            )
            try:
                log.save(force_insert=True)
            except me.NotUniqueError:
                logger.info("assignment email %s already logged, skip", log.dedupe_key)
                continue
            logs.append(log)
            try:
                enqueue_email_job(log, settings)
            except Exception:
                logger.exception("enqueue assignment email %s failed", log.dedupe_key)
                models.ReminderLog.objects(id=log.id, status="queued").update_one(
                    set__status="failed", set__error="เข้าคิวส่งอีเมลไม่สำเร็จ"
                )
    return logs
