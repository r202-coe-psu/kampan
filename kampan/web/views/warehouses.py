from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("warehouses", __name__, url_prefix="/warehouses")


@module.route("/")
@login_required
def index():
    warehouses = models.Warehouse.objects()
    return render_template(
        "/warehouses/index.html",
        warehouses=warehouses,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(warehouse_id=None))
@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@login_required
def add_or_edit(warehouse_id):
    form = forms.warehouses.WarehouseForm()

    warehouse = None
    if warehouse_id:
        warehouse = models.Warehouse.objects().get(id=warehouse_id)
        form = forms.warehouses.WarehouseForm(obj=warehouse)

    if not form.validate_on_submit():
        return render_template(
            "/warehouses/add-edit.html",
            form=form,
        )

    if not warehouse:
        warehouse = models.Warehouse()

    form.populate_obj(warehouse)
    warehouse.user = current_user._get_current_object()

    warehouse.save()

    return redirect(url_for("warehouses.index"))


@module.route("/<warehouse_id>/edit", methods=["GET", "POST"])
@login_required
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

    return redirect(url_for("warehouses.index"))


@module.route("/<warehouse_id>/delete")
@login_required
def delete(warehouse_id):
    warehouse = models.Warehouse.objects().get(id=warehouse_id)
    warehouse.delete()

    return redirect(url_for("warehouses.index"))
