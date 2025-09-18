from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)


email_subject_template = (
    "คำขออนุมัติรถจักรยานยนต์ใหม่จาก {{ motorcycle_application_creator }}"
)

# ตัวอย่าง body template
email_body_template = """
สวัสดี {{ endorser_name }},

มีคำขออนุมัติรถจักรยานยนต์ใหม่

ผู้ขอ: {{ motorcycle_application_creator }} ({{ motorcycle_application_creator_email }})

กรุณาตรวจสอบและอนุมัติคำขอนี้โดยคลิกที่ลิงก์ด้านล่าง:
{{ endorsement_url }}

ข้อความนี้ถูกส่งโดยอัตโนมัติจาก,
ระบบขอใช้รถจักรยานยนต์
"""


def get_endorser_text_format(sender, endorser, motorcycle_application, endorsement_url):

    text_format = {
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "motorcycle_application_email": motorcycle_application.creator.email,
        "motorcycle_application_creator": motorcycle_application.creator.get_name(),
        "motorcycle_application_creator_email": motorcycle_application.creator.email,
        "endorser_name": endorser.get_name(),
        "endorsement_url": endorsement_url,
    }
    return text_format


def force_send_email_to_admin(
    motorcycle_application: models.vehicle_applications.MotorcycleApplication,
    user,
    setting,
):
    logger.debug("use send_email_to_admin ")

    creator = motorcycle_application.creator
    division = motorcycle_application.division
    organization = division.organization
    all_admins = organization.get_admins()

    if not creator.email:
        logger.debug(f"attendant {creator.name} email is required")
        return False

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        logger.debug("email cannot login")
        return False

    for admin in all_admins:
        if not admin.email:
            pass
        template_subject = Template(email_subject_template)
        template_body = Template(email_body_template)

        host_url = setting.get("KAMPAN_HOST_URL")
        endorsement_url = f"{host_url}/vehicle_lending/motorcycle_permissions/admin_page?organization_id={organization.id}"

        text_format = get_endorser_text_format(
            user, admin, motorcycle_application, endorsement_url
        )

        email_subject = template_subject.render(text_format)
        email_body = template_body.render(text_format)

        logger.debug(f"send email to {admin.email}")

        motorcycle_application.save()
        psu_smtp.send_email(admin.email, email_subject, email_body)

    psu_smtp.quit()
    return True
