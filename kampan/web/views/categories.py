from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
from calendar import monthrange
import datetime
from flask_mongoengine import Pagination

module = Blueprint("categories", __name__, url_prefix="/categories")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects.get(id=organization_id)
    categories = models.Category.objects(organization=organization, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_categories = Pagination(categories, page=page, per_page=30)
    return render_template(
        "/categories/index.html",
        paginated_categories=paginated_categories,
        organization=organization,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"category_id": None})
@module.route("/<category_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(category_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects.get(id=organization_id)

    category = None
    form = forms.categories.CategoryForm()
    if category_id:
        category = models.Category.objects(id=category_id).first()
    if not form.validate_on_submit():
        if category:
            form.name.data = category.name
            form.description.data = category.description
        print(form.errors)
        return render_template(
            "/categories/create_or_edit.html",
            form=form,
            organization=organization,
        )
    if not category_id:
        category = models.Category()
        category.created_by = current_user
    form.populate_obj(category)
    category.last_updated_by = current_user
    category.organization = organization
    category.save()
    return redirect(url_for("categories.index", organization_id=organization_id))


@module.route("/<category_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def delete(category_id):
    organization_id = request.args.get("organization_id")
    category = models.Category.objects(id=category_id).first()
    if category:
        category.status = "disactive"
        category.save()

    return redirect(url_for("categories.index", organization_id=organization_id))
