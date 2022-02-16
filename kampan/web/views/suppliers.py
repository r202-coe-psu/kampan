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
    form = forms.suppliers.SupplierForm()
    if not form.validate_on_submit():
        return render_template(
            "/suppliers/add.html",
            form=form,
        )

    supply = models.Supplier(
        name=form.name.data,
        address=form.address.data,
        description=form.description.data,
        tax_id=form.tax_id.data,
        contact=form.contact.data,
        email=form.contact.data,
    )

    supply.save()

    return redirect(url_for("suppliers.index"))
