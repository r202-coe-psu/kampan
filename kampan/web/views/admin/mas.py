from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
)
from flask_login import login_required, current_user
from kampan.web import acl, forms
from kampan import models

import mongoengine as me
import datetime

module = Blueprint("mas", __name__, url_prefix="/mas")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    mas = models.MAS.objects(status="active")
    total_amount = sum(m.amount or 0 for m in mas)
    total_budget = sum(m.budget or 0 for m in mas)
    total_actual = sum(m.actual_cost or 0 for m in mas)
    total_remain = total_budget - total_actual
    return render_template(
        "procurement/mas/index.html",
        organization=organization,
        mas=mas,
        amount=total_amount,
        budget=total_budget,
        actual_cost=total_actual,
        remain=total_remain,
    )


@module.route("/create", methods=["GET", "POST"])
@module.route("/<mas_id>/edit", methods=["GET", "POST"])
@acl.roles_required("admin")
def create_or_edit(mas_id=None):
    organization = current_user.user_setting.current_organization

    mas = models.MAS.objects(id=mas_id).first() if mas_id else None
    form = forms.mas.MASForm(obj=mas)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "procurement/mas/create_or_edit.html",
            form=form,
            organization=organization,
            mas=mas,
        )

    if not mas:
        mas = models.MAS()
        mas.created_by = current_user._get_current_object()

    form.populate_obj(mas)
    mas.last_updated_by = current_user._get_current_object()
    mas.save()

    return redirect(url_for("procurement.mas.index", organization=organization))


@module.route("/<mas_id>/delete", methods=["GET", "POST"])
@acl.roles_required("admin")
def delete(mas_id):
    organization = current_user.user_setting.current_organization
    mas = models.MAS.objects(id=mas_id).first()
    if mas:
        mas.status = "closed"
        mas.save()

    return redirect(url_for("procurement.mas.index", organization=organization))
