import datetime

from flask import Blueprint, g, jsonify, request

from kampan import models
from kampan.web import acl

module = Blueprint("calendar", __name__, url_prefix="/calendar")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]

# คำขอที่ไม่อนุมัติหรือยกเลิกแล้วไม่จองรถ จึงไม่แสดงบนปฏิทิน
CALENDAR_STATUSES = ["pending", "active", "completed", "cancel_requested"]

EVENT_TONES = {
    "pending": "warning",
    "cancel_requested": "warning",
    "active": "success",
    "completed": "neutral",
}


def event_title(reservation):
    time = reservation.departure_datetime.strftime("%H:%M")
    title = f"{time} น. {reservation.location or '-'}"
    if reservation.car:
        title += f" ({reservation.car.license_plate})"
    return title


def event_of(reservation):
    last_day = reservation.return_datetime or reservation.departure_datetime
    return {
        "id": str(reservation.id),
        "title": event_title(reservation),
        "start": reservation.departure_datetime.strftime("%Y-%m-%d"),
        "end": (last_day + datetime.timedelta(days=1)).strftime("%Y-%m-%d"),
        "classNames": [f"event-{EVENT_TONES.get(reservation.status, 'neutral')}"],
    }


def parse_day(value):
    """วันของพารามิเตอร์ start/end ที่ FullCalendar ส่งมา (ISO date หรือ datetime มี offset)"""
    try:
        return datetime.datetime.strptime((value or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None


@module.route("/events")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def events():
    reservations = models.CarReservation.objects(
        organization=g.organization, status__in=CALENDAR_STATUSES
    )
    range_start = parse_day(request.args.get("start"))
    range_end = parse_day(request.args.get("end"))
    if range_start:
        reservations = reservations.filter(return_datetime__gte=range_start)
    if range_end:
        reservations = reservations.filter(departure_datetime__lt=range_end)
    return jsonify([event_of(reservation) for reservation in reservations])
