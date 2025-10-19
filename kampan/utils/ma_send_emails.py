from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = {
    "90d": "[แจ้งเตือน] เหลือ 3 เดือนครบกำหนดชำระเงินสำหรับ {{ name }}",
    "30d": "[แจ้งเตือน] เหลือ 1 เดือนครบกำหนดชำระเงินสำหรับ {{ name }}",
    "expired": "[แจ้งเตือน] เลยกำหนดชำระเงินสำหรับ {{ name }}",
    "default": "[แจ้งเตือน] การชำระเงินสำหรับ {{ name }}",
}

# Email body template
email_body_template = """
เรียน {{ responsible_name }},

ระบบขอแจ้งเตือนสถานะการชำระเงินสำหรับรายการจัดซื้อ/จ้าง:

- ชื่อรายการ: {{ name }}
- หมายเลขครุภัณฑ์: {{ product_number or '-' }}
- หมายเลขสินทรัพย์: {{ asset_code or '-' }}
- หมวดหมู่: {{ category or '-' }}
- บริษัท: {{ company or '-' }}
- จำนวนเงิน: {{ amount or '-' }}

{% if notif_type == "90d" %}
เหลือเวลาอีก 3 เดือน ({{ days_left }} วัน) จะถึงกำหนดชำระเงิน
{% elif notif_type == "30d" %}
เหลือเวลาอีก 1 เดือน ({{ days_left }} วัน) จะถึงกำหนดชำระเงิน
{% elif notif_type == "expired" %}
เลยกำหนดชำระเงินแล้ว
{% else %}
โปรดตรวจสอบสถานะการชำระเงิน
{% endif %}

หากมีข้อสงสัย กรุณาติดต่อเจ้าหน้าที่ที่รับผิดชอบ

ขอแสดงความนับถือ,
ระบบ DIIS-INVENTORY

หมายเหตุ: ข้อความนี้ถูกส่งโดยอัตโนมัติ กรุณาอย่าตอบกลับอีเมลนี้
"""

CATEGORY_MAP = {
    "software": "ซอฟต์แวร์",
    "product": "ครุภัณฑ์",
    "service": "จ้างเหมาบริการ",
    "other": "อื่นๆ",
}


def get_procurement_email_context(procurement):
    responsible_list = []
    procurement = models.Procurement.objects(id=procurement.id).first()

    if not procurement:
        return

    due_dates = procurement.get_payment_due_dates()
    for member in procurement.responsible_by:
        if member.user:
            user = member.user
            if user.email and user.get_name:
                responsible_list.append({"name": user.get_name(), "email": user.email})

    text_format = {
        "product_number": procurement.product_number,
        "asset_code": procurement.asset_code,
        "name": procurement.name,
        "category": procurement.category,
        "company": procurement.company,
        "amount": procurement.amount,
        "due_date": due_dates,
        "responsible_by": responsible_list,
    }

    return text_format


def send_payment_notification_job(
    procurement: models.Procurement,
    notif_type,
    days_left,
    setting,
):
    logger.debug("use MA_send_mail")

    text_format = get_procurement_email_context(procurement)

    if text_format and text_format["responsible_by"]:
        for person in text_format["responsible_by"]:
            if not person["email"]:
                logger.debug(f"attendant {person['name']} email is required")
                return False

    try:
        psu_smtp = PSUSMTP(setting)
        if not psu_smtp.login():
            logger.debug("email cannot login")
            return False

        subject_template_str = email_subject_template.get(
            notif_type, email_subject_template["default"]
        )
        template_subject = Template(subject_template_str)
        template_body = Template(email_body_template)

        if text_format and text_format["responsible_by"]:
            for person in text_format["responsible_by"]:
                context = {
                    **text_format,
                    "responsible_name": person["name"],
                    "notif_type": notif_type,
                    "days_left": days_left.get("days_left", ""),
                }
                email_subject = template_subject.render(context)
                email_body = template_body.render(context)

                logger.debug(f"send email to {person['email']}")
                psu_smtp.send_email(person["email"], email_subject, email_body)

        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"send_payment_notification_job error: {e}")
        return False
