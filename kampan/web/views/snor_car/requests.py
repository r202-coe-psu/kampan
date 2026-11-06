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

module = Blueprint("requests", __name__, url_prefix="/requests")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]
snor = utils.snor_car_flow


def get_request_or_404(request_id):
    try:
        snor_request = models.SnorCarRequest.objects(
            id=request_id, organization=g.organization
        ).first()
    except Exception:
        snor_request = None
    if snor_request is None:
        abort(404)
    return snor_request


@module.route("/")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    snor_requests = models.SnorCarRequest.objects(
        organization=g.organization, creator=current_user._get_current_object()
    ).order_by("-created_date")
    return render_template(
        "/snor_car/requests/index.html",
        organization=g.organization,
        snor_requests=snor_requests,
    )


@module.route("/new", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def create():
    organization = g.organization
    request_type = request.args.get("type", "domestic")
    if request_type not in dict(models.snor_car_requests.SNOR_REQUEST_TYPES):
        abort(404)

    form = forms.snor_car.SnorCarRequestForm()

    user = current_user._get_current_object()
    member = models.OrganizationUserRole.objects(
        user=user, organization=organization, status="active"
    ).first()
    division = member.division if member else None

    submitted = form.validate_on_submit()
    if submitted and snor.is_too_far_ahead(form.departure_date.data):
        form.departure_date.errors.append(snor.TOO_FAR_AHEAD)
        submitted = False
    if submitted and datetime.datetime.combine(
        form.return_date.data, form.return_time.data
    ) < datetime.datetime.combine(form.departure_date.data, form.departure_time.data):
        form.return_date.errors.append("วันกลับต้องไม่ก่อนวันออกเดินทาง")
        submitted = False
    short_notice_days = None
    is_urgent = False
    if submitted and snor.is_short_notice(
        organization, request_type, form.departure_date.data
    ):
        if form.confirm_urgent.data:
            is_urgent = True
        else:
            short_notice_days = snor.min_business_days(request_type)
            submitted = False
    if submitted and not snor.has_division_head(organization, division, excluding=user):
        flash("ฝ่ายของคุณยังไม่มีหัวหน้าฝ่าย กรุณาติดต่อผู้ดูแลระบบ", "danger")
    elif submitted:
        snor_request = models.SnorCarRequest(
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
        snor.submit(snor_request, user)
        flash("ยื่นคำขอใช้รถเรียบร้อยแล้ว", "success")
        return redirect(
            url_for(
                "snor_car.requests.detail",
                request_id=snor_request.id,
                organization_id=organization.id,
            )
        )

    return render_template(
        "/snor_car/requests/form.html",
        organization=organization,
        form=form,
        short_notice_days=short_notice_days,
        request_type=request_type,
        request_type_label=dict(models.snor_car_requests.SNOR_REQUEST_TYPES)[
            request_type
        ],
    )


def stepper(snor_request):
    """รายการขั้นของเส้นทางพร้อมสถานะ done/current/waiting/denied"""
    decisions = {
        approval.step_key: approval for approval in snor_request.step_approvals
    }
    steps = []
    for index, key in enumerate(snor_request.route_snapshot):
        approval = decisions.get(key)
        if approval and approval.decision == "denied":
            state = "denied"
        elif approval:
            state = "done"
        elif index == snor_request.current_step and snor_request.status == "pending":
            state = "current"
        else:
            state = "waiting"
        steps.append({"key": key, "label": snor.step_label(key), "state": state})
    return steps


@module.route("/<request_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def detail(request_id):
    snor_request = get_request_or_404(request_id)
    current_key = snor.current_step_key(snor_request)
    return render_template(
        "/snor_car/requests/detail.html",
        organization=g.organization,
        snor_request=snor_request,
        steps=stepper(snor_request),
        current_step_label=snor.step_label(current_key) if current_key else "",
        can_act=snor.can_act(snor_request, current_user._get_current_object()),
        form=forms.snor_car.ApprovalDecisionForm(),
        deny_form=forms.snor_car.DenyDecisionForm(),
    )


@module.route("/<request_id>/approve", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def approve(request_id):
    snor_request = get_request_or_404(request_id)
    form = forms.snor_car.ApprovalDecisionForm()
    if not form.validate_on_submit():
        abort(400)

    try:
        snor.approve(
            snor_request,
            current_user._get_current_object(),
            comment=form.comment.data or "",
        )
    except snor.FlowError:
        abort(403)

    flash("บันทึกการอนุมัติเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "snor_car.requests.detail",
            request_id=snor_request.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/deny", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def deny(request_id):
    snor_request = get_request_or_404(request_id)
    form = forms.snor_car.DenyDecisionForm()
    redirect_to_detail = redirect(
        url_for(
            "snor_car.requests.detail",
            request_id=snor_request.id,
            organization_id=g.organization.id,
        )
    )
    if not snor.can_act(snor_request, current_user._get_current_object()):
        abort(403)
    if not form.validate_on_submit():
        flash("กรุณาระบุเหตุผลที่ไม่อนุมัติ", "danger")
        return redirect_to_detail

    snor.deny(
        snor_request,
        current_user._get_current_object(),
        comment=form.comment.data,
    )
    flash("บันทึกการไม่อนุมัติเรียบร้อยแล้ว", "success")
    return redirect_to_detail
