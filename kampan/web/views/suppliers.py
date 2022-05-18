from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("suppliers", __name__, url_prefix="/suppliers")


@module.route("/")
@login_required
def index():
    suppliers = models.Supplier.objects()
    return render_template("/suppliers/index.html", suppliers=suppliers)


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
    supplier.delete()

    return redirect(url_for("suppliers.index"))