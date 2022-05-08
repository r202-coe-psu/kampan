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

    item_quantity = 0
    item_remain = 0
    notifications = []

    checkout_dates = []

    checkout_trend_month = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    for checkout in checkouts:
        date = checkout.checkout_date
        month = int(date.strftime("%m")) - 1
        checkout_trend_month[month] += checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain

        # If inventory remain is less than 25%
        if inventory.remain / inventory.quantity * 100 < 25:
            notifications.append(inventory)

    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/index.html",
        item_quantity=item_quantity,
        item_remain=item_remain,
        notifications=notifications,
        checkout_trend_month=checkout_trend_month,
    )
