from flask import Blueprint, render_template, redirect, url_for, request
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
    divisions = models.Division.objects(status="active")
    form = forms.divisions.SearchDivisionStartEndDateForm()
    [
        form.name.choices.append((division.id, f"{division.name}"))
        for division in divisions
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
        "/divisions/index.html",
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
        division = models.Division.objects(id=division_id, status="active").first()
        form = forms.divisions.DivisionForm(obj=division)
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/divisions/create_or_edit.html",
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
    if not division_id:
        return redirect(
            url_for(
                "divisions.index",
                organization_id=organization_id,
            )
        )
    else:
        return redirect(
            url_for(
                "divisions.detail",
                organization_id=organization_id,
                division_id=division_id,
            )
        )


@module.route("/<division_id>/detail")
@acl.organization_roles_required("admin")
def detail(division_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    division = models.Division.objects(
        id=division_id,
        status="active",
        organization=organization.id,
    ).first()
    return render_template(
        "/divisions/detail.html",
        organization=organization,
        division=division,
    )


@module.route("/<division_id>/add-member", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_member(division_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    division = models.Division.objects(id=division_id, status="active").first()
    form = forms.divisions.DivisionAddMemberForm()
    users_in_organization = organization.get_distinct_users()
    users_in_division = division.get_distinct_users()
    if users_in_organization:
        form.members.choices = [
            (str(u.id), u.get_name())
            for u in users_in_organization
            if u not in users_in_division
        ]
    else:
        form.members.choices = [
            (str(u.id), u.get_name()) for u in users_in_organization
        ]

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/divisions/add_member.html",
            form=form,
            organization=organization,
            division=division,
        )

    for user_id in form.members.data:
        user = models.User.objects(id=user_id)
        org_user = models.OrganizationUserRole.objects(
            user=user_id,
            status="active",
        ).first()
        org_user.division = division
        org_user.last_modifier = current_user._get_current_object()
        org_user.last_ip_address = request.headers.get(
            "X-Forwarded-For",
            request.remote_addr,
        )
        org_user.save()

    return redirect(
        url_for(
            "divisions.users",
            organization_id=organization_id,
            division_id=division.id,
        )
    )


@module.route("/<division_id>/users", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def users(division_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    division = models.Division.objects(id=division_id, status="active").first()
    form = forms.organizations.SearchUserForm()
    division_users = division.get_division_users()
    [
        form.user.choices.append((division_user.id, f"{division_user.user.get_name()}"))
        for division_user in division_users
    ]
    if form.user.data:
        form.user.data = form.user.data
    else:
        form.user.process(
            data="",
            formdata=form.user.choices,
        )

    if not form.validate_on_submit():
        print(form.errors)

    if form.start_date.data == None and form.end_date.data != None:
        division_users = division_users.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        division_users = division_users.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        division_users = division_users.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.role.data:
        division_users = division_users.filter(role=form.role.data)
    if form.user.data:
        division_users = division_users.filter(id=form.user.data)
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_division_users = Pagination(division_users, page=page, per_page=30)

    return render_template(
        "/divisions/members.html",
        form=form,
        paginated_division_users=paginated_division_users,
        organization=organization,
        division=division,
    )


@module.route(
    "/<division_id>/division_user/<division_user_id>/remove",
    methods=["GET", "POST"],
)
@acl.organization_roles_required("admin")
def remove_division_user(division_id, division_user_id):
    organization_id = request.args.get("organization_id")

    org_user = models.OrganizationUserRole.objects(
        id=division_user_id,
        status="active",
    ).first()
    org_user.division = None
    org_user.last_modifier = current_user._get_current_object()
    org_user.last_ip_address = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    org_user.save()
    return redirect(
        url_for(
            "divisions.users",
            organization_id=organization_id,
            division_id=division_id,
        )
    )
