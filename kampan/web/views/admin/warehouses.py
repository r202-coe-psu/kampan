from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination

from kampan.web import forms, acl
from kampan import models

module = Blueprint("warehouses", __name__, url_prefix="/warehouses")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    warehouses = models.Warehouse.objects(status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_warehouses = Pagination(warehouses, page=page, per_page=30)
    return render_template(
        "/admin/warehouses/index.html",
        paginated_warehouses=paginated_warehouses,
        warehouses=warehouses,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(warehouse_id=None))
@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def add_or_edit(warehouse_id):
    form = forms.warehouses.WarehouseForm()

    warehouse = None
    if warehouse_id:
        warehouse = models.Warehouse.objects().get(id=warehouse_id)
        form = forms.warehouses.WarehouseForm(obj=warehouse)

    if not form.validate_on_submit():
        return render_template(
            "/admin/warehouses/add-edit.html",
            form=form,
        )

    if not warehouse:
        warehouse = models.Warehouse()

    form.populate_obj(warehouse)
    warehouse.user = current_user._get_current_object()

    warehouse.save()

    return redirect(url_for("admin.warehouses.index"))


@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def edit(warehouse_id):
    warehouse = models.Warehouse.objects().get(id=warehouse_id)
    form = forms.warehouses.WarehouseForm(obj=warehouse)

    if not form.validate_on_submit():
        return render_template(
            "/warehouses/add-edit.html",
            form=form,
        )

    form.populate_obj(warehouse)
    warehouse.save()

    return redirect(url_for("admin.warehouses.index"))


@module.route("/<warehouse_id>/delete")
@login_required
@acl.roles_required("admin")
def delete(warehouse_id):
    warehouse = models.Warehouse.objects().get(id=warehouse_id)
    warehouse.status = "disactive"
    warehouse.save()

    return redirect(url_for("admin.warehouses.index"))
