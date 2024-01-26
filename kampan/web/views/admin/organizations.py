from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("organizations", __name__, url_prefix="/organizations")


@module.route("/")
@acl.roles_required("admin")
def index():
    organizations = models.Organization.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    if not form.validate_on_submit():
        print(form.errors)

    if form.start_date.data == None and form.end_date.data != None:
        organizations = organizations.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        organizations = organizations.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        organizations = organizations.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )

    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_organizations = Pagination(organizations, page=page, per_page=30)

    return render_template(
        "/admin/organizations/index.html",
        form=form,
        organizations=organizations,
        paginated_organizations=paginated_organizations,
    )


@module.route(
    "/create",
    methods=["GET", "POST"],
    defaults={"organization_id": None},
)
@module.route("/<organization_id>/edit", methods=["GET", "POST"])
@acl.roles_required("admin")
def craete_or_edit(organization_id):
    organization = models.Organization()
    form = forms.organizations.OrganizationForm()

    if organization_id:
        organization = models.Organization.objects(id=organization_id).first()
        form = forms.organizations.OrganizationForm(obj=organization)
    if not form.validate_on_submit():
        print(form.errors)
        return render_template("/admin/organizations/craete_or_edit.html", form=form)

    form.populate_obj(organization)
    if not organization_id:
        organization.created_by = current_user._get_current_object()
    organization.last_updated_by = current_user._get_current_object()
    organization.save()
    return redirect(url_for("admin.organizations.index"))


@module.route("/<organization_id>/add-member", methods=["GET", "POST"])
@acl.roles_required("admin")
def add_member(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.OrgnaizationAddMemberForm()
    users_in_organization = organization.get_users()
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

    if not form.validate_on_submit():
        print(form.errors)
        return render_template("/admin/organizations/add_member.html", form=form)

    for user_id in form.members.data:
        user = models.User.objects(id=user_id).first()
        if not user.get_current_organization():
            user.user_setting.current_organization = organization
            user.save()

        org_user = models.OrganizationUserRole(
            organization=organization,
            user=user,
            role=form.role.data,
            added_by=current_user._get_current_object(),
            last_modifier=current_user._get_current_object(),
            last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            created_date=datetime.datetime.now(),
        )
        org_user.save()

    return redirect(url_for("admin.organizations.index"))


@module.route("/<organization_id>/users", methods=["GET", "POST"])
@acl.roles_required("admin")
def users(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.inventories.SearchStartEndDateForm()
    users_in_organization = organization.get_users()

    if not form.validate_on_submit():
        print(form.errors)
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_users = Pagination(users_in_organization, page=page, per_page=30)
    return render_template(
        "/admin/organizations/users.html",
        form=form,
        paginated_users=paginated_users,
        organization=organization,
        users_in_organization=users_in_organization,
    )


@module.route("/<organization_id>/delete")
@acl.roles_required("admin")
def delete(organization_id):
    organization = models.Organization.objects().get(id=organization_id)
    organization.status = "disactive"
    organization.save()

    return redirect(url_for("admin.organizations.index"))
