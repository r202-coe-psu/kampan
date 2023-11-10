from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
from calendar import monthrange
import datetime

module = Blueprint("dashboard", __name__, url_prefix="/dashboard")
subviews = []


def index_admin():
    now = datetime.datetime.now()
    return render_template("/dashboard/index-admin.html", now=now, available_classes=[])


def index_user():
    return render_template(
        "/dashboard/daily_dashboard.html",
    )


@module.route("/")
def index():
    return redirect(url_for("dashboard.daily_dashboard"))


@module.route("/daily", methods=["GET", "POST"])
@login_required
def daily_dashboard():
    form = forms.inventories.InventoryForm()
    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    checkout_quantity, item_quantity, item_remain, total_values = 0, 0, 0, 0

    now = datetime.datetime.now()
    today_date = now.strftime("%d/%m/%Y")
    date_now = now.strftime("%d %B, %Y")
    month_now = int(now.strftime("%m"))
    year_now = int(now.strftime("%Y"))
    number_of_day = []
    checkout_trend_day = []
    years = []
    years_day = []

    for checkout in checkouts:
        date = checkout.checkout_date
        day_co = date.day - 1
        month_co = date.month - 1
        year_co = date.year

        if year_co not in years:
            years.append(year_co)

            numday = []
            for month in range(1, 13):
                month_size = monthrange(year_co, month)
                day = [0] * month_size[1]
                numday.append(day)
                day_in_month = [0] * month_size[1]
                for d in range(1, month_size[1] + 1):
                    day_in_month[d - 1] = d
                number_of_day.append(day_in_month)

            years_day.append(number_of_day)
            checkout_trend_day.append(numday)

        index_year_co = years.index(year_co)

        if checkout.status == "approved":
            checkout_trend_day[index_year_co][month_co][day_co] += (
                checkout.quantity * checkout.price
            )

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain

    eng_month = [
        "มกราคม",
        "กุมภาพันธ์",
        "มีนาคม",
        "เมษายน",
        "พฤษภาคม",
        "มิถุนายน",
        "กรกฏาคม",
        "สิงหาคม",
        "กันยายน",
        "ตุลาคม",
        "พฤศจิกายน",
        "ธันวาคม",
    ]

    # if "admin" in user.roles:
    #     return index_admin()

    sorted_checkout_trend_day = [i for _, i in sorted(zip(years, checkout_trend_day))]

    format_month = int(month_now) - 1
    format_year = year_now
    index_year = 0

    if request.method == "POST":
        format_year = form.calendar_month_year.data.year
        format_month = form.calendar_month_year.data.month

        if format_year in years:
            index_year = years.index(format_year)

        else:
            index_year = "none"

    years.append(year_now)
    select_year = years.index(year_now)
    select_month = int(month_now) - 1
    if format_year in years:
        print(format_year)
        select_year = index_year
        select_month = format_month

        for checkout_header in checkouts:
            if (
                checkout_header.checkout_date.month == format_month + 1
                and checkout_header.checkout_date.year == format_year
            ):
                if checkout_header.status == "approved":
                    total_values += checkout_header.price * checkout_header.quantity
                    checkout_quantity += checkout_header.quantity

    return render_template(
        "/dashboard/daily_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        years_day=years_day,
        number_of_day=number_of_day,
        eng_month=eng_month,
        date_now=date_now,
        select_year=select_year,
        select_month=select_month,
        checkout_trend_day=sorted_checkout_trend_day,
        years=sorted(years),
        size_years=len(years),
        today_date=today_date,
        form=form,
        format_month=format_month,
        format_year=format_year,
        idex_year=index_year,
    )


@module.route("/monthly", methods=["GET", "POST"])
@login_required
def monthly_dashboard():
    user = current_user._get_current_object()

    form = forms.inventories.InventoryForm()
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

        if year not in checkout_years:
            checkout_years.append(year)
            checkout_trend_month.append([0] * 12)
            index = checkout_years.index(year)
            if checkout.status == "approved":
                checkout_trend_month[index][month] += int(
                    checkout.quantity * checkout.price
                )
        else:
            index = checkout_years.index(year)
            if checkout.status == "approved":
                checkout_trend_month[index][month] += int(
                    checkout.quantity * checkout.price
                )

    now = datetime.datetime.now()
    today_date = now.strftime("%d/%m/%Y")
    date_now = now.strftime("%d %B, %Y")
    year_now = int(now.strftime("%Y"))

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain

    select_year = None
    if checkout_years:
        index_year_now = checkout_years.index(year_now)
        select_year = int(request.form.get("year", index_year_now))

    # if "admin" in user.roles:
    #     return index_admin()

    sorted_checkout_trend_month = [
        i for _, i in sorted(zip(checkout_years, checkout_trend_month))
    ]

    value_year = year_now
    check_date_index = None
    # เพิ่มการเช็คกราฟรายเดือนโดยการใช้ปฏิทิน
    if request.method == "POST":
        format_year = str(form.calendar_year.data)[:-15]
        value_year = int(format_year)

    for checkout_header in checkouts:
        if checkout_header.checkout_date.year == value_year:
            if checkout_header.status == "approved":
                checkout_quantity += checkout_header.quantity

        if value_year in checkout_years:
            check_date_index = int(checkout_years.index(value_year))
        else:
            check_date_index = 0

    if checkout_trend_month != []:
        total_values = float(sum(checkout_trend_month[check_date_index]))

    return render_template(
        "/dashboard/monthly_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_month=sorted_checkout_trend_month,
        date_now=date_now,
        checkout_years=sorted(checkout_years),
        size_checkout_years=len(checkout_years),
        select_year=select_year,
        today_date=today_date,
        form=form,
        check_date_index=check_date_index,
    )


@module.route("/yearly", methods=["GET", "POST"])
@login_required
def yearly_dashboard():
    user = current_user._get_current_object()

    form = forms.inventories.InventoryForm()
    inventories = models.Inventory.objects()
    checkouts = models.CheckoutItem.objects()

    now = datetime.datetime.now()
    today_date = now.strftime("%d/%m/%Y")
    date_now = now.strftime("%d %B, %Y")
    year_now = int(now.strftime("%Y"))

    checkout_quantity = 0
    item_quantity = 0
    item_remain = 0
    total_values = 0

    checkout_years = []
    checkout_trend_year = []

    for checkout in checkouts:
        date = checkout.checkout_date
        year = int(date.strftime("%Y"))
        if checkout.status == "approved":
            total_values += checkout.price * checkout.quantity

        if year not in checkout_years:
            checkout_years.append(year)
            checkout_trend_year.append(0)
            index = checkout_years.index(year)
            if checkout.status == "approved":
                checkout_trend_year[index] += int(checkout.quantity * checkout.price)

        else:
            index = checkout_years.index(year)
            if checkout.status == "approved":
                checkout_trend_year[index] += int(checkout.quantity * checkout.price)

        if checkout.status == "approved":
            checkout_quantity += checkout.quantity

    for inventory in inventories:
        item_quantity += inventory.quantity
        item_remain += inventory.remain

    # if "admin" in user.roles:
    #     return index_admin()

    sorted_checkout_trend_year = [
        i
        for _, i in sorted(
            zip(
                checkout_years,
                checkout_trend_year,
            )
        )
    ]

    return render_template(
        "/dashboard/yearly_dashboard.html",
        item_quantity=item_quantity,
        total_values=total_values,
        item_remain=item_remain,
        checkout_quantity=checkout_quantity,
        checkout_trend_year=sorted_checkout_trend_year,
        checkout_years=sorted(checkout_years),
        date_now=date_now,
        today_date=today_date,
        form=form,
    )
