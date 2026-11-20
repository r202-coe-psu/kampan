"""แจ้งเตือนอีเมลของระบบจองรถออนไลน์

notify() คำนวณผู้รับตามเหตุการณ์แล้วส่ง job เข้าคิว (ส่งเฉพาะ id/string ไม่ส่ง document)
"""

import logging
import pathlib

from flask import current_app, has_app_context, has_request_context, url_for
from flask_login import current_user
from jinja2 import Environment, FileSystemLoader, TemplateError
from jinja2.sandbox import SandboxedEnvironment

from kampan import models
from kampan.web import redis_rq

from . import config, email_utils, car_reservation_flow, template_filters
from . import notifications as utils_notifications

logger = logging.getLogger(__name__)

# ชื่อระบบที่แสดงที่หัวอีเมล (แทนชื่อ DIIS INVENTORY ของระบบอื่น)
APP_NAME = "ระบบจองรถ"

EVENTS = (
    "submitted",
    "approved",
    "active",
    "denied",
    "cancel_requested",
    "cancelled",
    "completed",
    "close_disputed",
)

# template ของระบบ (fallback) อยู่ในไฟล์ ส่วน template ที่แอดมินองค์กรแก้ได้
# ต้อง render ด้วย sandbox เท่านั้น กัน SSTI
_TEMPLATE_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "web" / "templates" / "email"
)
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True
)


def _division_heads(reservation):
    if reservation.division is None:
        return []
    return [
        member.user
        for member in models.OrganizationUserRole.objects(
            organization=reservation.organization,
            status="active",
            roles="head",
            division=reservation.division,
        )
        if member.user is not None and member.user != reservation.creator
    ]


def _role_members(reservation, role):
    return car_reservation_flow.members_with_role(reservation.organization, role)


def people_for(reservation, event):
    """ผู้ใช้ที่ต้องรู้เหตุการณ์นี้ (ใช้ทั้งอีเมลและแจ้งเตือนในระบบ)"""
    if event == "submitted":
        people = _division_heads(reservation)
    elif event == "approved":
        key = car_reservation_flow.current_step_key(reservation)
        people = _role_members(reservation, key) if key else []
    elif event == "active":
        people = [reservation.creator, reservation.driver]
    elif event == "denied":
        people = [reservation.creator]
    elif event == "cancel_requested":
        people = _role_members(reservation, "dispatcher")
    elif event == "cancelled":
        people = [reservation.creator, reservation.driver]
    elif event == "completed":
        people = [reservation.creator]
    elif event == "close_disputed":
        people = _role_members(reservation, "dispatcher")
    elif event == "driver_assigned":
        people = [reservation.driver]
    else:
        people = []
    return people


def recipients_for(reservation, event):
    """อีเมลผู้รับของเหตุการณ์ (ไม่ซ้ำ ข้ามคนไม่มีอีเมล) เรียงตามลำดับที่พบ"""
    people = people_for(reservation, event)
    emails = []
    for person in people:
        email = getattr(person, "email", None)
        if email and email not in emails:
            emails.append(email)
    # ผู้ติดต่อรับแจ้งสถานะได้รับทุกอีเมลที่ส่งถึงผู้ขอ
    if reservation.creator in people and reservation.contact_email:
        if reservation.contact_email not in emails:
            emails.append(reservation.contact_email)
    return emails


def notify(reservation, event, actor=None):
    notify_in_app(reservation, event, actor)

    recipients = recipients_for(reservation, event)
    if not recipients:
        return None
    return redis_rq.redis_queue.queue.enqueue(
        send_car_reservation_email,
        args=(
            str(reservation.id),
            event,
            recipients,
            email_utils.get_host_url(current_app.config),
        ),
        timeout=600,
        job_timeout=600,
    )


# หัวข้อแจ้งเตือนในระบบของแต่ละเหตุการณ์
IN_APP_TITLES = {
    "submitted": "มีคำขอใช้รถรอการอนุมัติ",
    "approved": "มีคำขอใช้รถรอการอนุมัติ",
    "active": "คำขอใช้รถได้รับการอนุมัติ",
    "denied": "คำขอใช้รถไม่ได้รับการอนุมัติ",
    "cancel_requested": "มีคำขอยกเลิกการใช้รถ",
    "cancelled": "คำขอใช้รถถูกยกเลิก",
    "completed": "ปิดงานเที่ยวรถแล้ว",
    "close_disputed": "ผู้ขอโต้แย้งการปิดงาน",
    "driver_assigned": "คุณได้รับมอบหมายงานขับรถ",
}


# หัวข้อที่ผู้ทำ action เห็นในแจ้งเตือนของตัวเอง (driver_assigned เกิดพร้อมการอนุมัติ จึงไม่บันทึกซ้ำ)
OWN_ACTION_TITLES = {
    "submitted": "คุณยื่นคำขอใช้รถแล้ว",
    "approved": "คุณอนุมัติคำขอใช้รถแล้ว",
    "active": "คุณอนุมัติคำขอใช้รถแล้ว",
    "denied": "คุณไม่อนุมัติคำขอใช้รถ",
    "cancel_requested": "คุณขอยกเลิกการใช้รถแล้ว",
    "cancelled": "คุณยกเลิกคำขอใช้รถแล้ว",
    "completed": "คุณปิดงานเที่ยวรถแล้ว",
    "close_disputed": "คุณโต้แย้งการปิดงานแล้ว",
}


def notify_in_app(reservation, event, actor=None):
    """แจ้งเตือนในระบบอย่างเดียว (driver_assigned ไม่มีอีเมล)"""
    if actor is None and has_request_context() and current_user.is_authenticated:
        actor = current_user._get_current_object()
    common = dict(
        module="car_reservation",
        event=event,
        ref=reservation,
        message=reservation.location,
        url=url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=reservation.organization.id,
        ),
    )
    utils_notifications.send(
        reservation.organization,
        people_for(reservation, event),
        title=IN_APP_TITLES[event],
        actor=actor,
        **common,
    )
    if actor is not None and event in OWN_ACTION_TITLES:
        utils_notifications.record_own_action(
            reservation.organization, actor, title=OWN_ACTION_TITLES[event], **common
        )


_COMMENT_ACTIONS = ("denied", "cancel_requested", "cancelled", "close_disputed")


def _latest_comment(reservation):
    for log in reversed(reservation.audit_logs):
        if log.action in _COMMENT_ACTIONS and log.comment:
            return log.comment
    return "-"


def template_variables(reservation, host_url):
    """ตัวแปรที่ใช้ใน {{ ... }} ของอีเมลระบบจองรถ (ต้องตรง EMAIL_TEMPLATE_VARIABLES)"""
    step_key = car_reservation_flow.current_step_key(reservation)
    return {
        "organization_name": reservation.organization.name,
        "requester_name": reservation.creator.get_name(),
        "contact_name": reservation.contact_name or reservation.creator.get_name(),
        "request_type_label": dict(models.car_reservations.RESERVATION_TYPES)[
            reservation.request_type
        ],
        "destination": reservation.location,
        "departure": template_filters.format_thai_datetime_short_month(
            reservation.departure_datetime
        ),
        "return_at": template_filters.format_thai_datetime_short_month(
            reservation.return_datetime
        ),
        "status_label": dict(models.car_reservations.RESERVATION_STATUS)[
            reservation.status
        ],
        "step_label": car_reservation_flow.step_label(step_key) if step_key else "-",
        "car_plate": reservation.car.license_plate if reservation.car else "",
        "driver_name": reservation.driver.get_name() if reservation.driver else "",
        "reason": reservation.request_reason,
        "comment": _latest_comment(reservation),
        "request_url": (
            f"{host_url}/car_reservation/requests/{reservation.id}"
            f"?organization_id={reservation.organization.id}"
        ),
        # หน้าประเมินสาธารณะของรถคันนั้น เลือกเที่ยวนี้เป็นค่าตั้งต้น (ว่างถ้ายังไม่จัดรถ)
        "feedback_url": (
            f"{host_url}/car_reservation/cars/{reservation.car.id}/feedback"
            f"?reservation_id={reservation.id}"
            if reservation.car
            else ""
        ),
    }


_sandbox = SandboxedEnvironment()


def _render_custom(reservation, event, variables):
    email_template = reservation.organization.get_default_email_template(
        f"car_reservation_{event}"
    )
    if email_template is None:
        return None
    try:
        return (
            _sandbox.from_string(email_template.subject).render(variables),
            _sandbox.from_string(email_template.body).render(variables),
        )
    except TemplateError:
        # แอดมินแก้ template ผิดไวยากรณ์ หรือเรียกสิ่งที่ sandbox ห้าม: ใช้ข้อความของระบบแทน
        logger.warning(
            "car reservation email template %s cannot be rendered",
            email_template.id,
            exc_info=True,
        )
        return None


def _render_file(event, variables):
    module = _env.get_template(f"car_reservation/{event}.html").make_module(variables)
    return module.subject, str(module).strip()


def send_car_reservation_email(request_id, event, recipients, host_url):
    if event not in EVENTS:
        raise ValueError(f"unknown car reservation email event: {event}")
    reservation = models.CarReservation.objects(id=request_id).first()
    if reservation is None:
        logger.warning("car reservation %s not found for email", request_id)
        return False

    variables = template_variables(reservation, host_url)
    subject, body = _render_custom(reservation, event, variables) or _render_file(
        event, variables
    )

    setting = current_app.config if has_app_context() else config.get_settings()
    smtp = email_utils.PSUSMTP(setting)
    if not smtp.login():
        logger.warning("car reservation email cannot login to smtp")
        return False
    # PSUSMTP ส่งได้ทีละผู้รับ จึงส่งแยกฉบับต่อคน
    for recipient in recipients:
        smtp.send_email(
            recipient, subject, body, html=True, app_name=APP_NAME
        )
    smtp.quit()
    return True
