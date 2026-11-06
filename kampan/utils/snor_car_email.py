"""แจ้งเตือนอีเมลของระบบจองรถ snor

notify() คำนวณผู้รับตามเหตุการณ์แล้วส่ง job เข้าคิว (ส่งเฉพาะ id/string ไม่ส่ง document)
"""

from flask import current_app

from kampan import models
from kampan.web import redis_rq

from . import email_utils, snor_car_flow


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


def send_snor_car_email(request_id, event, recipients, host_url):
    raise NotImplementedError
