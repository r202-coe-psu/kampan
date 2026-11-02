from flask import Blueprint, abort, flash, render_template, redirect, url_for, request
from flask_wtf import FlaskForm
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("divisions", __name__, url_prefix="/divisions")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    divisions = models.Division.objects(status="active", organization=organization)
    form = forms.divisions.SearchDivisionStartEndDateForm()
    form.name.choices = [("", "ทั้งหมด")] + [
        (str(division.id), f"{division.name}") for division in divisions
    ]

    if form.name.data:
        form.name.data = form.name.data
    else:
        form.name.process(data="", formdata=form.name.choices)
    if not form.validate_on_submit():
        print(form.errors)

    if form.start_date.data == None and form.end_date.data != None:
        divisions = divisions.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        divisions = divisions.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        divisions = divisions.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.name.data:
        divisions = divisions.filter(id=form.name.data)

    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_divisions = Pagination(divisions, page=page, per_page=30)
    return render_template(
        "/organizations/divisions/index.html",
        form=form,
        divisions=divisions,
        paginated_divisions=paginated_divisions,
        organization=organization,
    )


@module.route(
    "/create",
    methods=["GET", "POST"],
    defaults={"division_id": None},
)
@module.route("/<division_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(division_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.divisions.DivisionForm()
    if division_id:
        division = get_division(organization, division_id)
        form = forms.divisions.DivisionForm(obj=division)
    if not form.validate_on_submit():
        return render_template(
            "/organizations/divisions/create_or_edit.html",
            form=form,
            organization=organization,
            division_id=division_id,
        )
    if not division_id:
        division = models.Division(
            created_by=current_user._get_current_object(),
            organization=organization,
        )
    form.populate_obj(division)
    division.last_updated_by = current_user._get_current_object()
    division.save()
    flash(
        f"เพิ่มแผนก {division.name} แล้ว"
        if not division_id
        else f"บันทึกแผนก {division.name} แล้ว",
        "success",
    )
    if not division_id:
        return redirect(
            url_for("organizations.divisions.index", organization_id=organization_id)
        )
    return redirect(division_url(organization, division))


def get_division(organization, division_id):
    try:
        division = models.Division.objects(
            id=division_id, organization=organization, status="active"
        ).first()
    except me.ValidationError:
        division = None
    if not organization or not division:
        abort(404)
    return division


def division_url(organization, division):
    return url_for(
        "organizations.divisions.detail",
        organization_id=organization.id,
        division_id=division.id,
    )


def active_org_users(organization):
    """สมาชิกที่ยังไม่ถูกนำออก (active และรอเข้าสู่ระบบ) ใช้เกณฑ์เดียวกับหน้าภาพรวม"""
    return models.OrganizationUserRole.objects(
        organization=organization, status__ne="disactive"
    )


@module.route("/<division_id>/detail")
@acl.organization_roles_required("admin")
def detail(division_id):
    organization = models.Organization.objects(
        id=request.args.get("organization_id"), status="active"
    ).first()
    division = get_division(organization, division_id)

    org_users = list(active_org_users(organization).order_by("first_name", "last_name"))
    members = [u for u in org_users if u.division and u.division.id == division.id]
    active_division_ids = {
        d.id for d in models.Division.objects(organization=organization, status="active").only("id")
    }
    # คนที่อยู่แผนกอื่นยังเพิ่มได้ แต่ต้องบอกว่าเป็นการย้ายแผนก
    candidates = [
        {
            "org_user": u,
            "current_division": u.division
            if u.division and u.division.id in active_division_ids
            else None,
        }
        for u in org_users
        if not (u.division and u.division.id == division.id)
    ]

    return render_template(
        "/organizations/divisions/detail.html",
        organization=organization,
        division=division,
        members=members,
        pending_count=sum(1 for u in members if u.status == "pending"),
        candidates=candidates,
        action_form=FlaskForm(),
    )


@module.route("/<division_id>/users")
@acl.organization_roles_required("admin")
def users(division_id):
    # รวมเข้าหน้าแผนกแล้ว เก็บ URL เดิมไว้ให้ bookmark ยังใช้ได้
    return redirect(
        url_for(
            "organizations.divisions.detail",
            organization_id=request.args.get("organization_id"),
            division_id=division_id,
        ),
        code=301,
    )


@module.route("/<division_id>/add-member", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_member(division_id):
    organization = models.Organization.objects(
        id=request.args.get("organization_id"), status="active"
    ).first()
    division = get_division(organization, division_id)
    form = forms.divisions.DivisionAddMemberForm()
    if request.method == "GET" or not form.validate_on_submit():
        return redirect(division_url(organization, division))

    org_users = active_org_users(organization).filter(id__in=form.members.data or [])
    added = 0
    moved = []
    for org_user in org_users:
        previous = org_user.division
        if previous and previous.id == division.id:
            continue
        if previous and previous.status == "active":
            moved.append(
                {"label": org_user.display_fullname(), "detail": f"ย้ายมาจาก {previous.name}"}
            )
        org_user.division = division
        org_user.last_modifier = current_user._get_current_object()
        org_user.last_ip_address = request.headers.get(
            "X-Forwarded-For", request.remote_addr
        )
        org_user.save()
        added += 1

    if not added:
        flash(
            f"ไม่มีสมาชิกที่เพิ่มเข้าแผนก {division.name} ได้ "
            "(ยังไม่ได้เลือก หรืออยู่ในแผนกนี้แล้ว)",
            "error",
        )
    else:
        flash(f"เพิ่มสมาชิก {added} คนเข้าแผนก {division.name} แล้ว", "success")
    if moved:
        # ส่งเป็นโครงสร้าง ให้ layout แสดงเป็นรายการทีละคน อ่านง่ายกว่าข้อความยาวบรรทัดเดียว
        flash(
            {
                "title": "ย้ายสมาชิกจากแผนกอื่น",
                "summary": f"สมาชิก {len(moved)} คนถูกย้ายมาอยู่แผนก “{division.name}”",
                "items": moved,
            },
            "warning",
        )
    return redirect(division_url(organization, division))


@module.route(
    "/<division_id>/division_user/<division_user_id>/remove", methods=["POST"]
)
@acl.organization_roles_required("admin")
def remove_division_user(division_id, division_user_id):
    organization = models.Organization.objects(
        id=request.args.get("organization_id"), status="active"
    ).first()
    division = get_division(organization, division_id)
    if not FlaskForm().validate_on_submit():
        abort(400)

    try:
        org_user = active_org_users(organization).filter(
            id=division_user_id, division=division
        ).first()
    except me.ValidationError:
        org_user = None
    if not org_user:
        abort(404)

    org_user.division = None
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    flash(
        f"นำ {org_user.display_fullname()} ออกจากแผนก {division.name} แล้ว", "success"
    )
    return redirect(division_url(organization, division))


@module.route("/<division_id>/delete", methods=["POST"])
@acl.organization_roles_required("admin")
def delete(division_id):
    organization = models.Organization.objects(
        id=request.args.get("organization_id"), status="active"
    ).first()
    division = get_division(organization, division_id)
    if not FlaskForm().validate_on_submit():
        abort(400)

    division.status = "disactive"
    for org_user in active_org_users(organization).filter(division=division):
        org_user.division = None
        org_user.save()
    division.save()

    flash(f"ลบแผนก {division.name} แล้ว", "success")
    return redirect(
        url_for("organizations.divisions.index", organization_id=organization.id)
    )
