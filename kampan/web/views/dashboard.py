from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime
from calendar import monthrange

module = Blueprint("dashboard", __name__, url_prefix="/dashboard")
subviews = []


def index_admin():

    now = datetime.datetime.now()
    return render_template(
        "/dashboard/index-admin.html", now=datetime.datetime.now(), available_classes=[]
    )


def index_user():
    return render_template(
        "/dashboard/daily_dashboard.html",
        "/dashboard/monthly_dashboard.html",
        "/dashboard/yearly_dashboard.html",
    )


@module.route("/")
@login_required
def daily_dashboard():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0
    notifications = []

    now = datetime.datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%m")
    month_size = monthrange(int(year), int(month))
    checkout_trend_day = [0] * month_size[1]
    number_of_day = []
    for i in range(1, month_size[1] + 1):
        number_of_day.append(i)

    for checkout in checkouts:
        date = checkout.checkout_date
        if int(now.strftime("%m")) - int(date.strftime("%m")) == 0:
            day = int(date.strftime("%d")) - 1
            checkout_trend_day[day] += checkout.quantity
            total_values += checkout.price * checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain

    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/daily_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_day=checkout_trend_day,
        notifications=notifications,
        number_of_day=number_of_day,
    )


@module.route("/monthly")
@login_required
def monthly_dashboard():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0
    checkout_trend_month = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    for checkout in checkouts:
        date = checkout.checkout_date
        month = int(date.strftime("%m")) - 1
        checkout_trend_month[month] += checkout.quantity
        total_values += checkout.price * checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain

    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/monthly_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_month=checkout_trend_month,
    )


@module.route("/yearly")
@login_required
def yearly_dashboard():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0

    checkout_trend_year = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

    for checkout in checkouts:
        date = checkout.checkout_date
        year = int(date.strftime("%m")) - 1
        checkout_trend_year[year] += checkout.quantity
        total_values += checkout.price * checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain

    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/yearly_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_year=checkout_trend_year,
    )
