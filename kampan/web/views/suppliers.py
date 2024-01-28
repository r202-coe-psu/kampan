from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
import mongoengine as me
from flask_mongoengine import Pagination

import datetime

module = Blueprint("suppliers", __name__, url_prefix="/suppliers")


@module.route("/")
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    suppliers = models.Supplier.objects(status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_suppliers = Pagination(suppliers, page=page, per_page=30)
    return render_template(
        "/suppliers/index.html",
        suppliers=suppliers,
        paginated_suppliers=paginated_suppliers,
        organization=organization,
    )


@module.route("/add", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def add():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    supplier = models.Supplier()
    form = forms.suppliers.SupplierForm()
    if not form.validate_on_submit():
        return render_template(
            "/suppliers/add.html",
            form=form,
            organization=organization,
        )

    form.populate_obj(supplier)
    supplier.save()

    return redirect(
        url_for(
            "suppliers.index",
            organization_id=organization_id,
        )
    )


@module.route("/<supplier_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(supplier_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    supplier = models.Supplier.objects().get(id=supplier_id)
    form = forms.suppliers.SupplierForm(obj=supplier)

    if not form.validate_on_submit():
        return render_template(
            "/suppliers/add.html",
            form=form,
            organization=organization,
        )

    form.populate_obj(supplier)
    supplier.save()

    return redirect(
        url_for(
            "suppliers.index",
            organization_id=organization_id,
        )
    )


@module.route("/<supplier_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(supplier_id):
    organization_id = request.args.get("organization_id")

    supplier = models.Supplier.objects().get(id=supplier_id)
    supplier.status = "disactive"
    supplier.save()

    return redirect(url_for("suppliers.index", organization_id=organization_id))
