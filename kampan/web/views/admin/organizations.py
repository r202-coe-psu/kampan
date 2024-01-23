from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination

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


@module.route("/<organization_id>/delete")
@acl.roles_required("admin")
def delete(organization_id):
    organization = models.Organization.objects().get(id=organization_id)
    organization.status = "disactive"
    organization.save()

    return redirect(url_for("admin.organizations.index"))
