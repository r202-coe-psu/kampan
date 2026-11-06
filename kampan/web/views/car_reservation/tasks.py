"""งานของพนักงานขับรถ: เห็นเฉพาะงานที่ถูกจัดให้ตัวเอง"""

from functools import wraps

from flask import Blueprint, abort, g, render_template
from flask_login import current_user

from kampan import models, utils

module = Blueprint("tasks", __name__, url_prefix="/tasks")

flow = utils.car_reservation_flow

RECENT_COMPLETED_LIMIT = 10


def driver_required(func):
    """เฉพาะสมาชิก role driver ของ org ที่ดูอยู่ (admin ของ org หรือของระบบก็ไม่ผ่าน)"""

    @wraps(func)
    def wrapped(*args, **kwargs):
        organization = getattr(g, "organization", None)
        if (
            not current_user.is_authenticated
            or organization is None
            or getattr(g, "organization_denied", False)
            or not flow.has_role(
                organization, current_user._get_current_object(), "driver"
            )
        ):
            abort(403)
        return func(*args, **kwargs)

    return wrapped


def my_tasks(status):
    return models.CarReservation.objects(
        organization=g.organization,
        driver=current_user._get_current_object(),
        status=status,
    )


@module.route("/")
@driver_required
def index():
    return render_template(
        "/car_reservation/tasks/index.html",
        organization=g.organization,
        active_tasks=my_tasks("active").order_by("departure_datetime"),
        completed_tasks=my_tasks("completed").order_by("-departure_datetime")[
            :RECENT_COMPLETED_LIMIT
        ],
    )
