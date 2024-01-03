from calendar import calendar
from crypt import methods
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms
from kampan import models
import mongoengine as me

module = Blueprint("lost_breaks", __name__, url_prefix="/lost_breaks")


@module.route("/", methods=["GET", "POST"])
@login_required
def index():
    lost_break_items = models.LostBreakItem.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        lost_break_items = lost_break_items.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        lost_break_items = lost_break_items.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        lost_break_items = lost_break_items.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1
    paginated_lost_break_items = Pagination(lost_break_items, page=page, per_page=30)

    return render_template(
        "/lost_breaks/index.html",
        paginated_lost_break_items=paginated_lost_break_items,
        lost_break_items=lost_break_items,
        form=form,
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
    if lost_break_item.quantity != 0:
        return_inventory = models.Inventory.objects(
            id=lost_break_item.lost_from.id
        ).first()
        return_inventory.remain += lost_break_item.quantity
        return_inventory.save()

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
    if lost_break_item.quantity != 0:
        return_inventory = models.Inventory.objects(
            id=lost_break_item.lost_from.id
        ).first()
        return_inventory.remain += lost_break_item.quantity
        return_inventory.save()
    lost_break_item.status = "disactive"
    lost_break_item.save()

    return redirect(url_for("lost_breaks.index"))
