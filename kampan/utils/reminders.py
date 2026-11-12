"""ระบบเตือน MA (#28, #29): วันนี้มี reminder อะไรที่ถึงกำหนดแล้วและยังไม่เคยส่ง

อ่าน Mongo อย่างเดียว ไม่แตะ Redis/SMTP controller เป็นคนสร้าง ReminderLog แล้ว enqueue งานส่งอีเมล
"""

import dataclasses
import datetime

from dateutil.relativedelta import relativedelta

from kampan import models
from kampan.models.procurement import parent_procurement_ids
from kampan.models.reminder_logs import SYSTEM_LOG_STATUSES

# ช่วงเตือน key → ระยะก่อนถึงกำหนด ("due" = วันครบกำหนดเอง)
OFFSET_DELTAS = {
    "6m": relativedelta(months=6),
    "5m": relativedelta(months=5),
    "4m": relativedelta(months=4),
    "3m": relativedelta(months=3),
    "2m": relativedelta(months=2),
    "1m": relativedelta(months=1),
    "15d": relativedelta(days=15),
    "7d": relativedelta(days=7),
}
DUE_OFFSET = "due"
# MA ที่หยุดเตือนทั้งหมด: ไม่ต่ออายุ / ต่ออายุแล้ว
STOPPED_STATUSES = ["disactive", "renewed"]
# trigger ที่เลยมาเกินกี่วันจะไม่ส่งแล้ว ใช้กับทุก kind (กันนำเข้า MA ที่มีงวดค้างย้อนหลัง,
# กรอกวันในอดีต หรือ controller ล่มนานแล้วยิงเมลย้อนหลัง)
REMINDER_GRACE_DAYS = 7


@dataclasses.dataclass
class Reminder:
    item: models.ProcurementItem
    kind: str
    trigger_date: datetime.date
    offset: str
    recipients: list[str]
    installment_id: object = None
    installment_index: int | None = None

    @property
    def dedupe_key(self) -> str:
        """กันสร้าง log ซ้ำ (controller รันซ้ำวันเดียวกัน / 2 process พร้อมกัน)"""
        installment = self.installment_id if self.installment_id is not None else "-"
        return f"{self.item.id}:{self.kind}:{installment}:{self.trigger_date.isoformat()}"


def _as_date(value) -> datetime.date | None:
    if isinstance(value, datetime.datetime):
        return value.date()
    return value


def _offset_triggers(target: datetime.date, offsets, extra_days=()) -> list[tuple[datetime.date, str]]:
    """วัน trigger ของทุกช่วงที่ติ๊ก + จำนวนวันที่กรอกเอง + วันครบกำหนดเอง (1 ครั้ง)"""
    triggers = [(target - OFFSET_DELTAS[key], key) for key in offsets or [] if key in OFFSET_DELTAS]
    triggers += [(target - datetime.timedelta(days=days), str(days)) for days in extra_days or [] if days]
    triggers.append((target, DUE_OFFSET))
    return triggers


def _oldest_sendable(today: datetime.date) -> datetime.date:
    return today - datetime.timedelta(days=REMINDER_GRACE_DAYS)


def _latest_due(triggers, today):
    """trigger ล่าสุดที่ถึงกำหนดแล้ว ถ้าเก่ากว่า today − 7 วันถือว่าเลยรอบไปแล้ว ไม่ส่ง"""
    due = [trigger for trigger in triggers if trigger[0] <= today]
    if not due:
        return None
    latest = max(due, key=lambda trigger: trigger[0])
    if latest[0] < _oldest_sendable(today):
        return None
    return latest


def _recipients(item) -> list[str]:
    """อีเมลของผู้รับผิดชอบรายการย่อยนี้ (ไม่รวมสมาชิกที่ถูกนำออก) ไม่ซ้ำ"""
    emails = []
    for member in item.responsible_by or []:
        # สมาชิกที่ถูกลบไปแล้ว (DBRef ค้าง) หรือถูกนำออกจากหน่วยงานแล้วไม่ได้รับ (pending ยังได้รับทาง member.email)
        if not isinstance(member, models.OrganizationUserRole) or member.status == "disactive":
            continue
        email = (member.user.email if member.user else None) or member.email
        if email and email not in emails:
            emails.append(email)
    return emails


def _midnight(value: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(value, datetime.time.min)


def _already_logged(item, kind: str, trigger_date: datetime.date, installment_id=None, exact=False) -> bool:
    """มี log ของระบบ (queued / sent / failed) ของ item + kind นี้แล้วหรือยัง

    ปกติดู log ที่ trigger_date >= trigger นี้ (collapse: ส่งรอบหลังไปแล้วก็ไม่ส่งรอบก่อนย้อนหลัง)
    ``exact`` ใช้กับวันที่เจาะจง ซึ่งแต่ละวันเป็นคนละ milestone
    """
    date_filter = {"trigger_date": _midnight(trigger_date)} if exact else {"trigger_date__gte": _midnight(trigger_date)}
    logs = models.ReminderLog.objects(
        organization=item._data.get("organization"),
        item=item,
        kind=kind,
        status__in=SYSTEM_LOG_STATUSES,
        **date_filter,
    )
    if installment_id is not None:
        logs = logs.filter(installment_id=installment_id)
    return logs.count() > 0


def _item_candidates(item, today: datetime.date) -> list[dict]:
    """reminder ที่ถึงกำหนดของรายการย่อยนี้ ก่อนตัดตัวที่มี log แล้ว (กลุ่มละ 1 ตัว ยกเว้นวันที่เจาะจง)"""
    candidates = []
    end_date = _as_date(item.end_date)

    if end_date:
        latest = _latest_due(_offset_triggers(end_date, item.expiry_reminder_offsets, item.reminder_offsets_days), today)
        if latest:
            candidates.append({"kind": "expiry", "trigger": latest})
        if item.requires_activation and _oldest_sendable(today) <= end_date <= today:
            candidates.append({"kind": "activation", "trigger": (end_date, DUE_OFFSET)})

    for index, installment in enumerate(item.get_sorted_installments(), start=1):
        due_date = _as_date(installment.due_date)
        if installment.is_paid() or not due_date:
            continue
        latest = _latest_due(_offset_triggers(due_date, item.payment_reminder_offsets), today)
        if latest:
            candidates.append(
                {"kind": "payment", "trigger": latest, "installment_id": installment._id, "installment_index": index}
            )

    for value in sorted({_as_date(value) for value in item.custom_reminder_dates or [] if value}):
        if _oldest_sendable(today) <= value <= today:
            candidates.append({"kind": "custom", "trigger": (value, "date"), "exact": True})
    return candidates


def due_reminders(today: datetime.date) -> list[Reminder]:
    """reminder ทุกตัวที่ถึงกำหนดแล้ว (trigger <= today) และยังไม่มี log ของระบบ

    - expiry: ทุกช่วงที่ติ๊ก + จำนวนวันที่กรอกเอง ก่อน end_date และ 1 ครั้งในวัน end_date
    - payment: ต่องวดที่ยังไม่จ่าย ทุกช่วงที่ติ๊กก่อน due_date และ 1 ครั้งในวัน due_date
    - activation: 1 ครั้งในวัน end_date ถ้า requires_activation
    - custom: ในวันที่เจาะจง
    - ทุก kind: ข้าม trigger ที่เก่ากว่า today − 7 วัน (REMINDER_GRACE_DAYS) เช่น MA นำเข้าที่มีงวดค้างย้อนหลัง
    - collapse: ต่อ (รายการย่อย, kind[, งวด]) คืนเฉพาะ trigger ล่าสุดที่ถึงกำหนด ถ้ามี log ที่ trigger_date >= ตัวนั้นแล้วข้าม
      (controller ล่มหลายวันแล้วไม่ยิงเมลค้างหลายฉบับ และไม่มีการเตือนซ้ำหลังเลยกำหนด)
    - MA ที่ไม่ต่ออายุ / ต่ออายุแล้ว ไม่เตือนเลย
    - สัญญาหลักที่มีสัญญาย่อย ไม่เตือนเอง (เตือนจากสัญญาย่อยแทน กันได้เมลซ้ำ)
    """
    stopped_ids = list(models.Procurement.objects(status__in=STOPPED_STATUSES).scalar("id"))
    # สัญญาหลักที่แยกสัญญาย่อยแล้ว: เตือนจากสัญญาย่อยเท่านั้น (รายการย่อยของสัญญาย่อยเป็นสำเนาของสัญญาหลัก)
    parent_ids = parent_procurement_ids()
    reminders = []
    for item in models.ProcurementItem.objects(procurement__nin=stopped_ids + parent_ids):
        recipients = None
        for candidate in _item_candidates(item, today):
            trigger_date, offset = candidate["trigger"]
            installment_id = candidate.get("installment_id")
            if _already_logged(item, candidate["kind"], trigger_date, installment_id, candidate.get("exact", False)):
                continue
            if recipients is None:
                recipients = _recipients(item)
            reminders.append(
                Reminder(
                    item=item,
                    kind=candidate["kind"],
                    trigger_date=trigger_date,
                    offset=offset,
                    recipients=list(recipients),
                    installment_id=installment_id,
                    installment_index=candidate.get("installment_index"),
                )
            )
    return reminders
