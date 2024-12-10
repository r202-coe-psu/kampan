from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
import mongoengine as me
from flask_mongoengine import Pagination

import datetime

module = Blueprint("warehouses", __name__, url_prefix="/warehouses")


@module.route("/")
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    warehouses = models.Warehouse.objects(
        status="active", organization=organization
    ).order_by("-created_date")
    page = request.args.get("page", default=1, type=int)
    paginated_warehouses = Pagination(warehouses, page=page, per_page=30)
    return render_template(
        "/warehouses/index.html",
        paginated_warehouses=paginated_warehouses,
        warehouses=warehouses,
        organization=organization,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(warehouse_id=None))
@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def add_or_edit(warehouse_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.warehouses.WarehouseForm()

    if warehouse_id:
        warehouse = models.Warehouse.objects().get(id=warehouse_id)
        form = forms.warehouses.WarehouseForm(obj=warehouse)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/warehouses/add-edit.html",
            form=form,
            organization=organization,
        )

    if not warehouse_id:
        warehouse = models.Warehouse()

    form.populate_obj(warehouse)
    if not warehouse_id:
        warehouse.created_by = current_user._get_current_object()
    warehouse.name = str(form.name).strip()
    warehouse.organization = organization
    warehouse.last_updated_by = current_user._get_current_object()

    warehouse.save()

    return redirect(
        url_for(
            "warehouses.index",
            organization_id=organization_id,
        )
    )


@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(warehouse_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    warehouse = models.Warehouse.objects().get(id=warehouse_id)
    form = forms.warehouses.WarehouseForm(obj=warehouse)

    if not form.validate_on_submit():
        return render_template(
            "/warehouses/add-edit.html",
            form=form,
            organization=organization,
        )

    form.populate_obj(warehouse)
    warehouse.save()

    return redirect(
        url_for(
            "warehouses.index",
            organization_id=organization_id,
        )
    )


@module.route("/<warehouse_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(warehouse_id):
    organization_id = request.args.get("organization_id")

    warehouse = models.Warehouse.objects().get(id=warehouse_id)
    warehouse.status = "disactive"
    warehouse.save()

    return redirect(
        url_for(
            "warehouses.index",
            organization_id=organization_id,
        )
    )
