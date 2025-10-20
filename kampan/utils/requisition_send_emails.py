from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

email_subject_template = {
    "complete": "[แจ้งเตือน] รายการขอซื้อ/จัดหาเลขที่ {{ requisition_code }} ได้รับการอนุมัติสมบูรณ์"
}

email_body_template = """
เรียน {{ purchaser }},
มีรายการขอซื้อ/จัดหาเลขที่ {{ requisition_code }} ซึ่งได้รับการอนุมัติสมบูรณ์แล้ว
"""


def get_requisition_text_format(requisition):
    req = models.Requisition.objects(id=requisition.id).first()
    if not req:
        return

    purchaser = req.purchaser
    user = purchaser.user if purchaser and purchaser.user else None

    purchaser_name = (
        user.get_name() if user else purchaser.display_name() if purchaser else "-"
    )
    purchaser_email = user.email if user else purchaser.email if purchaser else "-"

    text_format = {
        "requisition_code": req.requisition_code,
        "purchaser": purchaser_name,
        "purchaser_email": purchaser_email,
    }
    return text_format


def requisition_send_emails(
    requisition: models.Requisition,
    setting,
):
    logger.debug("use requisition_send_emails")

    text_format = get_requisition_text_format(requisition)

    if not text_format["purchaser_email"]:
        return False

    try:
        psu_smtp = PSUSMTP(setting)
        if not psu_smtp.login():
            logger.debug("email cannot login")
            return False

        subject_template_str = email_subject_template.get(
            "complete", email_subject_template["complete"]
        )

        template_subject = Template(subject_template_str)
        template_body = Template(email_body_template)

        email_subject = template_subject.render(
            requisition_code=text_format["requisition_code"]
        )
        email_body = template_body.render(
            purchaser=text_format["purchaser"],
            requisition_code=text_format["requisition_code"],
        )

        logger.debug(f"send email to {text_format['purchaser_email']}")
        psu_smtp.send_email(text_format["purchaser_email"], email_subject, email_body)

        psu_smtp.quit()
        return True
    except Exception as e:
        logger.error(f"requisition_send_emails error: {e}")
        return False
