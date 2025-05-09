from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
import mongoengine as me

from kampan.web import forms, acl
from kampan import models


module = Blueprint("item_checkouts", __name__, url_prefix="/item_checkouts")


@module.route("/", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def index():
    checkout_items = models.CheckoutItem.objects(
        status="active", approval_status="pending"
    )
    approved_checkout_items = models.inventories.ApprovedCheckoutItem.objects(
        status="active"
    )
    items = models.Item.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    form.item.choices = [
        (item.id, f"{item.barcode_id} ({item.name})") for item in items
    ]
    if form.start_date.data == None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__lt=form.end_date.data,
        )
        approved_checkout_items = approved_checkout_items.filter(
            created_date__lt=form.end_date.data,
        )
    elif form.start_date.data and form.end_date.data == None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
        )
        approved_checkout_items = approved_checkout_items.filter(
            created_date__gte=form.start_date.data,
        )
    elif form.start_date.data != None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
        approved_checkout_items = approved_checkout_items.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.item.data != None:
        approved_checkout_items = approved_checkout_items.filter(item=form.item.data)
        checkout_items = checkout_items.filter(item=form.item.data)
    checkouts = list(checkout_items) + list(approved_checkout_items)
    checkouts = sorted(checkouts, key=lambda k: k["created_date"], reverse=True)

    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/admin/item_checkouts/index.html",
        checkouts=checkouts,
        form=form,
        paginated_checkouts=paginated_checkouts,
    )


@module.route("/checkout", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def checkout():
    # items = models.Item.objects()
    form = forms.item_checkouts.CheckoutItemForm()
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()

    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())

    if items:
        form.item.choices = [
            (
                item.id,
                f"{item.barcode_id} ({item.name}) (มีวัสดุทั้งหมด {item.get_items_quantity()} {item.unit})"
                + (
                    f" (จองอยู่ทั้งหมด {item.get_booking_item()})"
                    if item.get_booking_item() != 0
                    else ""
                ),
            )
            for item in items
        ]
    if not form.validate_on_submit():

        return render_template(
            "/admin/item_checkouts/checkout.html",
            form=form,
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item = models.CheckoutItem()
    checkout_item.user = current_user._get_current_object()
    checkout_item.order = order
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    checkout_item.quantity = form.quantity.data
    checkout_item.save()

    return redirect(url_for("admin.item_orders.index"))


@module.route("/all-checkout", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def bill_checkout():
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")

    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)

    return render_template(
        "/admin/item_checkouts/bill-checkout.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
    )


@module.route("/checkout/<checkout_item_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def edit(checkout_item_id):
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    order = models.OrderItem.objects(id=checkout_item.order.id).first()

    form = forms.item_checkouts.CheckoutItemForm(obj=checkout_item)
    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())
        items = list(items)
        if checkout_item.item:
            items.append(models.Item.objects(id=checkout_item.item.id).first())
    if items:
        form.item.choices = [
            (item.id, f"{item.barcode_id} ({item.name})") for item in items
        ]
        form.item.process(data=checkout_item.item.id, formdata=form.item.choices)
    if not form.validate_on_submit():
        return render_template(
            "/admin/item_checkouts/checkout.html",
            form=form,
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item.user = current_user._get_current_object()
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    checkout_item.quantity = form.quantity.data
    checkout_item.save()
    return redirect(
        url_for("admin.item_checkouts.bill_checkout", order_id=checkout_item.order.id)
    )


@module.route("/checkout/<checkout_item_id>/delete", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def delete(checkout_item_id):
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    checkout_item.status = "disactive"
    checkout_item.save()
    return redirect(
        url_for("admin.item_checkouts.bill_checkout", order_id=checkout_item.order.id)
    )
