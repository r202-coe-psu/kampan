from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me
from flask_mongoengine import Pagination

import datetime

module = Blueprint("suppliers", __name__, url_prefix="/suppliers")


@module.route("/")
@login_required
def index():
    suppliers = models.Supplier.objects(status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_suppliers = Pagination(suppliers, page=page, per_page=30)
    return render_template(
        "/suppliers/index.html",
        suppliers=suppliers,
        paginated_suppliers=paginated_suppliers,
    )


@module.route("/add", methods=["GET", "POST"])
@login_required
def add():
    supplier = models.Supplier()
    form = forms.suppliers.SupplierForm()
    if not form.validate_on_submit():
        return render_template(
            "/suppliers/add.html",
            form=form,
        )

    form.populate_obj(supplier)
    supplier.save()

    return redirect(url_for("suppliers.index"))


@module.route("/<supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit(supplier_id):
    supplier = models.Supplier.objects().get(id=supplier_id)
    form = forms.suppliers.SupplierForm(obj=supplier)

    if not form.validate_on_submit():
        return render_template(
            "/suppliers/add.html",
            form=form,
        )

    form.populate_obj(supplier)
    supplier.save()

    return redirect(url_for("suppliers.index"))


@module.route("/<supplier_id>/delete")
@login_required
def delete(supplier_id):
    supplier = models.Supplier.objects().get(id=supplier_id)
    supplier.status = "disactive"
    supplier.save()

    return redirect(url_for("suppliers.index"))
