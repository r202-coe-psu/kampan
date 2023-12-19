from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("item_positions", __name__, url_prefix="/item-positions")


@module.route("/")
@login_required
def index():
    item_positions = models.ItemPosition.objects()
    return render_template(
        "/item_positions/index.html",
        item_positions=item_positions,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(item_position_id=None))
@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@login_required
def add_or_edit(item_position_id):
    form = forms.item_positions.ItemPositionForm()

    item_position = None
    if item_position_id:
        item_position = models.ItemPosition.objects().get(id=item_position_id)
        form = forms.item_positions.ItemPositionForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/item_positions/add-edit.html",
            form=form,
        )

    if not item_position:
        item_position = models.ItemPosition()

    form.populate_obj(item_position)
    item_position.user = current_user._get_current_object()

    item_position.save()

    return redirect(url_for("item_positions.index"))


@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@login_required
def edit(item_position_id):
    item_position = models.Warehouse.objects().get(id=item_position_id)
    form = forms.item_positions.WarehouseForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/item_positions/add-edit.html",
            form=form,
        )

    form.populate_obj(item_position)
    item_position.save()

    return redirect(url_for("item_positions.index"))


@module.route("/<item_position_id>/delete")
@login_required
def delete(item_position_id):
    item_position = models.ItemPosition.objects().get(id=item_position_id)
    item_position.status = "disactive"
    item_position.save()

    return redirect(url_for("item_positions.index"))
