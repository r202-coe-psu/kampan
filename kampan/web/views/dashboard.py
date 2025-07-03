from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models, utils
from kampan.repositories.dashboards import DashboardRepository
from calendar import monthrange
from mongoengine import Q
import datetime
from flask_mongoengine import Pagination

module = Blueprint("dashboard", __name__, url_prefix="/dashboard")
subviews = []


def get_quarter_of_year(year):
    return [
        (datetime.date(year, 10, 1), datetime.date(year, 12, 31)),
        (datetime.date(year + 1, 1, 1), datetime.date(year + 1, 3, 31)),
        (datetime.date(year + 1, 4, 1), datetime.date(year + 1, 6, 30)),
        (datetime.date(year + 1, 7, 1), datetime.date(year + 1, 9, 30)),
    ]


def get_choice_of_quarter():
    quarter_choices = []
    default_quarter = ""

    start_year = 2023
    now_year = datetime.datetime.now().year
    for year in range(start_year, now_year + 1):
        quarter_dates = get_quarter_of_year(year)
        count = 0
        for start_date, end_date in quarter_dates:
            quarter_choices.append(
                (
                    f"{year}_{count}",
                    f"ปี {year+543+1} ไตรมาสที่ {(count%4)+1} : {start_date.strftime('%d-%m-%Y')} - {end_date.strftime('%d-%m-%Y')}",
                )
            )
            count += 1
            if end_date <= datetime.date.today():
                default_quarter = f"{year}_{count%4}"
    return quarter_choices, default_quarter


@module.route("/all_report", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
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

    quarter_choices, default_quarter = get_choice_of_quarter()

    form.quarter.choices = [("", "-")] + quarter_choices

    if not form.validate_on_submit():
        # if not form.quarter.data:
        #     form.quarter.data = default_quarter

        search_quarter = request.args.get("search_quarter")
        if search_quarter:
            form.quarter.data = search_quarter

        search_categories = request.args.get("search_categories")
        if search_categories:
            form.categories.data = search_categories

        search_start_date = request.args.get("search_start_date")
        if search_start_date:
            form.start_date.data = datetime.datetime.strptime(
                search_start_date,
                "%Y-%m-%d",
            )
        search_end_date = request.args.get("search_end_date")
        if search_end_date:
            form.end_date.data = datetime.datetime.strptime(
                search_end_date,
                "%Y-%m-%d",
            )

        start_date = None
        end_date = None
        category = None
        if form.categories.data:
            category = models.Category.objects(id=form.categories.data).first()

        search_item = request.args.get("search_item")
        if search_item:
            form.item.data = search_item
        item = None
        if form.item.data:
            item = models.Item.objects(id=form.item.data).first()
        if form.quarter.data:
            year, quarter = str(form.quarter.data).split("_")

            start_date, end_date = get_quarter_of_year(int(year))[int(quarter)]
        elif form.start_date.data and form.end_date.data:
            start_date = form.start_date.data
            end_date = form.end_date.data

        items_snapshot = []
        if start_date and end_date:
            items_snapshot = models.ItemSnapshot.objects(
                Q(created_date__gte=start_date + datetime.timedelta(days=1))
                & Q(created_date__lt=end_date + datetime.timedelta(days=2))
                & Q(organization=organization)
                & Q(status="active")
            )

            latest_snapshots = {}

            for snapshot in items_snapshot:
                item_id = snapshot.item  # or snapshot.item if you want the whole object
                if item_id not in latest_snapshots:
                    latest_snapshots[item_id] = snapshot
                else:
                    if snapshot.created_date > latest_snapshots[item_id].created_date:
                        latest_snapshots[item_id] = snapshot

            items_snapshot = list(latest_snapshots.values())

        if item:
            items_snapshot = [i for i in items_snapshot if i.item == item]
        elif category:
            items = models.Item.objects(categories=category, status="active")
            items_snapshot = [i for i in items_snapshot if i.item in items]
        return render_template(
            "/dashboard/all_report.html",
            organization=organization,
            items_snapshot=items_snapshot,
            form=form,
        )
    search_quarter = form.quarter.data
    search_categories = form.categories.data
    search_item = form.item.data
    return redirect(
        url_for(
            "dashboard.all_report",
            search_item=search_item,
            search_quarter=search_quarter,
            search_start_date=form.start_date.data,
            search_end_date=form.end_date.data,
            search_categories=search_categories,
            organization_id=organization_id,
        )
    )


@module.route("/all_report/download", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def download_all_report():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    search_quarter = request.args.get("search_quarter")
    start_date = None
    end_date = None
    search_start_date = request.args.get("search_start_date")
    if search_start_date:
        start_date = datetime.datetime.strptime(
            search_start_date,
            "%Y-%m-%d",
        )
    search_end_date = request.args.get("search_end_date")
    if search_end_date:
        end_date = datetime.datetime.strptime(
            search_end_date,
            "%Y-%m-%d",
        )
    if search_quarter:
        year, quarter = str(search_quarter).split("_")
        start_date, end_date = get_quarter_of_year(int(year))[int(quarter)]

    search_categories = request.args.get("search_categories")
    category = None
    if search_categories:
        category = models.Category.objects(id=search_categories).first()

    search_item = request.args.get("search_item")
    item = None
    if search_item:
        item = models.Item.objects(id=search_item).first()
    items_snapshot = []
    if start_date and end_date:
        items_snapshot = models.ItemSnapshot.objects(
            Q(created_date__gte=start_date + datetime.timedelta(days=1))
            & Q(created_date__lt=end_date + datetime.timedelta(days=2))
            & Q(organization=organization)
            & Q(status="active")
        ).order_by("item.name")
        latest_snapshots = {}

        for snapshot in items_snapshot:
            item_id = snapshot.item  # or snapshot.item if you want the whole object
            if item_id not in latest_snapshots:
                latest_snapshots[item_id] = snapshot
            else:
                if snapshot.created_date > latest_snapshots[item_id].created_date:
                    latest_snapshots[item_id] = snapshot

        items_snapshot = list(latest_snapshots.values())
    if item:
        items_snapshot = [i for i in items_snapshot if i.item == item]
    elif category:
        items = models.Item.objects(categories=category, status="active")
        items_snapshot = [i for i in items_snapshot if i.item in items]

    response = utils.reports.get_all_report(
        items_snapshot,
        organization,
        start_date=start_date,
        end_date=end_date,
        search_quarter=search_quarter,
    )
    return response


def fetch_organization(organization_id):
    return models.Organization.objects(id=organization_id, status="active").first()


def fetch_items(organization):
    return models.Item.objects(organization=organization, status="active")


def fetch_filtered_data(model, start_date, end_date, item_id, organization):
    return model.objects(
        Q(created_date__gte=start_date)
        & Q(created_date__lt=end_date + datetime.timedelta(days=1))
        & Q(status="active")
        & Q(item=item_id)
        & Q(organization=organization)
    )


def prepare_data(start_date, end_date, item_id, organization):
    item_snapshot = (
        fetch_filtered_data(
            models.ItemSnapshot, start_date, end_date, item_id, organization
        )
        .order_by("created_date")
        .first()
    )
    inventories = fetch_filtered_data(
        models.Inventory, start_date, end_date, item_id, organization
    )
    item_checkouts = fetch_filtered_data(
        models.CheckoutItem, start_date, end_date, item_id, organization
    )
    lost_break_items = fetch_filtered_data(
        models.LostBreakItem, start_date, end_date, item_id, organization
    )

    data = (
        ([item_snapshot] if item_snapshot else [])
        + list(item_checkouts)
        + list(inventories)
        + list(lost_break_items)
    )
    return sorted(data, key=lambda el: el["created_date"])


def calculate_amount_item(data):
    amount_item = 0
    list_data = []
    for row in data:
        if row._cls == "ItemSnapshot":
            amount_item = row.amount
        elif row._cls == "CheckoutItem":
            amount_item -= row.quantity
        elif row._cls == "Inventory":
            amount_item += row.quantity
        elif row._cls == "LostBreakItem":
            amount_item -= row.quantity
        list_data.append((row, amount_item))
    return list_data


@module.route("/item_report_quarter", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def item_report_quarter():
    organization_id = request.args.get("organization_id")
    organization = fetch_organization(organization_id)
    items = fetch_items(organization)
    form = forms.dashboard.ItemReportQuarter()
    form.item.choices = [(str(item.id), item.name) for item in items]
    form.quarter.choices, default_quarter = get_choice_of_quarter()

    if not form.validate_on_submit():
        form.quarter.data = request.args.get("search_quarter", default_quarter)
        form.item.data = request.args.get(
            "search_item", (form.item.choices[0][0] if form.item.choices else None)
        )

        year, quarter = str(form.quarter.data).split("_")
        start_date, end_date = get_quarter_of_year(int(year))[int(quarter)]

        reports = DashboardRepository.get_item_report(
            start_date=start_date,
            end_date=end_date,
            item_id=form.item.data,
            organization_id=organization_id,
        )
        return render_template(
            "/dashboard/item_report_quarter.html",
            organization=organization,
            reports=reports,
            form=form,
        )

    return redirect(
        url_for(
            "dashboard.item_report_quarter",
            search_quarter=form.quarter.data,
            search_item=form.item.data,
            organization_id=organization_id,
        )
    )


@module.route("/item_report_custom", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def item_report_custom():
    organization_id = request.args.get("organization_id")
    organization = fetch_organization(organization_id)
    items = fetch_items(organization)
    form = forms.dashboard.ItemReportCustom()
    form.item.choices = [(str(item.id), item.name) for item in items]

    if not form.validate_on_submit():

        search_start_date = request.args.get("search_start_date")
        if search_start_date:
            form.start_date.data = datetime.datetime.strptime(
                search_start_date,
                "%Y-%m-%d",
            )

        else:
            form.start_date.data = datetime.datetime.combine(
                datetime.datetime.now().replace(day=1), datetime.datetime.min.time()
            )
        search_end_date = request.args.get("search_end_date")
        if search_end_date:
            form.end_date.data = datetime.datetime.strptime(
                search_end_date,
                "%Y-%m-%d",
            )
        else:
            form.end_date.data = datetime.datetime.combine(
                datetime.datetime.now(), datetime.datetime.min.time()
            )

        form.item.data = request.args.get(
            "search_item", (form.item.choices[0][0] if form.item.choices else None)
        )
        reports = DashboardRepository.get_item_report(
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            item_id=form.item.data,
            organization_id=organization_id,
        )
        data = prepare_data(
            form.start_date.data, form.end_date.data, form.item.data, organization
        )
        list_data = calculate_amount_item(data)
        return render_template(
            "/dashboard/item_report_custom.html",
            organization=organization,
            reports=reports,
            form=form,
        )

    return redirect(
        url_for(
            "dashboard.item_report_custom",
            search_start_date=form.start_date.data,
            search_end_date=form.end_date.data,
            search_item=form.item.data,
            organization_id=organization_id,
        )
    )


@module.route("/item_report/download", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def download_item_report():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    search_quarter = request.args.get("search_quarter")
    if search_quarter:
        year, quarter = str(search_quarter).split("_")
        start_date, end_date = get_quarter_of_year(int(year))[int(quarter) - 1]

    search_start_date = request.args.get("search_start_date")
    search_end_date = request.args.get("search_end_date")
    if search_start_date and search_end_date:
        start_date = datetime.datetime.strptime(
            search_start_date,
            "%Y-%m-%d %H:%M:%S",
        )
        end_date = datetime.datetime.strptime(
            search_end_date,
            "%Y-%m-%d %H:%M:%S",
        )
    if not start_date or not end_date:
        return redirect(
            url_for(
                "dashboard.item_report_all",
                organization_id=organization_id,
            )
        )
    item_id = request.args.get("item_id")
    response = utils.reports.get_item_report(
        start_date, end_date, organization, item_id
    )
    return response


@module.route("/summary", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def dashboard():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    notifications = 0

    items = models.Item.objects(status="active")
    orders = models.OrderItem.objects(
        organization=organization, status="pending"
    ).order_by("created_date")[0:3]
    count_orders = (
        models.OrderItem.objects(organization=organization, status="pending")
        .order_by("created_date")
        .count()
    )
    pending_orders = models.OrderItem.objects(
        Q(organization=organization)
        & Q(status__ne="denied")
        & Q(status__ne="approved")
        & Q(status__ne="pending")
        & Q(status__ne="disactive")
    ).order_by("created_date")[0:3]
    count_pending_orders = (
        models.OrderItem.objects(
            Q(organization=organization)
            & Q(status__ne="denied")
            & Q(status__ne="approved")
            & Q(status__ne="pending")
            & Q(status__ne="disactive")
        )
        .order_by("created_date")
        .count()
    )
    for item in items:
        if item.minimum >= item.get_amount_pieces():
            notifications += 1
    return render_template(
        "/dashboard/summary.html",
        organization=organization,
        notifications=notifications,
        orders=orders,
        pending_orders=pending_orders,
        count_orders=count_orders,
        count_pending_orders=count_pending_orders,
    )
