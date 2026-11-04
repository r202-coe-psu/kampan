"""อีเมลแจ้งเตือน MA (#28): 1 reminder = อีเมล 1 ฉบับ ส่งให้ผู้รับผิดชอบรายการย่อยทีละคน

รันใน worker (``send_reminder_job``) ผลการส่งเขียนลง ReminderLog เสมอ (sent / failed) ไม่ค้าง queued
"""

import datetime
import logging

from kampan import models
from .date_utils import format_date_th
from .email_utils import PSUSMTP, get_host_url

logger = logging.getLogger(__name__)

NO_RECIPIENT_ERROR = "ไม่มีผู้รับ"
SMTP_LOGIN_ERROR = "เข้าสู่ระบบ SMTP ไม่สำเร็จ"

# คำเรียกรายการย่อยตาม reminder_kind
REMINDER_KIND_NOUNS = {
    "ma": "MA",
    "license": "License",
    "rental": "สัญญาเช่า-จ้างเหมา",
}
OFFSET_LABELS = {
    "6m": "6 เดือน",
    "5m": "5 เดือน",
    "4m": "4 เดือน",
    "3m": "3 เดือน",
    "2m": "2 เดือน",
    "1m": "1 เดือน",
    "15d": "15 วัน",
    "7d": "7 วัน",
}
DUE_OFFSET = "due"

EMAIL_FOOTER = """
ดูรายละเอียด: {ma_url}

ด้วยความเคารพ
งานพัสดุ
อีเมลติดต่อ patsadu_diis@psu.ac.th
"""


def _as_date(value):
    return value.date() if isinstance(value, datetime.datetime) else value


def _offset_label(offset: str) -> str:
    if offset in OFFSET_LABELS:
        return OFFSET_LABELS[offset]
    return f"{offset} วัน"


def _installment_due_date(log, item):
    for installment in item.installments:
        if installment._id == log.installment_id:
            return _as_date(installment.due_date)
    return _as_date(log.trigger_date)


def reminder_title(log) -> str:
    """ประเภทการเตือนที่ใช้ใน subject เช่น "หมดอายุใน 3 เดือน", "ครบกำหนดจ่ายงวดที่ 2" """
    if log.kind == "expiry":
        return "ครบกำหนดหมดอายุ" if log.offset == DUE_OFFSET else f"หมดอายุใน {_offset_label(log.offset)}"
    if log.kind == "payment":
        installment = f"งวดที่ {log.installment_index}" if log.installment_index else "งวด"
        if log.offset == DUE_OFFSET:
            return f"ครบกำหนดจ่าย{installment}"
        return f"จ่าย{installment} ใน {_offset_label(log.offset)}"
    if log.kind == "activation":
        return "ครบกำหนด activate"
    return "เตือนตามวันที่กำหนด"


def _days_text(target: datetime.date, from_date: datetime.date) -> str:
    days = (target - from_date).days
    if days > 0:
        return f"(อีก {days} วัน)"
    if days == 0:
        return "(วันนี้)"
    return f"(เลยมาแล้ว {-days} วัน)"


def _reminder_message(log, item, noun: str) -> str:
    trigger = _as_date(log.trigger_date)
    end_date = _as_date(item.end_date)
    end_text = f"{format_date_th(end_date)} {_days_text(end_date, trigger)}"
    ending = "สิ้นสุดสัญญา" if item.reminder_kind == "rental" else "หมดอายุ"

    if log.kind == "expiry":
        return (
            f"{noun} รายการนี้จะ{ending}ในวันที่ {end_text}\n"
            "กรุณาวางแผนการจัดซื้อจัดจ้างใหม่หรือต่ออายุ และส่งเอกสารมายังงานพัสดุโดยเร็ว"
        )
    if log.kind == "payment":
        due_date = _installment_due_date(log, item)
        installment = f"งวดที่ {log.installment_index}" if log.installment_index else "งวด"
        return (
            f"{installment} ครบกำหนดจ่ายวันที่ {format_date_th(due_date)} {_days_text(due_date, trigger)}\n"
            "กรุณาดำเนินการเบิกจ่าย และบันทึกการจ่ายในระบบเมื่อจ่ายแล้ว"
        )
    if log.kind == "activation":
        return f"{noun} รายการนี้ครบกำหนดในวันที่ {end_text}\nกรุณา activate ให้เรียบร้อย"
    return f"แจ้งเตือนตามวันที่ที่ตั้งไว้ ({format_date_th(trigger)})\n{noun} รายการนี้{ending}วันที่ {end_text}"


def build_reminder_email(log, settings) -> tuple[str, str]:
    """(subject, body) ของ reminder นี้"""
    item = log.item
    procurement = log.procurement
    noun = REMINDER_KIND_NOUNS.get(item.reminder_kind, "MA")
    psu_number = procurement.psu_disbursement_number or "-"
    subject = f"[แจ้งเตือน] {reminder_title(log)} {item.name} (ม.อ.เบิกจ่าย {psu_number})"

    ma_url = (
        f"{get_host_url(settings)}/procurement/payment/{procurement.id}"
        f"?organization_id={log._data['organization'].id}#item-{item.id}"
    )
    body = (
        "เรียน ผู้รับผิดชอบ\n\n"
        f"{noun}: {item.name}\n"
        f"สัญญา MA: {procurement.name} (เลขที่ ม.อ.เบิกจ่าย {psu_number})\n"
        f"บริษัท: {procurement.company or '-'}\n"
        f"ช่วงสัญญา: {format_date_th(_as_date(item.start_date))} – {format_date_th(_as_date(item.end_date))}\n\n"
        f"{_reminder_message(log, item, noun)}\n" + EMAIL_FOOTER.format(ma_url=ma_url)
    )
    return subject, body


def _deliver(log, settings) -> tuple[str, str | None]:
    """ส่งอีเมลของ log นี้ คืน (status, error)"""
    recipients = list(log.recipients or [])
    if not recipients:
        return "failed", NO_RECIPIENT_ERROR

    subject, body = build_reminder_email(log, settings)
    psu_smtp = PSUSMTP(settings)
    try:
        if not psu_smtp.login():
            return "failed", SMTP_LOGIN_ERROR
        failed = [receiver for receiver in recipients if not psu_smtp.send_email(receiver, subject, body)]
    finally:
        try:
            psu_smtp.quit()
        except Exception:
            logger.warning("SMTP quit failed for reminder %s", log.id)

    if failed:
        return "failed", "ส่งไม่ถึง: " + ", ".join(failed)
    return "sent", None


def send_reminder_job(log_id: str, settings) -> bool:
    """งานใน worker: ส่งอีเมลของ ReminderLog ที่ยัง queued แล้วเขียนสถานะสุดท้ายใน finally (failed ไม่ retry เอง)"""
    log = models.ReminderLog.objects(id=log_id, status="queued").first()
    if not log:
        logger.info("reminder log %s is not queued, skip", log_id)
        return False

    status, error = "failed", None
    try:
        status, error = _deliver(log, settings)
    except Exception as exception:
        logger.exception("send_reminder_job %s failed", log_id)
        status, error = "failed", f"เกิดข้อผิดพลาด: {exception}"
    finally:
        updates = {"set__status": status}
        if error:
            updates["set__error"] = error
        if status == "sent":
            updates["set__sent_date"] = datetime.datetime.now()
        models.ReminderLog.objects(id=log.id, status="queued").update_one(**updates)
    return status == "sent"
