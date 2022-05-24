from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

module = Blueprint("lost_breaks", __name__, url_prefix="/lost_breaks")


@module.route("/")
@login_required
def index():
    lost_break_items = models.LostBreakItem.objects()
    return render_template(
        "/lost_breaks/index.html",
        lost_break_items=lost_break_items,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(lost_break_item_id=None))
@login_required
def add(lost_break_item_id):
    form = forms.lost_break.ItemLostBreakForm()

    if not form.validate_on_submit():
        return render_template(
            "/lost_breaks/add.html",
            form=form,
        )

    quantity = form.quantity.data
    inventories = models.Inventory.objects(item=form.item.data, remain__gt=0)
    for inventory in inventories:
        lost_break_item = models.LostBreakItem()
        lost_break_item.user = current_user._get_current_object()
        lost_break_item.item = form.item.data
        lost_break_item.lost_from = inventory
        lost_break_item.warehouse = inventory.warehouse
        lost_break_item.description = form.description.data
        
        if inventory.remain >= quantity:
            inventory.remain -= quantity
            lost_break_item.quantity = quantity
            quantity = 0
        else:
            quantity -= inventory.remain
            lost_break_item.quantity = inventory.remain
            inventory.remain = 0

        inventory.save()
        lost_break_item.save()

        if quantity <= 0:
            break

    return redirect(url_for("lost_breaks.index"))

@module.route("/<lost_break_item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(lost_break_item_id):
    lost_break_item = models.LostBreakItem.objects().get(id=lost_break_item_id)
    form = forms.lost_break.ItemLostBreakForm(obj=lost_break_item)

    if not form.validate_on_submit():
        return render_template(
            "/lost_breaks/add.html",
            form=form,
        )

    quantity = form.quantity.data
    inventories = models.Inventory.objects(item=form.item.data, remain__gt=0)
    for inventory in inventories:
        lost_break_item.user = current_user._get_current_object()
        lost_break_item.item = form.item.data
        lost_break_item.lost_from = inventory
        lost_break_item.warehouse = inventory.warehouse
        lost_break_item.description = form.description.data
        
        if inventory.remain >= quantity:
            inventory.remain -= quantity
            lost_break_item.quantity = quantity
            quantity = 0
        else:
            quantity -= inventory.remain
            lost_break_item.quantity = inventory.remain
            inventory.remain = 0

        inventory.save()
        lost_break_item.save()

        if quantity <= 0:
            break

    return redirect(url_for("lost_breaks.index"))

@module.route("/<lost_break_item_id>/delete")
@login_required
def delete(lost_break_item_id):
    lost_break_item = models.LostBreakItem.objects().get(id=lost_break_item_id)
    lost_break_item.delete()

    return redirect(url_for("lost_breaks.index"))