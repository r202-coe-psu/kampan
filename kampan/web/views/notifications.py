from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("notifications", __name__, url_prefix="/notifications")
subviews = []


@module.route("/")
@login_required
def index():
    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

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
        # If inventory remain is less than 25%
        if inventory.item.minimum:
            if inventory.remain < inventory.item.minimum:
                notifications.append(inventory)

        if inventory.remain / inventory.quantity * 100 < 25:
            notifications.append(inventory)

    return render_template(
        "/notifications/index.html",
        notifications=notifications,
    )
