from flask import Blueprint, flash, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models, utils

module = Blueprint("members", __name__, url_prefix="/<organization_id>/members")


@module.route("/add", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_member(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.OrganizationAddMemberForm()
    users_in_organization = organization.get_distinct_users()
    if users_in_organization:
        form.members.choices = [
            (str(u.id), u.get_name())
            for u in models.User.objects()
            if u not in users_in_organization
        ]
    else:
        form.members.choices = [
            (str(u.id), u.get_name()) for u in models.User.objects()
        ]
    form.division.choices = [
        (str(d.id), d.name)
        for d in models.Division.objects(organization=organization, status="active")
    ]
    if not form.validate_on_submit():
        return render_template(
            "/organizations/add_member.html",
            form=form,
            organization=organization,
        )
    user_id = form.members.data
    user = models.User.objects(id=user_id).first()
    if user and not user.get_default_organization():
        user.user_setting.current_organization = organization
        user.save()

    org_user = models.OrganizationUserRole(
        organization=organization,
        user=user,
        roles=form.roles.data,
        division=models.Division.objects(
            id=form.division.data, status="active"
        ).first(),
        appointment=form.appointment.data,
        added_by=current_user._get_current_object(),
        last_modifier=current_user._get_current_object(),
        last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
        created_date=datetime.datetime.now(),
    )
    org_user.save()

    flash(f"เพิ่มสมาชิก {org_user.display_fullname()} แล้ว", "success")
    return redirect(
        url_for(
            "organizations.members.index",
            organization_id=organization_id,
        )
    )


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.OrganizationMemberSearchForm()
    divisions = list(
        models.Division.objects(organization=organization, status="active").order_by(
            "name"
        )
    )
    form.set_division_choices(divisions)
    org_users = organization.get_organization_users()
    if org_users:
        form.user.choices = [("", "")] + [
            (str(u.id), f"{u.display_fullname()}") for u in org_users
        ]
    if form.user.data:
        form.user.data = form.user.data
    else:
        form.user.process(data="", formdata=form.user.choices)

    if not form.validate_on_submit():
        start_date = request.args.get("start_date", default="")
        end_date = request.args.get("end_date", default="")
        user = request.args.get("user", default="")
        role = request.args.get("role", default="")
        division = request.args.get("division", default="")
        if division:
            form.division.data = division
        if role:
            form.role.data = role
        if user:
            form.user.data = user
        if start_date:
            start_date = datetime.datetime.strptime(
                start_date,
                "%Y-%m-%d",
            )
            form.start_date.data = start_date
        if end_date:
            end_date = datetime.datetime.strptime(
                end_date,
                "%Y-%m-%d",
            )
            form.end_date.data = end_date

        if form.start_date.data == None and form.end_date.data != None:
            org_users = org_users.filter(
                created_date__lt=form.end_date.data,
            )

        elif form.start_date.data and form.end_date.data == None:
            org_users = org_users.filter(
                created_date__gte=form.start_date.data,
            )

        elif form.start_date.data != None and form.end_date.data != None:
            org_users = org_users.filter(
                created_date__gte=form.start_date.data,
                created_date__lt=form.end_date.data,
            )
        if form.role.data:
            org_users = org_users.filter(roles=form.role.data)
        if form.user.data:
            org_users = org_users.filter(id=form.user.data)
        if form.division.data == forms.organizations.UNASSIGNED_DIVISION:
            # แผนกที่ถูกลบไปแล้วนับเป็นยังไม่ได้ระบุแผนก ให้ตรงกับหน้าภาพรวม
            org_users = org_users.filter(division__nin=divisions)
        elif form.division.data:
            division = next(
                (d for d in divisions if str(d.id) == form.division.data), None
            )
            org_users = org_users.filter(division=division) if division else org_users.none()
        page = request.args.get("page", default=1, type=int)
        if form.start_date.data or form.end_date.data:
            page = 1
        paginated_org_users = None
        if org_users:
            paginated_org_users = Pagination(org_users, page=page, per_page=30)
        return render_template(
            "/organizations/members.html",
            form=form,
            paginated_org_users=paginated_org_users,
            organization=organization,
            org_users=org_users,
        )
    return redirect(
        url_for(
            "organizations.members.index",
            organization_id=organization.id,
            role=form.role.data,
            user=form.user.data,
            division=form.division.data,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
        )
    )


@module.route(
    "/<org_user_id>/edit_roles",
    methods=["GET", "POST"],
)
@acl.organization_roles_required("admin")
def edit_roles(organization_id, org_user_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    org_user = models.OrganizationUserRole.objects(
        id=org_user_id, status="active"
    ).first()

    if org_user and org_user.user:
        if not org_user.first_name:
            org_user.first_name = org_user.user.first_name
        if not org_user.last_name:
            org_user.last_name = org_user.user.last_name
        if not org_user.email:
            org_user.email = org_user.user.email

    form = forms.organizations.OrganizationRoleEditForm(obj=org_user)

    if not form.validate_on_submit():
        return render_template(
            "/organizations/edit_roles.html",
            form=form,
            organization=organization,
            org_user=org_user,
        )
    org_user.first_name = form.first_name.data
    org_user.last_name = form.last_name.data
    org_user.email = form.email.data
    org_user.appointment = form.appointment.data
    org_user.roles = form.roles.data
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    flash(f"บันทึกตำแหน่งของ {org_user.display_fullname()} แล้ว", "success")
    return redirect(
        url_for(
            "organizations.members.index",
            organization_id=organization_id,
        )
    )


@module.route("/<org_user_id>/remove", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def remove_org_user(organization_id, org_user_id):
    org_user = models.OrganizationUserRole.objects(id=org_user_id).first()
    org_user.status = "disactive"
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    flash(f"นำ {org_user.display_fullname()} ออกจากองค์กรแล้ว", "success")
    return redirect(
        url_for(
            "organizations.members.index",
            organization_id=organization_id,
        )
    )


@module.route("/upload", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "staff")
def upload_member_file(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.items.UploadFileForm()
    errors = request.args.getlist("errors")

    if not form.validate_on_submit():
        return render_template(
            "/organizations/upload_member_file.html",
            organization=organization,
            errors=errors,
            form=form,
        )

    if form.upload_file.data:
        errors = utils.organizations.validate_member_upload_engagement(
            form.upload_file.data, organization
        )
        if not errors:
            completed = utils.organizations.process_member_upload_file(
                form.upload_file.data, organization, current_user
            )
        else:
            return render_template(
                "/organizations/upload_member_file.html",
                organization=organization,
                errors=errors,
                form=form,
            )
    else:
        return redirect(
            url_for(
                "organizations.members.upload_member_file",
                organization_id=organization_id,
                errors=["ไม่พบไฟล์"],
            )
        )
    flash("นำเข้าสมาชิกจากไฟล์แล้ว", "success")
    return redirect(
        url_for(
            "organizations.members.index",
            organization_id=organization_id,
        )
    )


@module.route("/upload/template", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "staff")
def download_template_member_file(organization_id):
    return utils.organizations.get_template_delete_items_file()
