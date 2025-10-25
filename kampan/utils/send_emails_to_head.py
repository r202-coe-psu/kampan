from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = "[แจ้งเตือน] ขออนุมัติซื้อ/จ้างพัสดุ"

email_body_template = """ 
เรียน หัวหน้าฝ่าย

    {{ purchaser_name }} จาก {{ purchaser_division }} มีความต้องการขอซื้อ/จ้าง ตามรายละเอียดดังนี้
ใบขอซื้อ/จ้างเลขที่: {{ requisition_code }}
รายการขอซื้อ:
{% for item in items %}  
    - {{ item }}
{% endfor %}
เหตุผลความต้องการ: {{ reason }}

ระบบขอซื้อพัสดุ
Link เอกสาร: {{ document_url }}

ด้วยความเคารพ
{{ purchaser_name }}
อีเมลติดต่อ
{{ purchaser_email }}
"""


def get_head_text_format(requisition, setting):

    req = models.Requisition.objects(id=requisition.id).first()
    if not req:
        return

    purchaser = req.purchaser

    user = purchaser.user if purchaser and purchaser.user else None

    purchaser_name = (
        user.get_name() if user else purchaser.display_name() if purchaser else "-"
    )
    purchaser_division = (
        purchaser.division.name if purchaser and purchaser.division else "-"
    )
    purchaser_division_id = (
        str(purchaser.division.id) if purchaser and purchaser.division else "-"
    )
    purchaser_email = user.email if user else purchaser.email if purchaser else "-"
    host_url = setting.get("KAMPAN_HOST_URL")
    document_url = f"{host_url}/procurement/requisitions/{requisition.id}/document"

    text_format = {
        "requisition_code": req.requisition_code,
        "items": [item.product_name for item in req.items],
        "reason": req.reason,
        "purchaser_name": purchaser_name,
        "purchaser_division": purchaser_division,
        "purchaser_division_id": purchaser_division_id,
        "purchaser_email": purchaser_email,
        "document_url": document_url,
    }
    return text_format


def send_email_to_head(
    requisition: models.Requisition,
    user_id,
    setting,
    organization,
):
    logger.debug("use send_email_to_head ")
    text_format = get_head_text_format(requisition, setting)
    all_heads = organization.get_heads_by_division(text_format["purchaser_division_id"])

    if not text_format:
        logger.debug("no text format for email to head")
        return False

    purchaser_email = text_format["purchaser_email"]
    if not purchaser_email or purchaser_email == "-":
        logger.debug("purchaser email is required")
        return False

    try:
        psu_smtp = PSUSMTP(setting)
        if not psu_smtp.login():
            return False

        email_subject = Template(email_subject_template).render(text_format)
        email_body = Template(email_body_template).render(text_format)
        print(email_subject)
        print(email_body)

        for head in all_heads:
            if not head.email:
                logger.debug(f"head {head.get_name()} email is required")
                continue
            try:
                logger.debug(f"send email to {head.email}")
                psu_smtp.send_email(head.email, email_subject, email_body)
            except Exception as e:
                logger.error(f"send_email_to_head error: {e}")
                continue

        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"send_email_to_head error: {e}")
        return False
