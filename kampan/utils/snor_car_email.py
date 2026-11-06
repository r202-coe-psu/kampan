"""แจ้งเตือนอีเมลของระบบจองรถ snor

notify() คำนวณผู้รับตามเหตุการณ์แล้วส่ง job เข้าคิว (ส่งเฉพาะ id/string ไม่ส่ง document)
"""

import logging
import pathlib

from flask import current_app, has_app_context
from jinja2 import Environment, FileSystemLoader

from kampan import models
from kampan.web import redis_rq

from . import config, email_utils, snor_car_flow, template_filters

logger = logging.getLogger(__name__)

EVENTS = (
    "submitted",
    "approved",
    "active",
    "denied",
    "cancel_requested",
    "cancelled",
)

# ข้อความอีเมลมาจากไฟล์ template ของระบบเท่านั้น (ไม่ render ข้อความที่ผู้ใช้กรอก) กัน SSTI
_TEMPLATE_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "web" / "templates" / "email"
)
_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR), trim_blocks=True, lstrip_blocks=True
)
_env.filters["thai_datetime"] = template_filters.format_thai_datetime_short_month


def _division_heads(snor_request):
    if snor_request.division is None:
        return []
    return [
        member.user
        for member in models.OrganizationUserRole.objects(
            organization=snor_request.organization,
            status="active",
            roles="head",
            division=snor_request.division,
        )
        if member.user is not None and member.user != snor_request.creator
    ]


def _position_people(snor_request, position_key):
    position = models.CarFlowPosition.objects(
        organization=snor_request.organization, position_key=position_key
    ).first()
    if position is None:
        return []
    return [position.user] + list(position.delegates)


def recipients_for(snor_request, event):
    """อีเมลผู้รับของเหตุการณ์ (ไม่ซ้ำ ข้ามคนไม่มีอีเมล) เรียงตามลำดับที่พบ"""
    if event == "submitted":
        people = _division_heads(snor_request)
    elif event == "approved":
        key = snor_car_flow.current_step_key(snor_request)
        people = _position_people(snor_request, key) if key else []
    elif event == "active":
        people = [snor_request.creator, snor_request.driver]
    elif event == "denied":
        people = [snor_request.creator]
    elif event == "cancel_requested":
        people = _position_people(snor_request, "dispatcher")
    elif event == "cancelled":
        people = [snor_request.creator, snor_request.driver]
    else:
        people = []

    emails = []
    for person in people:
        email = getattr(person, "email", None)
        if email and email not in emails:
            emails.append(email)
    return emails


def notify(snor_request, event):
    recipients = recipients_for(snor_request, event)
    if not recipients:
        return None
    return redis_rq.redis_queue.queue.enqueue(
        send_snor_car_email,
        args=(
            str(snor_request.id),
            event,
            recipients,
            email_utils.get_host_url(current_app.config),
        ),
        timeout=600,
        job_timeout=600,
    )


def _context(snor_request, host_url):
    link = (
        f"{host_url}/snor_car/requests/{snor_request.id}"
        f"?organization_id={snor_request.organization.id}"
    )
    return {
        "requester_name": snor_request.creator.get_name(),
        "request_type_label": dict(models.snor_car_requests.SNOR_REQUEST_TYPES)[
            snor_request.request_type
        ],
        "destination": snor_request.location,
        "departure": snor_request.departure_datetime,
        "return_at": snor_request.return_datetime,
        "status_label": dict(models.snor_car_requests.SNOR_REQUEST_STATUS)[
            snor_request.status
        ],
        "car_plate": snor_request.car.license_plate if snor_request.car else "",
        "driver_name": snor_request.driver.get_name() if snor_request.driver else "",
        "link": link,
    }


def send_snor_car_email(request_id, event, recipients, host_url):
    if event not in EVENTS:
        raise ValueError(f"unknown snor car email event: {event}")
    snor_request = models.SnorCarRequest.objects(id=request_id).first()
    if snor_request is None:
        logger.warning("snor car request %s not found for email", request_id)
        return False

    module = _env.get_template(f"snor_car/{event}.html").make_module(
        _context(snor_request, host_url)
    )
    subject = module.subject
    body = str(module).strip()

    setting = current_app.config if has_app_context() else config.get_settings()
    smtp = email_utils.PSUSMTP(setting)
    if not smtp.login():
        logger.warning("snor car email cannot login to smtp")
        return False
    # PSUSMTP ส่งได้ทีละผู้รับ จึงส่งแยกฉบับต่อคน
    for recipient in recipients:
        smtp.send_email(recipient, subject, body, html=True)
    smtp.quit()
    return True
