from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
from calendar import monthrange
import datetime
from flask_mongoengine import Pagination

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
    organization = current_user.get_current_organization()
    user = current_user._get_current_object()
    if not organization and "admin" not in user.roles:
        return redirect(url_for("accounts.index"))
    if not organization:
        organization_id = request.args.get("organization_id")
        organization = models.Organization.objects(
            id=organization_id, status="active"
        ).first()
    form = forms.inventories.SearchStartEndDateForm()
    form.end_date.validators = None
    form.item.validators = None

    today = datetime.date.today()

    if form.start_date.data != None:
        today = form.start_date.data
    # print(today)
    item_orders = models.OrderItem.objects(status="active", organization=organization)

    daily_item_orders = item_orders.filter(
        created_date__gte=today,
        created_date__lt=today + datetime.timedelta(days=1),
    )
    approved_orders = item_orders.filter(
        created_date__gte=today,
        created_date__lt=today + datetime.timedelta(days=1),
        approval_status="approved",
    )

    total_values = sum(
        [approved_order.get_all_price() for approved_order in approved_orders]
    )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_daily_item_orders = Pagination(daily_item_orders, page=page, per_page=30)

    notifications = 0

    items = models.Item.objects(status="active")
    for item in items:
        if item.minimum > item.get_amount_items():
            notifications += 1
    return render_template(
        "/dashboard/daily_dashboard.html",
        form=form,
        total_values=total_values,
        daily_item_orders=daily_item_orders,
        paginated_daily_item_orders=paginated_daily_item_orders,
        today=today,
        notifications=notifications,
        organization=organization,
    )


@module.route("/monthly", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def monthly_dashboard():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.inventories.SearchMonthYearForm()

    today = datetime.datetime.today().date().replace(day=1)
    if form.validate_on_submit():
        print(form.errors)
        if form.month_year.data != None:
            today = form.month_year.data

    days_month = lambda dt: monthrange(dt.year, dt.month)[1]
    next_time = today + datetime.timedelta(days_month(today))

    # print(today, next_time)
    monthly_item_orders = models.OrderItem.objects(
        status="active",
        created_date__gte=today,
        created_date__lt=next_time,
        organization=organization,
    )

    days_month_categories = list(range(1, days_month(today) + 1))
    print(
        datetime.datetime.combine(today, datetime.datetime.min.time()),
        datetime.datetime.combine(next_time, datetime.datetime.min.time()),
    )
    pipeline_approved_checkout_items = [
        {
            "$match": {
                "status": "active",
                "approved_date": {
                    "$gte": datetime.datetime.combine(
                        today, datetime.datetime.min.time()
                    ),
                    "$lt": datetime.datetime.combine(
                        next_time, datetime.datetime.min.time()
                    ),
                },
            }
        },
        {
            "$group": {
                "_id": {"$dayOfMonth": "$approved_date"},
                "total": {
                    "$sum": {
                        "$multiply": [
                            "$price",
                            "$aprroved_amount",
                        ]
                    }
                },
            }
        },
    ]

    approved_checkout_items = models.CheckoutItem.objects().aggregate(
        pipeline_approved_checkout_items
    )
    trend_checkout_items = [0] * days_month(today)
    for checkout_item in approved_checkout_items:
        trend_checkout_items[checkout_item["_id"] - 1] = checkout_item["total"]
    total_values = sum(trend_checkout_items)
    months = [
        "มกราคม",
        "กุมภาพันธ์",
        "มีนาคม",
        "เมษายน",
        "พฤษภาคม",
        "มิถุนายน",
        "กรกฎาคม",
        "สิงหาคม",
        "กันยายน",
        "ตุลาคม",
        "พฤษจิกายน",
        "ธันวาคม",
    ]
    this_month = months[today.month - 1] + " " + str(today.year)

    notifications = 0

    items = models.Item.objects(status="active")
    for item in items:
        if item.minimum > item.get_amount_items():
            notifications += 1
    return render_template(
        "/dashboard/monthly_dashboard.html",
        trend_checkout_items=trend_checkout_items,
        days_month_categories=days_month_categories,
        form=form,
        monthly_item_orders=monthly_item_orders,
        total_values=total_values,
        this_month=this_month,
        notifications=notifications,
        organization=organization,
    )


@module.route("/yearly", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def yearly_dashboard():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.inventories.SearchYearForm()

    today = datetime.datetime.today().date().replace(month=1, day=1)
    if form.validate_on_submit():
        print(form.errors)
        if form.year.data != None:
            year = form.year.data
            today = today.replace(year=year)

    next_time = today.replace(year=today.year + 1)

    yearly_item_orders = models.OrderItem.objects(
        status="active",
        created_date__gte=today,
        created_date__lt=next_time,
        organization=organization,
    )

    # year_categories = list(range(1, days_month(today) + 1))
    pipeline_checkout_item = [
        {
            "$match": {
                "status": "active",
                "approved_date": {
                    "$gte": datetime.datetime.combine(
                        today, datetime.datetime.min.time()
                    ),
                    "$lt": datetime.datetime.combine(
                        next_time, datetime.datetime.min.time()
                    ),
                },
            }
        },
        {
            "$group": {
                "_id": {"$month": "$approved_date"},
                "total": {
                    "$sum": {
                        "$multiply": [
                            "$price",
                            "$aprroved_amount",
                        ]
                    }
                },
            }
        },
    ]
    checkout_items = models.CheckoutItem.objects().aggregate(pipeline_checkout_item)
    trend_checkout_items = [0] * 12
    for checkout_item in checkout_items:
        trend_checkout_items[checkout_item["_id"] - 1] = checkout_item["total"]
    total_values = sum(trend_checkout_items)
    this_year = today.year

    notifications = 0

    items = models.Item.objects(status="active")
    for item in items:
        if item.minimum > item.get_amount_items():
            notifications += 1
    return render_template(
        "/dashboard/yearly_dashboard.html",
        yearly_item_orders=yearly_item_orders,
        total_values=total_values,
        trend_checkout_items=trend_checkout_items,
        this_year=this_year,
        form=form,
        notifications=notifications,
        organization=organization,
    )
