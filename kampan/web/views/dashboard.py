from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models, utils
from calendar import monthrange
from mongoengine import Q
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


@module.route("/daily", methods=["GET", "POST"])
@login_required
def daily_dashboard():
    organization_id = request.args.get("organization_id")
    organization = current_user.get_current_organization()
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


@module.route("/all_report", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def all_report():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.dashboard.AllItemReport()
    form.categories.choices += [
        (str(category.id), category.name)
        for category in models.Category.objects(
            status="active", organization=organization
        )
    ]
    form.item.choices += [
        (str(item.id), item.name)
        for item in models.Item.objects(status="active", organization=organization)
    ]
    if not form.validate_on_submit():
        form.start_date.data = datetime.datetime.combine(
            datetime.datetime.now(), datetime.datetime.min.time()
        )
        search_date = request.args.get("search_date")
        if search_date:
            form.start_date.data = datetime.datetime.strptime(
                search_date,
                "%Y-%m-%d",
            )

        search_categories = request.args.get("search_categories")
        if search_categories:
            form.categories.data = search_categories
        category = None
        if form.categories.data:
            category = models.Category.objects(id=form.categories.data).first()

        search_item = request.args.get("search_item")
        if search_item:
            form.item.data = search_item
        item = None
        if form.item.data:
            item = models.Item.objects(id=form.item.data).first()

        items_snapshot = models.ItemSnapshot.objects(
            Q(created_date__gte=form.start_date.data)
            & Q(created_date__lt=form.start_date.data + datetime.timedelta(days=1))
            & Q(organization=organization)
        )
        if item:
            items_snapshot = [i for i in items_snapshot if i.item == item]
        elif category:
            items = models.Item.objects(categories=category, status="active")
            items_snapshot = [i for i in items_snapshot if i.item in items]
        print(form.errors)
        return render_template(
            "/dashboard/all_report.html",
            organization=organization,
            items_snapshot=items_snapshot,
            form=form,
        )
    search_date = form.start_date.data
    search_categories = form.categories.data
    search_item = form.item.data
    return redirect(
        url_for(
            "dashboard.all_report",
            search_item=search_item,
            search_date=search_date,
            search_categories=search_categories,
            organization_id=organization_id,
        )
    )


@module.route("/all_report/download", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def download_all_report():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    search_date = request.args.get("search_date")
    if not search_date:
        date = datetime.datetime.combine(
            datetime.datetime.now(), datetime.datetime.min.time()
        )
    else:
        date = datetime.datetime.strptime(
            search_date,
            "%Y-%m-%d",
        )
    search_categories = request.args.get("search_categories")
    category = None
    if search_categories:
        category = models.Category.objects(id=search_categories).first()

    search_item = request.args.get("search_item")
    item = None
    if search_item:
        item = models.Item.objects(id=search_item).first()
    items_snapshot = models.ItemSnapshot.objects(
        Q(created_date__gte=date)
        & Q(created_date__lt=date + datetime.timedelta(days=1))
        & Q(organization=organization)
    ).order_by("item.name")
    if item:
        items_snapshot = [i for i in items_snapshot if i.item == item]
    elif category:
        items = models.Item.objects(categories=category, status="active")
        items_snapshot = [i for i in items_snapshot if i.item in items]
    response = utils.reports.get_all_report(items_snapshot, organization)
    return response


@module.route("/item_report", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def item_report():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    items = models.Item.objects(organization=organization, status="active")
    form = forms.dashboard.ItemReport()
    form.item.choices = [(str(item.id), item.name) for item in items]
    if not form.validate_on_submit():
        form.start_date.data = datetime.datetime.combine(
            datetime.datetime.now().replace(day=1), datetime.datetime.min.time()
        )
        search_start_date = request.args.get("search_start_date")
        if search_start_date:
            form.start_date.data = datetime.datetime.strptime(
                search_start_date,
                "%Y-%m-%d",
            )
        form.end_date.data = datetime.datetime.combine(
            datetime.datetime.now(), datetime.datetime.min.time()
        )
        search_end_date = request.args.get("search_end_date")
        if search_end_date:
            form.end_date.data = datetime.datetime.strptime(
                search_end_date,
                "%Y-%m-%d",
            )

        search_item = request.args.get("search_item")
        if search_item:
            form.item.data = search_item
        else:
            try:
                form.item.data = form.item.choices[0][0]
            except:
                pass

        item_snapshot = (
            models.ItemSnapshot.objects(
                Q(created_date__gte=form.start_date.data)
                & Q(created_date__lt=form.end_date.data + datetime.timedelta(days=1))
                & Q(item=form.item.data)
                & Q(organization=organization)
            )
            .order_by("created_date")
            .first()
        )
        inventories = models.Inventory.objects(
            Q(registeration_date__gte=form.start_date.data)
            & Q(registeration_date__lt=form.end_date.data + datetime.timedelta(days=1))
            & Q(item=form.item.data)
            & Q(organization=organization)
        )
        item_checkouts = models.CheckoutItem.objects(
            Q(checkout_date__gte=form.start_date.data)
            & Q(checkout_date__lt=form.end_date.data + datetime.timedelta(days=1))
            & Q(item=form.item.data)
            & Q(organization=organization)
        )
        print(item_snapshot)
        data = [item_snapshot] + list(item_checkouts) + list(inventories)
        print(form.errors)
        return render_template(
            "/dashboard/item_report.html",
            organization=organization,
            data=data,
            form=form,
        )
    search_start_date = form.start_date.data
    search_end_date = form.end_date.data
    search_item = form.item.data
    return redirect(
        url_for(
            "dashboard.item_report",
            search_start_date=search_start_date,
            search_end_date=search_end_date,
            search_item=search_item,
            organization_id=organization_id,
        )
    )


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def dashboard():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    return render_template("/dashboard/dashboard.html", organization=organization)
