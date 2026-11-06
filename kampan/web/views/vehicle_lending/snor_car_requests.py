import datetime

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

module = Blueprint("snor_car_requests", __name__, url_prefix="/snor_car_requests")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]
snor = utils.car_flows.snor


def get_car_application_or_404(car_application_id):
    try:
        car_application = models.vehicle_applications.CarApplication.objects(
            id=car_application_id, organization=g.organization
        ).first()
    except Exception:
        car_application = None
    if car_application is None or not car_application.request_type:
        abort(404)
    return car_application


def supervisor_choices(organization):
    """สมาชิก active ขององค์กร ยกเว้นตัวผู้ขอเอง"""
    me = current_user._get_current_object()
    choices = {}
    for member_role in models.OrganizationUserRole.objects(
        organization=organization, status="active"
    ):
        user = member_role.user
        if user is None or user == me:
            continue
        choices[str(user.id)] = user.get_name()
    return list(choices.items())


@module.route("/new", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def create():
    organization = g.organization
    request_type = request.args.get("type", "domestic")
    if request_type not in dict(models.vehicle_applications.SNOR_REQUEST_TYPES):
        abort(404)

    form = forms.snor_car_requests.SnorCarRequestForm()
    form.supervisor.choices = supervisor_choices(organization)

    if form.validate_on_submit():
        user = current_user._get_current_object()
        car_application = models.vehicle_applications.CarApplication(
            organization=organization,
            creator=user,
            updater=user,
            request_type=request_type,
            using_type="general",  # ช่องของ flow DIIS ที่ต้องมีค่าตาม choices; snor ใช้ request_type แทน
            province_scope=form.province_scope.data if request_type == "domestic" else None,
            supervisor=models.User.objects.get(id=form.supervisor.data),
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
        snor.submit(car_application, user)
        flash("ยื่นคำขอใช้รถเรียบร้อยแล้ว", "success")
        return redirect(
            url_for(
                "vehicle_lending.snor_car_requests.detail",
                car_application_id=car_application.id,
                organization_id=organization.id,
            )
        )

    return render_template(
        "/vehicle_lending/snor_car_requests/form.html",
        organization=organization,
        form=form,
        request_type=request_type,
        request_type_label=dict(models.vehicle_applications.SNOR_REQUEST_TYPES)[
            request_type
        ],
    )


def stepper(car_application):
    """รายการขั้นของเส้นทางพร้อมสถานะ done/current/waiting/denied"""
    decisions = {
        approval.step_key: approval for approval in car_application.step_approvals
    }
    steps = []
    for index, key in enumerate(car_application.route_snapshot):
        approval = decisions.get(key)
        if approval and approval.decision == "denied":
            state = "denied"
        elif approval:
            state = "done"
        elif index == car_application.current_step and car_application.status == "pending":
            state = "current"
        else:
            state = "waiting"
        steps.append({"key": key, "label": snor.step_label(key), "state": state})
    return steps


@module.route("/<car_application_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def detail(car_application_id):
    car_application = get_car_application_or_404(car_application_id)
    current_key = snor.current_step_key(car_application)
    return render_template(
        "/vehicle_lending/snor_car_requests/detail.html",
        organization=g.organization,
        car_application=car_application,
        steps=stepper(car_application),
        current_step_label=snor.step_label(current_key) if current_key else "",
        can_act=snor.can_act(car_application, current_user._get_current_object()),
        form=forms.snor_car_requests.ApprovalDecisionForm(),
    )


@module.route("/<car_application_id>/approve", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def approve(car_application_id):
    car_application = get_car_application_or_404(car_application_id)
    form = forms.snor_car_requests.ApprovalDecisionForm()
    if not form.validate_on_submit():
        abort(400)

    try:
        snor.approve(
            car_application,
            current_user._get_current_object(),
            comment=form.comment.data or "",
        )
    except snor.FlowError:
        abort(403)

    flash("บันทึกการอนุมัติเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "vehicle_lending.snor_car_requests.detail",
            car_application_id=car_application.id,
            organization_id=g.organization.id,
        )
    )
