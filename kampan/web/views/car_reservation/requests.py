import datetime

from bson import ObjectId
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint("requests", __name__, url_prefix="/requests")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]
flow = utils.car_reservation_flow


def get_request_or_404(request_id):
    try:
        reservation = models.CarReservation.objects(
            id=request_id, organization=g.organization
        ).first()
    except Exception:
        reservation = None
    if reservation is None:
        abort(404)
    return reservation


@module.route("/")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    reservations = models.CarReservation.objects(
        organization=g.organization, creator=current_user._get_current_object()
    ).order_by("-created_date")
    return render_template(
        "/car_reservation/requests/index.html",
        organization=g.organization,
        reservations=reservations,
    )


@module.route("/inbox")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def inbox():
    waiting = flow.inbox_for(g.organization, current_user._get_current_object())
    return render_template(
        "/car_reservation/requests/inbox.html",
        organization=g.organization,
        reservations=waiting,
        step_label=lambda app: flow.step_label(
            flow.current_step_key(app) or "dispatcher"
        ),
    )


@module.route("/new", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def create():
    organization = g.organization
    request_type = request.args.get("type", "domestic")
    if request_type not in dict(models.car_reservations.RESERVATION_TYPES):
        abort(404)

    form = forms.car_reservation.CarReservationForm()

    user = current_user._get_current_object()
    member = models.OrganizationUserRole.objects(
        user=user, organization=organization, status="active"
    ).first()
    division = member.division if member else None

    submitted = form.validate_on_submit()
    if submitted and flow.is_too_far_ahead(form.departure_date.data):
        form.departure_date.errors.append(flow.TOO_FAR_AHEAD)
        submitted = False
    if submitted and datetime.datetime.combine(
        form.return_date.data, form.return_time.data
    ) < datetime.datetime.combine(form.departure_date.data, form.departure_time.data):
        form.return_date.errors.append("วันกลับต้องไม่ก่อนวันออกเดินทาง")
        submitted = False
    short_notice_days = None
    is_urgent = False
    if submitted and flow.is_short_notice(
        organization, request_type, form.departure_date.data
    ):
        if form.confirm_urgent.data:
            is_urgent = True
        else:
            short_notice_days = flow.min_business_days(request_type)
            submitted = False
    if submitted and not flow.has_division_head(organization, division, excluding=user):
        flash("ฝ่ายของคุณยังไม่มีหัวหน้าฝ่าย กรุณาติดต่อผู้ดูแลระบบ", "danger")
    elif submitted:
        reservation = models.CarReservation(
            organization=organization,
            division=division,
            creator=user,
            updater=user,
            request_type=request_type,
            is_urgent=is_urgent,
            province_scope=form.province_scope.data if request_type == "domestic" else None,
            requester_unit=form.requester_unit.data,
            phone=form.phone.data,
            location=form.location.data,
            request_reason=form.request_reason.data,
            passenger_number=form.passenger_number.data,
            departure_datetime=datetime.datetime.combine(
                form.departure_date.data, form.departure_time.data
            ),
            return_datetime=datetime.datetime.combine(
                form.return_date.data, form.return_time.data
            ),
        )
        flow.submit(reservation, user)
        utils.car_reservation_email.notify(reservation, "submitted")
        flash("ยื่นคำขอใช้รถเรียบร้อยแล้ว", "success")
        return redirect(
            url_for(
                "car_reservation.requests.detail",
                request_id=reservation.id,
                organization_id=organization.id,
            )
        )

    return render_template(
        "/car_reservation/requests/form.html",
        organization=organization,
        form=form,
        short_notice_days=short_notice_days,
        request_type=request_type,
        request_type_label=dict(models.car_reservations.RESERVATION_TYPES)[
            request_type
        ],
    )


def stepper(reservation):
    """รายการขั้นของเส้นทางพร้อมสถานะ done/current/waiting/denied"""
    decisions = {
        approval.step_key: approval for approval in reservation.step_approvals
    }
    steps = []
    for index, key in enumerate(reservation.route_snapshot):
        approval = decisions.get(key)
        if approval and approval.decision == "denied":
            state = "denied"
        elif approval:
            state = "done"
        elif index == reservation.current_step and reservation.status == "pending":
            state = "current"
        else:
            state = "waiting"
        steps.append({"key": key, "label": flow.step_label(key), "state": state})
    return steps


@module.route("/<request_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def detail(request_id):
    reservation = get_request_or_404(request_id)
    current_key = flow.current_step_key(reservation)
    if current_key == "dispatcher":
        form = forms.car_reservation.DispatchDecisionForm()
        form.car.choices = [
            (str(car.id), f"{car.license_plate} ({car.vehicle_type or '-'})")
            for car in flow.assignable_cars(g.organization)
        ]
        form.driver.choices = [
            (str(user.id), user.get_name())
            for user in flow.assignable_drivers(g.organization)
        ]
    else:
        form = forms.car_reservation.ApprovalDecisionForm()
    return render_template(
        "/car_reservation/requests/detail.html",
        organization=g.organization,
        reservation=reservation,
        steps=stepper(reservation),
        current_step_label=flow.step_label(current_key) if current_key else "",
        can_act=flow.can_act(reservation, current_user._get_current_object()),
        can_cancel=flow.can_cancel(
            reservation, current_user._get_current_object()
        ),
        can_confirm_cancel=flow.can_confirm_cancel(
            reservation, current_user._get_current_object()
        ),
        cancel_form=forms.car_reservation.CancelRequestForm(),
        form=form,
        deny_form=forms.car_reservation.DenyDecisionForm(),
    )


@module.route("/<request_id>/approve", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def approve(request_id):
    reservation = get_request_or_404(request_id)
    dispatching = flow.current_step_key(reservation) == "dispatcher"
    form = (
        forms.car_reservation.DispatchDecisionForm()
        if dispatching
        else forms.car_reservation.ApprovalDecisionForm()
    )
    if not form.validate_on_submit():
        abort(400)

    assignment = {}
    if dispatching:
        assignment = {
            "car": models.vehicles.Car.objects(
                id=form.car.data, organization=g.organization
            ).first()
            if ObjectId.is_valid(form.car.data)
            else None,
            "driver": models.User.objects(id=form.driver.data).first()
            if ObjectId.is_valid(form.driver.data)
            else None,
        }
    try:
        flow.approve(
            reservation,
            current_user._get_current_object(),
            comment=form.comment.data or "",
            **assignment,
        )
    except flow.FlowError as error:
        if not dispatching or not flow.can_act(
            reservation, current_user._get_current_object()
        ):
            abort(403)
        flash(str(error), "danger")
        return redirect(
            url_for(
                "car_reservation.requests.detail",
                request_id=reservation.id,
                organization_id=g.organization.id,
            )
        )

    utils.car_reservation_email.notify(
        reservation, "active" if reservation.status == "active" else "approved"
    )
    flash("บันทึกการอนุมัติเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/deny", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def deny(request_id):
    reservation = get_request_or_404(request_id)
    form = forms.car_reservation.DenyDecisionForm()
    redirect_to_detail = redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )
    if not flow.can_act(reservation, current_user._get_current_object()):
        abort(403)
    if not form.validate_on_submit():
        flash("กรุณาระบุเหตุผลที่ไม่อนุมัติ", "danger")
        return redirect_to_detail

    flow.deny(
        reservation,
        current_user._get_current_object(),
        comment=form.comment.data,
    )
    utils.car_reservation_email.notify(reservation, "denied")
    flash("บันทึกการไม่อนุมัติเรียบร้อยแล้ว", "success")
    return redirect_to_detail


@module.route("/<request_id>/cancel", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def cancel(request_id):
    reservation = get_request_or_404(request_id)
    form = forms.car_reservation.CancelRequestForm()
    try:
        flow.cancel(
            reservation,
            current_user._get_current_object(),
            reason=form.reason.data or "",
        )
    except flow.FlowError:
        abort(403)
    utils.car_reservation_email.notify(reservation, reservation.status)
    flash("ยกเลิกคำขอเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/cancel/confirm", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def confirm_cancel(request_id):
    reservation = get_request_or_404(request_id)
    try:
        flow.confirm_cancel(reservation, current_user._get_current_object())
    except flow.FlowError:
        abort(403)
    utils.car_reservation_email.notify(reservation, "cancelled")
    flash("รับทราบการยกเลิกเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )
