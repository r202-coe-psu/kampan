"""อีเมลแจ้งเตือน MA (#28): 1 reminder = อีเมล 1 ฉบับ ส่งให้ผู้รับผิดชอบรายการย่อยทีละคน

รันใน worker (``send_reminder_job``) ผลการส่งเขียนลง ReminderLog เสมอ (sent / failed) ไม่ค้าง queued
"""

import datetime
import logging

from kampan import models
from . import ma_email_templates
from .date_utils import format_date_th
from .email_utils import PSUSMTP, get_host_url

logger = logging.getLogger(__name__)

# ข้อความใน ReminderLog.error แสดงบนหน้าเว็บ จึงเก็บแค่ประเภทสาเหตุ รายละเอียดของ exception อยู่ใน log ของ worker
NO_RECIPIENT_ERROR = "ไม่มีผู้รับ"
SMTP_LOGIN_ERROR = "เข้าสู่ระบบ SMTP ไม่สำเร็จ"
SEND_ERROR = "ส่งอีเมลไม่สำเร็จ"

# คำเรียกรายการย่อยตาม reminder_kind
REMINDER_KIND_NOUNS = {
    "ma": "MA",
    "license": "License",
    "rental": "สัญญาเช่า-จ้างเหมา",
}
OFFSET_LABELS = {
    "6m": "180 วัน",
    "5m": "150 วัน",
    "4m": "120 วัน",
    "3m": "90 วัน",
    "2m": "60 วัน",
    "1m": "30 วัน",
    "15d": "15 วัน",
    "7d": "7 วัน",
    "5d": "5 วัน",
    "3d": "3 วัน",
}

def _as_date(value):
    return value.date() if isinstance(value, datetime.datetime) else value


def _installment_due_date(log, item):
    for installment in item.installments:
        if installment._id == log.installment_id:
            return _as_date(installment.due_date)
    return _as_date(log.trigger_date)


def _send_date(log) -> datetime.date:
    """วันที่ส่ง reminder นี้ (วันของรอบเตือนที่สร้าง log) ใช้นับจำนวนวันที่เหลือจริง ไม่ใช่วัน trigger"""
    return _as_date(log.created_date) or datetime.date.today()


def _target_date(log, item):
    """วันครบกำหนดจริงที่ reminder นี้เตือน: end_date (หมดอายุ / activate) หรือ due_date ของงวด"""
    if log.kind == "payment":
        return _installment_due_date(log, item)
    return _as_date(item.end_date)


def reminder_title(log, item) -> str:
    """ประเภทการเตือนที่ใช้ใน subject จำนวนวันนับจากวันที่ส่งถึงวันครบกำหนดจริง

    ใช้ชื่อช่วงเตือน (เช่น "3 เดือน") เฉพาะตอนส่งตรงวัน trigger
    ถ้าส่งช้า (MA สร้างทีหลัง / controller ล่ม) ใช้จำนวนวันจริง
    เช่น "หมดอายุใน 3 เดือน", "หมดอายุใน 10 วัน", "ครบกำหนดหมดอายุวันนี้", "เลยกำหนดจ่ายงวดที่ 2 มาแล้ว 3 วัน"
    """
    if log.kind == "custom":
        return "เตือนตามวันที่กำหนด"

    sent = _send_date(log)
    target = _target_date(log, item)
    days = (target - sent).days if target else 0
    on_time = sent == _as_date(log.trigger_date) and log.offset in OFFSET_LABELS
    ahead = OFFSET_LABELS[log.offset] if on_time else f"{days} วัน"

    if log.kind == "payment":
        installment = f"งวดที่ {log.installment_index}" if log.installment_index else "งวด"
        if days > 0:
            return f"จ่าย{installment} ใน {ahead}"
        if days == 0:
            return f"ครบกำหนดจ่าย{installment} วันนี้"
        return f"เลยกำหนดจ่าย{installment} มาแล้ว {-days} วัน"
    if log.kind == "activation":
        return "ครบกำหนด activate วันนี้" if days >= 0 else f"เลยกำหนด activate มาแล้ว {-days} วัน"
    if days > 0:
        return f"หมดอายุใน {ahead}"
    if days == 0:
        return "ครบกำหนดหมดอายุวันนี้"
    return f"เลยกำหนดหมดอายุมาแล้ว {-days} วัน"


def _days_text(target: datetime.date, from_date: datetime.date) -> str:
    days = (target - from_date).days
    if days > 0:
        return f"(อีก {days} วัน)"
    if days == 0:
        return "(วันนี้)"
    return f"(เลยมาแล้ว {-days} วัน)"


def _reminder_message(log, item, noun: str) -> str:
    sent = _send_date(log)
    end_date = _as_date(item.end_date)
    end_text = f"{format_date_th(end_date)} {_days_text(end_date, sent)}"
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
            f"{installment} ครบกำหนดจ่ายวันที่ {format_date_th(due_date)} {_days_text(due_date, sent)}\n"
            "กรุณาดำเนินการเบิกจ่าย และบันทึกการจ่ายในระบบเมื่อจ่ายแล้ว"
        )
    if log.kind == "activation":
        return f"{noun} รายการนี้ครบกำหนดในวันที่ {end_text}\nกรุณา activate ให้เรียบร้อย"
    trigger = _as_date(log.trigger_date)
    return f"แจ้งเตือนตามวันที่ที่ตั้งไว้ ({format_date_th(trigger)})\n{noun} รายการนี้{ending}วันที่ {end_text}"


def _detail_procurement(procurement, item):
    """MA ที่เปิดดูรายการนี้: สัญญาหลักเป็นข้อมูลอ้างอิง ลิงก์ไปสัญญาย่อยที่เป็นสำเนาของรายการแทน"""
    for child in procurement._matching_children(item):
        return child
    return procurement


def _common_context(log, item, procurement, detail_procurement) -> dict:
    organization = log.organization
    return {
        "organization_name": organization.name if organization else "",
        "ma_name": procurement.name,
        "psu_number": procurement.psu_disbursement_number or "-",
        "company": procurement.company or "-",
        "item_name": item.name,
        "noun": REMINDER_KIND_NOUNS.get(item.reminder_kind, "MA"),
        "start_date": format_date_th(_as_date(item.start_date)),
        "end_date": format_date_th(_as_date(item.end_date)),
        "detail_url": "",
    }


def _detail_url(log, settings, target, item) -> str:
    return (
        f"{get_host_url(settings)}/procurement/payment/{target.id}"
        f"?organization_id={log._data['organization'].id}#item-{item.id}"
    )


def build_email_context(log, settings) -> dict:
    """ตัวแปรที่ใช้ใน template อีเมล MA (ต้องตรงกับ EMAIL_TEMPLATE_VARIABLES ของชนิด ma_*)"""
    item = log.item
    procurement = log.procurement
    context = _common_context(log, item, procurement, procurement)
    if log.kind == "assigned":
        context["assigner_name"] = log.created_by.get_resources_fullname_th() if log.created_by else "เจ้าหน้าที่"
        context["detail_url"] = _detail_url(log, settings, _detail_procurement(procurement, item), item)
        return context

    context["detail_url"] = _detail_url(log, settings, procurement, item)
    target = _target_date(log, item)
    context.update(
        reminder_title=reminder_title(log, item),
        reminder_message=_reminder_message(log, item, context["noun"]),
        target_date=format_date_th(target) if target else "",
        days_text=_days_text(target, _send_date(log)) if target else "",
    )
    if log.kind == "payment":
        context["installment_index"] = log.installment_index or ""
        context["due_date"] = context["target_date"]
    return context


def build_reminder_email(log, settings) -> tuple[str, str]:
    """(subject, body) ของ log นี้ จาก template ขององค์กรเท่านั้น
    raise MaEmailTemplateError เมื่อองค์กรไม่มี template เริ่มต้นของชนิดนี้ หรือ template ไม่ถูกต้อง"""
    organization = log.organization
    template = ma_email_templates.get_template(organization, ma_email_templates.email_type_for(log.kind))
    return ma_email_templates.render(template, build_email_context(log, settings))


def _deliver(log, settings) -> tuple[str, str | None]:
    """ส่งอีเมลของ log นี้ คืน (status, error)"""
    recipients = list(log.recipients or [])
    if not recipients:
        return "failed", NO_RECIPIENT_ERROR

    try:
        subject, body = build_reminder_email(log, settings)
    except ma_email_templates.MaEmailTemplateError as error:
        return "failed", str(error)
    psu_smtp = PSUSMTP(settings)
    try:
        if not psu_smtp.login():
            return "failed", SMTP_LOGIN_ERROR
        failed = [receiver for receiver in recipients if not psu_smtp.send_email(receiver, subject, body, html=True)]
    finally:
        try:
            psu_smtp.quit()
        except Exception:
            logger.warning("SMTP quit failed for reminder %s", log.id)

    if failed:
        return "failed", "ส่งไม่ถึง: " + ", ".join(failed)
    return "sent", None


STOPPED_SKIP_NOTE = "MA ไม่ต่ออายุ / ต่ออายุแล้ว / เป็นแบบร่าง จึงไม่ส่งอีเมล"


def _is_stopped(log) -> bool:
    """MA ของ log นี้หยุดเตือนแล้วตอนส่ง (ไม่ต่ออายุ / ต่ออายุแล้ว / แบบร่าง หรือหาไม่พบ) log ที่ค้างคิวไว้ก่อนหน้าจึงไม่ถูกส่ง"""
    from .reminders import STOPPED_STATUSES

    procurement = models.Procurement.objects(id=log._data["procurement"].id).only("status").first()
    return procurement is None or procurement.status in STOPPED_STATUSES


def send_reminder_job(log_id: str, settings) -> bool:
    """งานใน worker: ส่งอีเมลของ ReminderLog ที่ยัง queued แล้วเขียนสถานะสุดท้ายใน finally (failed ไม่ retry เอง)

    ตรวจสถานะ MA ตอนส่งอีกครั้ง: ถ้าหยุดเตือนแล้ว (เช่นอนุมัติไม่ต่ออายุหลังเข้าคิว) ไม่ส่ง และตั้ง log เป็น skipped
    """
    log = models.ReminderLog.objects(id=log_id, status="queued").first()
    if not log:
        logger.info("reminder log %s is not queued, skip", log_id)
        return False
    if _is_stopped(log):
        models.ReminderLog.objects(id=log.id, status="queued").update_one(
            set__status="skipped", set__error=STOPPED_SKIP_NOTE
        )
        logger.info("reminder log %s skipped: procurement stopped", log_id)
        return False

    status, error = "failed", None
    try:
        status, error = _deliver(log, settings)
    except Exception:
        logger.exception("send_reminder_job %s failed", log_id)
        status, error = "failed", SEND_ERROR
    finally:
        updates = {"set__status": status}
        if error:
            updates["set__error"] = error
        if status == "sent":
            updates["set__sent_date"] = datetime.datetime.now()
        models.ReminderLog.objects(id=log.id, status="queued").update_one(**updates)
    return status == "sent"
