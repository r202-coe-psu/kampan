from flask import Flask, Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import numpy as np

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


@module.route("/", methods=["GET", "POST"])
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
    date_now = now.strftime("%d %B, %Y")
    month_now = int(now.strftime("%m"))
    year_now = int(now.strftime("%Y"))
    entire_checkout = []
    number_of_day = []

    for month in range(1, 13):
        month_size = monthrange(year_now, month)
        entire_checkout.append([0] * month_size[1])

        day_in_month = [0] * month_size[1]
        for d in range(1, month_size[1] + 1):
            day_in_month[d - 1] = d
        number_of_day.append(day_in_month)

    for checkout in checkouts:
        date = checkout.checkout_date
        day_co = int(date.strftime("%d")) - 1
        month_co = int(date.strftime("%m")) - 1
        year_co = int(date.strftime("%Y")) - 1

        entire_checkout[month_co][day_co] += checkout.quantity
        total_values += checkout.price * checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain

    select_month = int(request.form.get("month", month_now - 1))
    eng_month = [
        "January",
        "Febuary",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    if "admin" in user.roles:
        return index_admin()
        
    return render_template(
        "/dashboard/daily_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        notifications=notifications,
        number_of_day=number_of_day,
        entire_checkout=entire_checkout,
        select_month=select_month,
        eng_month=eng_month,
        date_now=date_now,
    )


@module.route("/monthly", methods=["GET", "POST"])
@login_required
def monthly_dashboard():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0

    checkout_years = []
    checkout_trend_month = []


    for checkout in checkouts:
        date = checkout.checkout_date
        month = int(date.strftime("%m")) - 1
        year = int(date.strftime("%Y"))
        total_values += checkout.price * checkout.quantity
        
        if year not in checkout_years:
            checkout_years.append(year)
            checkout_trend_month.append([0] * 12)
            index = checkout_years.index(year)
            checkout_trend_month[index][month] += int(checkout.quantity)
        else:
            index = checkout_years.index(year)
            checkout_trend_month[index][month] += int(checkout.quantity)

    now = datetime.datetime.now()
    date_now = now.strftime("%d %B, %Y")
    year_now = int(now.strftime("%Y"))

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain
        checkout_quantity = item_quantity - item_remain


    select_year = None
    if checkout_years:
        index_year_now = checkout_years.index(year_now)
        select_year = int(request.form.get("year", index_year_now ))
    
    if "admin" in user.roles:
        return index_admin()

    return render_template(
        "/dashboard/monthly_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_month=checkout_trend_month,
        date_now=date_now,
        checkout_years=checkout_years,
        size_checkout_years=len(checkout_years),
        select_year=select_year,
    )


@module.route("/yearly")
@login_required
def yearly_dashboard():
    user = current_user._get_current_object()

    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    now = datetime.datetime.now()
    date_now = now.strftime("%d %B, %Y")

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0

    checkout_years = []
    checkout_trend_year = []
    

    for checkout in checkouts:
        date = checkout.checkout_date
        year = int(date.strftime("%Y"))
        total_values += checkout.price * checkout.quantity
        
        if year not in checkout_years:
            checkout_years.append(year)
            checkout_trend_year.append(0)
            index = checkout_years.index(year)
            checkout_trend_year[index] += int(checkout.quantity)
        
        else:
            index = checkout_years.index(year)
            checkout_trend_year[index] += int(checkout.quantity)


    print(checkout_years)
    print(checkout_trend_year)
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
        checkout_years=checkout_years,
        date_now=date_now,
    )
