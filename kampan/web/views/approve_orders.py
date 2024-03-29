from calendar import calendar
from crypt import methods
from pyexpat import model
from tabnanny import check
from flask import Blueprint, render_template, redirect, url_for, request, send_file
from flask_login import login_required, current_user
from kampan.models import inventories
from kampan.web import forms, acl
from kampan import models
from flask_mongoengine import Pagination
import datetime

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(approval_status="pending", status="active")

    form = forms.inventories.SearchStartEndDateForm()
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=30)
    return render_template(
        "/approve_orders/index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects(id=order_id).first()
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    items = order.get_item_detail()

    form = forms.item_orders.get_approved_amount_form(items)
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/approve_orders/approve_detail.html",
            form=form,
            checkouts=checkouts,
            organization=organization,
        )
    dict_checkouts = dict()
    for checkout in checkouts:
        dict_checkouts[checkout.item.name] = dict()
        dict_checkouts[checkout.item.name]["checkout_date"] = checkout.checkout_date
        dict_checkouts[checkout.item.name]["quantity"] = checkout.quantity

    for item in form:
        # This code area have to rewrite for supporting multiple checkin_item, in case of remain less than request
        if item.id == "csrf_token":
            continue
        inventories = models.Inventory.objects(
            item=item.id, remain__gt=0, status="active"
        )
        aprroved_amount = item.data
        for inventory in inventories:
            approved_checkout = models.inventories.ApprovedCheckoutItem()
            approved_checkout.user = current_user._get_current_object()
            approved_checkout.order = order
            approved_checkout.item = inventory.item
            approved_checkout.checkout_date = dict_checkouts[inventory.item.name][
                "checkout_date"
            ]
            approved_checkout.checkout_from = inventory
            approved_checkout.warehouse = inventory.warehouse
            approved_checkout.price = inventory.price
            approved_checkout.approved_date = datetime.datetime.now()
            approved_checkout.quantity = dict_checkouts[inventory.item.name]["quantity"]

            if inventory.remain >= aprroved_amount:
                inventory.remain -= aprroved_amount
                approved_checkout.aprroved_amount = aprroved_amount
                aprroved_amount = 0
            else:
                aprroved_amount -= inventory.remain
                approved_checkout.aprroved_amount = inventory.remain
                inventory.remain = 0
            inventory.save()
            approved_checkout.save()

            if aprroved_amount <= 0:
                break

    return redirect(
        url_for(
            "approve_orders.approve", order_id=order_id, organization_id=organization_id
        )
    )


@module.route("<order_id>", methods=["GET"])
@acl.organization_roles_required("admin", "endorser")
def approve(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    order.approval_status = "approved"
    order.save()

    for checkout in checkout_items:
        checkout.approval_status = "approved"
        checkout.save()

    return redirect(url_for("approve_orders.index", organization_id=organization_id))


@module.route("/item_checkouts", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def item_checkouts():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/approve_orders/item_checkouts.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
        organization=organization,
    )
