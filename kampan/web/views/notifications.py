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
    inventories = models.Inventory.objects(status="active")
    checkouts = models.CheckoutItem.objects(status="active")

    notifications = []

    items = models.Item.objects(status="active")
    for item in items:
        if item.minimum > item.get_items_quantity():
            notifications.append(item)
    # pipeline = [
    #     {"$match": {"status": "active"}},
    #     {"$group": {"_id": "$item", "total": {"$sum": "$remain"}}},
    # ]
    # inventories = models.Inventory.objects().aggregate(pipeline)
    # for inventory in inventories:
    #     print(inventory["_id"])
    # total_values = 0
    # checkout_trend_month = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    # for checkout in checkouts:
    #     date = checkout.checkout_date
    #     now = datetime.datetime.now()
    #     if int(now.strftime("%Y")) - int(date.strftime("%Y")) == 0:
    #         month = int(date.strftime("%m")) - 1
    #         checkout_trend_month[month] += checkout.quantity
    #         total_values += checkout.price

    # for inventory in inventories:
    #     # If inventory remain is less than 25%
    #     if inventory.item.minimum:
    #         if inventory.remain <= inventory.item.minimum:
    #             if inventory.notification_status == True:
    #                 notifications.append(inventory)

    # print(notifications)
    return render_template(
        "/notifications/index.html",
        notifications=notifications,
    )


@module.route("/<item_id>/set_status")
def set_status(item_id):
    item = models.Item.objects(id=item_id).first()
    item.notification_status = False
    item.save()

    return redirect(url_for("notifications.index"))
