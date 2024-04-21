from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("organizations", __name__, url_prefix="/organizations")


@module.route("/<organization_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def edit(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.OrganizationForm(obj=organization)
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/organizations/create_or_edit.html",
            form=form,
            organization=organization,
        )

    form.populate_obj(organization)
    organization.last_updated_by = current_user._get_current_object()
    organization.save()
    return redirect(
        url_for(
            "organizations.detail",
            organization_id=organization_id,
        )
    )


@module.route("/<organization_id>/detail")
@acl.organization_roles_required("admin")
def detail(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    return render_template(
        "/organizations/detail.html",
        organization=organization,
    )


@module.route("/<organization_id>/add-member", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_member(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.OrgnaizationAddMemberForm()
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

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/organizations/add_member.html",
            form=form,
            organization=organization,
        )

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

    return redirect(
        url_for(
            "organizations.index",
            organization_id=organization_id,
        )
    )


@module.route("/<organization_id>/organizaiton_users", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def organizaiton_users(organization_id):
    organization = models.Organization.objects(id=organization_id).first()
    form = forms.organizations.SearchUserForm()
    org_users = organization.get_organization_users()
    if org_users:
        [
            form.user.choices.append((org_user.id, f"{org_user.user.get_name()}"))
            for org_user in org_users
        ]
    if form.user.data:
        form.user.data = form.user.data
    else:
        form.user.process(data="", formdata=form.user.choices)

    if not form.validate_on_submit():
        print(form.errors)

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
        org_users = org_users.filter(role=form.role.data)
    if form.user.data:
        org_users = org_users.filter(id=form.user.data)
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


@module.route(
    "/<organization_id>/organizaiton_users/<org_user_id>/edit_roles",
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
    form = forms.organizations.OrganizationRoleSelectionForm(obj=org_user)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/organizations/edit_roles.html",
            form=form,
            organization=organization,
            org_user=org_user,
        )

    org_user.role = form.role.data
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    return redirect(
        url_for(
            "organizations.organizaiton_users",
            organization_id=organization_id,
        )
    )


@module.route(
    "/<organization_id>/organizaiton_user/<org_user_id>/remove", methods=["GET", "POST"]
)
@acl.organization_roles_required("admin")
def remove_org_user(organization_id, org_user_id):
    org_user = models.OrganizationUserRole.objects(id=org_user_id).first()
    org_user.status = "disactive"
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    return redirect(
        url_for(
            "organizations.organizaiton_users",
            organization_id=organization_id,
        )
    )


@module.route("/<organization_id>/email_templates", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "staff")
def view_email_templates(organization_id):
    organization = models.Organization.objects.get(id=organization_id)
    form = forms.email_templates.EmailTemplateFileForm()

    query_default = request.args.get("is_default")
    email_templates = models.EmailTemplate.objects(organization=organization)

    return render_template(
        "/email_templates/index.html",
        organization=organization,
        email_templates=email_templates,
        form=form,
        default=query_default,
    )
