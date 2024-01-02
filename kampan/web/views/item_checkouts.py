from atexit import register
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


@module.route("/", methods=["GET", "POST"])
@login_required
def index():
    checkouts = models.CheckoutItem.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            checkout_date__lte=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            checkout_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            checkout_date__gte=form.start_date.data,
            checkout_date__lte=form.end_date.data,
        )

    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts,
        form=form,
    )


@module.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    # items = models.Item.objects()
    form = forms.item_checkouts.CheckoutItemForm()
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()

    items = models.Item.objects()
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())
        # print(item_register.get_item_in_bill())

    if items:
        form.item.choices = [
            (item, f"{item.barcode_id} ({item.name})") for item in items
        ]
    if not form.validate_on_submit():
        print(form.errors)

        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
        )
    checkout_item = models.CheckoutItem()
    checkout_item.user = current_user._get_current_object()
    checkout_item.order = order
    checkout_item.item = form.item.data
    checkout_item.checkout_date = form.checkout_date.data
    checkout_item.quantity = form.quantity.data
    checkout_item.save()
    # quantity = form.quantity.data
    # # This code area have to rewrite for supporting multiple checkin_item, in case of remain less than request
    # inventories = models.Inventory.objects(
    #     item=form.item.data, remain__gt=0, status="active"
    # )
    # for inventory in inventories:
    #     checkout = models.CheckoutItem()
    #     checkout.user = current_user._get_current_object()
    #     checkout.order = order
    #     checkout.item = form.item.data
    #     checkout.checkout_date = form.checkout_date.data
    #     checkout.checkout_from = inventory
    #     checkout.warehouse = inventory.warehouse
    #     checkout.price = inventory.price
    #     checkout.checkout_date = form.checkout_date.data
    #     if inventory.remain >= quantity:
    #         inventory.remain -= quantity
    #         checkout.quantity = quantity
    #         quantity = 0
    #     else:
    #         quantity -= inventory.remain
    #         checkout.quantity = inventory.remain
    #         inventory.remain = 0

    #     order.save()
    #     inventory.save()
    #     checkout.save()

    #     if quantity <= 0:
    #         break
    print(form.errors)
    return redirect(url_for("item_orders.index"))


@module.route("/all-checkout", methods=["GET", "POST"])
@login_required
def bill_checkout():
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")

    # print(checkout)

    return render_template(
        "/item_checkouts/bill-checkout.html",
        checkouts=checkouts,
        order_id=order_id,
    )


@module.route("/checkout/<checkout_item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(checkout_item_id):
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    order = models.OrderItem.objects(id=checkout_item.order.id).first()

    form = forms.item_checkouts.CheckoutItemForm(obj=checkout_item)
    items = models.Item.objects()
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())
        items = list(items)
        if checkout_item.item:
            items.append(models.Item.objects(id=checkout_item.item.id).first())
            # print(items)
    if items:
        form.item.choices = [
            (item.id, f"{item.barcode_id} ({item.name})") for item in items
        ]
        form.item.process(data=checkout_item.item.id, formdata=form.item.choices)
    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item.user = current_user._get_current_object()
    checkout_item.item = item
    checkout_item.checkout_date = form.checkout_date.data
    checkout_item.quantity = form.quantity.data
    checkout_item.save()
    return redirect(
        url_for("item_checkouts.bill_checkout", order_id=checkout_item.order.id)
    )


@module.route("/checkout/<checkout_item_id>/delete", methods=["GET", "POST"])
@login_required
def delete(checkout_item_id):
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    checkout_item.status = "disactive"
    checkout_item.save()
    return redirect(
        url_for("item_checkouts.bill_checkout", order_id=checkout_item.order.id)
    )
