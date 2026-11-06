import datetime

from flask import Blueprint, g, jsonify

from kampan import models
from kampan.web import acl

module = Blueprint("calendar", __name__, url_prefix="/calendar")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]

# คำขอที่ไม่อนุมัติหรือยกเลิกแล้วไม่จองรถ จึงไม่แสดงบนปฏิทิน
CALENDAR_STATUSES = ["pending", "active", "completed", "cancel_requested"]


@module.route("/events")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def events():
    reservations = models.CarReservation.objects(
        organization=g.organization, status__in=CALENDAR_STATUSES
    )
    return jsonify(
        [
            {"id": str(reservation.id), "title": reservation.location}
            for reservation in reservations
        ]
    )
