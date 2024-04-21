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
    orders = models.OrderItem.objects(approval_status="pending", status="pending")

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


@module.route("/approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_index():
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
        "/approve_orders/admin_approve_index.html",
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
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/approve_orders/approve_detail.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


@module.route("/<order_id>/admin_approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def admin_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    error_message = request.args.get("error_message")

    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/approve_orders/admin_approve_detail.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
        error_message=error_message,
    )


@module.route("/<order_id>/endorser_approve", methods=["GET"])
@acl.organization_roles_required("admin", "endorser")
def endorser_approve(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    order.status = "active"
    order.save()

    return redirect(url_for("approve_orders.index", organization_id=organization_id))


@module.route("/<order_id>/admin_approve", methods=["GET"])
@acl.organization_roles_required("admin")
def admin_approve(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")

    for checkout in checkout_items:
        checkout.status = "active"
        # checkout.save()
        item = checkout.item
        quantity = (checkout.set_ * item.piece_per_set) + checkout.piece
        # print("--->", quantity, item.get_amount_pieces())
        if quantity > item.get_amount_pieces():
            return redirect(
                url_for(
                    "approve_orders.admin_approved_detail",
                    organization_id=organization_id,
                    order_id=order_id,
                    error_message=True,
                )
            )
        inventories = models.Inventory.objects(item=item, remain__gt=0)
        for inventory in inventories:
            if inventory.remain >= quantity:
                inventory.remain -= quantity
                quantity = 0
            else:
                quantity -= inventory.remain
                inventory.remain = 0

            inventory.save()
            checkout.inventories.append(inventory)
            if quantity <= 0:
                break
        checkout.save()
    order.approval_status = "approved"
    order.approved_date = datetime.datetime.now()
    order.save()
    return redirect(
        url_for("approve_orders.admin_index", organization_id=organization_id)
    )


@module.route("/<order_id>/endorser_denied", methods=["GET"])
@acl.organization_roles_required("admin", "endorser")
def endorser_denied(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    order.status = "denied"
    order.save()

    return redirect(url_for("approve_orders.index", organization_id=organization_id))


@module.route("/<order_id>/admin_denied", methods=["GET"])
@acl.organization_roles_required("admin")
def admin_denied(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    order.approval_status = "denied"
    order.save()

    for checkout in checkout_items:
        checkout.status = "denied"
        checkout.save()

    return redirect(
        url_for("approve_orders.admin_index", organization_id=organization_id)
    )


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
