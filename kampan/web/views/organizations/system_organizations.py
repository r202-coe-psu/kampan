import datetime

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user
from flask_mongoengine import Pagination

from kampan import models
from kampan.web import acl, forms

module = Blueprint(
    "system_organizations", __name__, url_prefix="/system/organizations"
)


def get_target_organization(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        abort(404)
    return organization


def render_system_page(template, **context):
    # organization ใน template คือหน่วยงานที่ผู้ใช้กำลังดู ใช้ render sidebar
    # หน่วยงานที่กำลังจัดการในหน้านี้ส่งมาเป็น target_organization
    return render_template(
        f"/organizations/system/organizations/{template}",
        organization=current_user.get_viewing_organization(),
        **context,
    )


@module.route("/")
@acl.roles_required("admin")
def index():
    organizations = models.Organization.objects(status="active").order_by("name")
    page = max(request.args.get("page", default=1, type=int), 1)
    return render_system_page(
        "index.html",
        paginated_organizations=Pagination(organizations, page=page, per_page=30),
    )


@module.route("/create", methods=["GET", "POST"], defaults={"organization_id": None})
@module.route("/<organization_id>/edit", methods=["GET", "POST"])
@acl.roles_required("admin")
def create_or_edit(organization_id):
    target_organization = (
        get_target_organization(organization_id)
        if organization_id
        else models.Organization()
    )
    form = forms.organizations.OrganizationForm(obj=target_organization)

    if not form.validate_on_submit():
        return render_system_page(
            "create_or_edit.html",
            form=form,
            target_organization=target_organization if organization_id else None,
        )

    form.populate_obj(target_organization)
    if not organization_id:
        target_organization.created_by = current_user._get_current_object()
    target_organization.last_updated_by = current_user._get_current_object()
    target_organization.save()
    return redirect(url_for("organizations.system_organizations.index"))


@module.route("/<organization_id>/detail")
@acl.roles_required("admin")
def detail(organization_id):
    return render_system_page(
        "detail.html", target_organization=get_target_organization(organization_id)
    )


@module.route("/<organization_id>/add-member", methods=["GET", "POST"])
@acl.roles_required("admin")
def add_member(organization_id):
    target_organization = get_target_organization(organization_id)
    form = forms.organizations.OrganizationAddMemberForm()
    users_in_organization = target_organization.get_distinct_users() or []
    form.members.choices = [
        (str(u.id), u.get_name())
        for u in models.User.objects()
        if u not in users_in_organization
    ]
    form.division.choices = [("", "")] + [
        (str(d.id), d.name)
        for d in models.Division.objects(
            organization=target_organization, status="active"
        )
    ]

    if not form.validate_on_submit():
        return render_system_page(
            "add_member.html", form=form, target_organization=target_organization
        )

    user = models.User.objects(id=form.members.data).first()
    if user:
        user.user_setting.current_organization = target_organization
        user.save()

        org_user = models.OrganizationUserRole(
            organization=target_organization,
            user=user,
            roles=form.roles.data,
            division=(
                models.Division.objects(id=form.division.data, status="active").first()
                if form.division.data
                else None
            ),
            appointment=form.appointment.data,
            added_by=current_user._get_current_object(),
            last_modifier=current_user._get_current_object(),
            last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            created_date=datetime.datetime.now(),
        )
        org_user.save()

    return redirect(
        url_for(
            "organizations.system_organizations.users",
            organization_id=target_organization.id,
        )
    )


@module.route("/<organization_id>/users")
@acl.roles_required("admin")
def users(organization_id):
    target_organization = get_target_organization(organization_id)
    org_users = models.OrganizationUserRole.objects(
        organization=target_organization, status__ne="disactive"
    ).order_by("-first_name")
    page = max(request.args.get("page", default=1, type=int), 1)
    return render_system_page(
        "members.html",
        paginated_org_users=Pagination(org_users, page=page, per_page=30),
        target_organization=target_organization,
    )


@module.route("/<organization_id>/users/<org_user_id>/edit-roles", methods=["GET", "POST"])
@acl.roles_required("admin")
def edit_roles(organization_id, org_user_id):
    target_organization = get_target_organization(organization_id)
    org_user = models.OrganizationUserRole.objects(
        id=org_user_id, organization=target_organization, status="active"
    ).first()
    if not org_user:
        abort(404)
    form = forms.organizations.OrganizationRoleEditForm(obj=org_user)

    if not form.validate_on_submit():
        return render_system_page(
            "edit_roles.html",
            form=form,
            target_organization=target_organization,
            org_user=org_user,
        )

    org_user.roles = form.roles.data
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    return redirect(
        url_for(
            "organizations.system_organizations.users",
            organization_id=target_organization.id,
        )
    )


@module.route("/<organization_id>/users/<org_user_id>/remove", methods=["GET", "POST"])
@acl.roles_required("admin")
def remove_org_user(organization_id, org_user_id):
    target_organization = get_target_organization(organization_id)
    org_user = models.OrganizationUserRole.objects(
        id=org_user_id, organization=target_organization
    ).first()
    if not org_user:
        abort(404)
    org_user.status = "disactive"
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    return redirect(
        url_for(
            "organizations.system_organizations.users",
            organization_id=target_organization.id,
        )
    )


@module.route("/<organization_id>/delete")
@acl.roles_required("admin")
def delete(organization_id):
    target_organization = get_target_organization(organization_id)
    target_organization.status = "disactive"
    target_organization.save()
    return redirect(url_for("organizations.system_organizations.index"))
