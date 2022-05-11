from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("dashboard", __name__, url_prefix="/dashboard")
subviews = []


def index_admin():

    now = datetime.datetime.now()
    return render_template(
        "/dashboard/index-admin.html", now=datetime.datetime.now(), available_classes=[]
    )


def index_user():
    return render_template("/dashboard/index.html")


@module.route("/")
@login_required
def index():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0
    notifications = []
    checkout_trend_month = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    for checkout in checkouts:
        date = checkout.checkout_date
        now = datetime.datetime.now()
        if int(now.strftime("%Y")) - int(date.strftime("%Y")) == 0:
            month = int(date.strftime("%m")) - 1
            checkout_trend_month[month] += checkout.quantity
            total_values += checkout.price

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain

        # If inventory remain is less than 25%
        if inventory.remain / inventory.quantity * 100 < 25:
            notifications.append(inventory)

    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/index.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_month=checkout_trend_month,
        notifications=notifications,
    )
