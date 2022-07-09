from calendar import calendar
from crypt import methods
from pyexpat import model
from typing import OrderedDict
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime


module = Blueprint("item_checkouts", __name__, url_prefix="/item_checkouts")


def check_in_time(checkout_date,calendar_select):
    print(checkout_date,calendar_select)
    if checkout_date <= calendar_select:
        return True

    else:
        return False


@module.route("/", methods=["GET","POST"])
@login_required
def index():
    checkouts = models.CheckoutItem.objects()

    form = forms.inventories.InventoryForm()

    if request.method == "POST":
        print("\n\n\n\n\n", form.calendar_select.data)

    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts,
        calendar_select=form.calendar_select.data,
        check_in_time = check_in_time,
        form=form,
    )


@module.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    items = models.Item.objects()
    form = forms.item_checkouts.CheckoutItemForm()
    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
        )
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()

    quantity = form.quantity.data
    # This code area have to rewrite for supporting multiple checkin_item, in case of remain less than request
    inventories = models.Inventory.objects(item=form.item.data, remain__gt=0)
    for inventory in inventories:
        checkout = models.CheckoutItem()
        checkout.user = current_user._get_current_object()
        checkout.order = order
        checkout.item = form.item.data
        checkout.checkout_date = form.checkout_date.data
        checkout.checkout_from = inventory
        checkout.warehouse = inventory.warehouse
        checkout.price = inventory.price
        checkout.checkout_date = form.checkout_date.data
        
        if inventory.remain >= quantity:
            inventory.remain -= quantity
            checkout.quantity = quantity
            quantity = 0
        else:
            quantity -= inventory.remain
            checkout.quantity = inventory.remain
            inventory.remain = 0

        if checkout.item.status == "no_approval_required":
            checkout.status = "approved"
            checkout.order.status = "approved"
        else:
            checkout.status = "pending"
            checkout.order.status = "pending"

        order.save()
        inventory.save()
        checkout.save()

        if quantity <= 0:
            break
    
    return redirect(url_for("item_orders.index"))

@module.route("/all-checkout", methods=["GET", "POST"])
@login_required
def bill_checkout():
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order)

    print(checkout)

    return render_template(
        "/item_checkouts/bill-checkout.html",
        checkouts = checkouts,
        order_id=order_id,
    )
