"""รอบเตือน MA ประจำวันของ controller (#28)

เรียก ``due_reminders`` แล้วต่อ reminder หนึ่งตัว: สร้าง ReminderLog ``queued`` ก่อน (dedupe_key กันซ้ำ)
แล้ว enqueue ``send_reminder_job`` ส่งแค่ id ของ log ไปให้ worker
"""

import datetime
import logging

import mongoengine as me

from kampan import models
from kampan.utils import ma_send_emails
from kampan.utils.reminders import Reminder, due_reminders

logger = logging.getLogger(__name__)

JOB_TIMEOUT = 600
ENQUEUE_ERROR = "เข้าคิวส่งอีเมลไม่สำเร็จ"


def _create_log(reminder: Reminder, today: datetime.date) -> models.ReminderLog | None:
    """log queued ของ reminder นี้ ถ้ามี log key เดียวกันอยู่แล้ว (รันซ้ำ / รันพร้อมกัน) คืน None

    created_date เป็นวันของรอบเตือนนี้ (ปกติคือวันนี้) อีเมลใช้นับจำนวนวันที่เหลือจริงถึงวันครบกำหนด
    """
    item = reminder.item
    log = models.ReminderLog(
        organization=item.organization,
        procurement=item.procurement,
        item=item,
        kind=reminder.kind,
        trigger_date=datetime.datetime.combine(reminder.trigger_date, datetime.time.min),
        offset=reminder.offset,
        installment_id=reminder.installment_id,
        installment_index=reminder.installment_index,
        recipients=reminder.recipients,
        status="queued",
        dedupe_key=reminder.dedupe_key,
        created_date=datetime.datetime.combine(today, datetime.datetime.now().time()),
    )
    try:
        return log.save(force_insert=True)
    except me.NotUniqueError:
        logger.info("reminder %s already logged, skip", reminder.dedupe_key)
        return None


def enqueue_due_reminders(today: datetime.date, settings, queue) -> list[models.ReminderLog]:
    """สร้าง log + enqueue งานส่งเมลของทุก reminder ที่ถึงกำหนดวันนี้ คืน log ที่สร้าง

    enqueue ไม่สำเร็จ (เช่น Redis ล่ม): log เป็น failed พร้อมสาเหตุ ไม่ค้าง queued และไม่ retry เอง
    """
    logs = []
    for reminder in due_reminders(today):
        log = _create_log(reminder, today)
        if not log:
            continue
        logs.append(log)
        try:
            job = queue.enqueue(
                ma_send_emails.send_reminder_job,
                args=(str(log.id), dict(settings)),
                job_timeout=JOB_TIMEOUT,
            )
            logger.info("enqueued reminder %s as job %s", log.dedupe_key, getattr(job, "id", None))
        except Exception:
            # รายละเอียดของ exception (อาจมี host ของ Redis) อยู่ใน log ของ controller เท่านั้น
            # ไม่เก็บใน ReminderLog ที่แสดงบนหน้าเว็บ
            logger.exception("enqueue reminder %s failed", log.dedupe_key)
            models.ReminderLog.objects(id=log.id, status="queued").update_one(
                set__status="failed",
                set__error=ENQUEUE_ERROR,
            )
    return logs
