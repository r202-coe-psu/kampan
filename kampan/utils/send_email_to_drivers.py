from jinja2 import Template
import logging
from kampan import models
from .email_utils import PSUSMTP

logger = logging.getLogger(__name__)

# แจ้งเตือนอีเมลว่ามี นัดหมายการใช้รถยนต์ไปยังคนขับ เมื่อมีการอนุมัติคำขอใช้รถยนต์
email_subject_template = (
    "นัดหมายการใช้รถยนต์ใหม่ ณ {{ appointment_datetime }} จาก {{ car_application_creator }}"
)

email_body_template = """
สวัสดี {{ driver_name }},
มีนัดหมายการใช้รถยนต์ใหม่จาก {{ car_application_creator }} 

ณ วันที่และเวลา: {{ appointment_datetime }}
จุดหมายปลายทาง: {{ destination }}

ข้อความนี้ถูกส่งโดยอัตโนมัติจาก
ระบบขอใช้รถยนต์
"""


def get_driver_text_format(
    sender, driver, car_application, appointment_datetime, destination
):

    text_format = {
        "sender_name": sender.get_name(),
        "sender_email": sender.email,
        "car_application_creator": car_application.creator.get_name(),
        "driver_name": driver.get_name(),
        "appointment_datetime": appointment_datetime,
        "destination": destination,
    }
    return text_format


def force_send_email_to_driver(
    car_application: models.vehicle_applications.CarApplication,
    user,
    setting,
):
    logger.debug("use send_email_to_driver ")

    creator = car_application.creator
    organization = car_application.division.organization
    drivers = organization.get_all_drivers()
    appointment_datetime = car_application.departure_datetime.strftime("%d/%m/%Y %H:%M")
    destination = car_application.location

    if not creator.email:
        logger.debug(f"attendant {creator.name} email is required")
        return False
    if not drivers:
        logger.debug("no active drivers found")
        return False

    psu_smtp = PSUSMTP(setting)
    if not psu_smtp.login():
        return False

    sender = user
    for driver in drivers:
        text_format = get_driver_text_format(
            sender, driver, car_application, appointment_datetime, destination
        )

        subject_template = Template(email_subject_template)
        email_subject = subject_template.render(text_format)

        body_template = Template(email_body_template)
        email_body = body_template.render(text_format)

        success = psu_smtp.send_email(
            to_email=driver.email,
            to_name=driver.get_name(),
            subject=email_subject,
            body=email_body,
        )
    psu_smtp.quit()
    return success
