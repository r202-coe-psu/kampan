"""งานของพนักงานขับรถ: เห็นเฉพาะงานที่ถูกจัดให้ตัวเอง"""

from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, url_for
from flask_login import current_user

from kampan import models, utils
from kampan.web import forms

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


def get_task_or_404(task_id):
    try:
        task = models.CarReservation.objects(
            id=task_id, organization=g.organization
        ).first()
    except Exception:
        task = None
    if task is None:
        abort(404)
    return task


@module.route("/<task_id>/close", methods=["GET", "POST"])
@driver_required
def close(task_id):
    task = get_task_or_404(task_id)
    user = current_user._get_current_object()
    if not flow.can_close(task, user):
        abort(403)

    form = forms.car_reservation.TripCloseForm()
    if form.validate_on_submit():
        try:
            flow.close_trip(
                task,
                user,
                mileage_out=form.mileage_out.data,
                mileage_in=form.mileage_in.data,
                expense_case=form.expense_case.data,
                fuel_liters=form.fuel_liters.data,
                cost_baht=form.cost_baht.data,
            )
        except flow.FlowError as error:
            form.mileage_in.errors = [*form.mileage_in.errors, str(error)]
        else:
            flash("ปิดงานเรียบร้อยแล้ว", "success")
            return redirect(
                url_for(
                    "car_reservation.tasks.index", organization_id=g.organization.id
                )
            )
    return render_template(
        "/car_reservation/tasks/close.html",
        organization=g.organization,
        task=task,
        form=form,
    )
