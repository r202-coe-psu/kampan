from atexit import register
from calendar import calendar
from crypt import methods
from pyexpat import model
from typing import OrderedDict
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms, acl
from kampan import models
import mongoengine as me

import datetime


module = Blueprint("item_checkouts", __name__, url_prefix="/item_checkouts")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    checkout_items = models.CheckoutItem.objects(
        status="active", organization=organization
    ).order_by("-created_date")

    items = models.Item.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    form.item.choices = [("", "เลือกวัสดุ")] + [
        (str(item.id), f"{item.barcode_id} ({item.name})") for item in items
    ]
    set_categories = set([f"{''.join(item.categories)}" for item in items])
    form.categories.choices = [("", "หมวดหมู่")] + [
        (f"{category}", f"{category}") for category in set_categories
    ]
    if form.start_date.data == None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            checkout_date__lt=form.end_date.data,
        )
        # approved_checkout_items = approved_checkout_items.filter(
        #     checkout_date__lt=form.end_date.data,
        # )
    elif form.start_date.data and form.end_date.data == None:
        checkout_items = checkout_items.filter(
            checkout_date__gte=form.start_date.data,
        )
        # approved_checkout_items = approved_checkout_items.filter(
        #     checkout_date__gte=form.start_date.data,
        # )
    elif form.start_date.data != None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            checkout_date__gte=form.start_date.data,
            checkout_date__lt=form.end_date.data,
        )
    if form.item.data:
        checkout_items = checkout_items.filter(item=form.item.data)

    if form.categories.data:
        items = models.Item.objects(categories=form.categories.data)
        list_checkout_items = []
        for item in items:
            checkout_items_ = checkout_items.filter(item=item.id)
            list_checkout_items += checkout_items_
        checkout_items = set(list_checkout_items)

    checkouts = list(checkout_items)
    checkouts = sorted(checkouts, key=lambda k: k["checkout_date"], reverse=True)

    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1

    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts,
        form=form,
        paginated_checkouts=paginated_checkouts,
        organization=organization,
    )


@module.route("/checkout", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def checkout():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    # items = models.Item.objects()
    form = forms.item_checkouts.CheckoutItemForm()
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()

    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())
        # print(item_register.get_item_in_bill())

    if items:
        form.item.choices = [
            (
                item.id,
                (
                    f"{item.barcode_id} ({item.name}) (มีวัสดุทั้งหมด {item.get_items_quantity()})"
                    + (
                        f" ({item.set_unit} {item.piece_unit}ละ {item.piece_per_set})"
                        if item.piece_per_set > 1
                        else f" ({item.set_unit}ละ 1)"
                    )
                    + (
                        f" (จองอยู่ทั้งหมด {item.get_booking_item()})"
                        if item.get_booking_item() != 0
                        else ""
                    )
                ),
            )
            for item in items
        ]
    if not form.validate_on_submit():
        print(form.errors)

        return render_template(
            "/item_checkouts/checkout.html", form=form, organization=organization
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item = models.CheckoutItem()
    checkout_item.user = current_user._get_current_object()
    checkout_item.order = order
    checkout_item.item = item
    checkout_item.checkout_date = form.checkout_date.data
    # checkout_item.set_ = form.set_.data
    checkout_item.piece = form.piece.data
    checkout_item.quantity = form.piece.data
    checkout_item.organization = organization
    checkout_item.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))


@module.route("/all-checkout", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def bill_checkout():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status__ne="disactive")

    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)

    return render_template(
        "/item_checkouts/bill-checkout.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
        organization=organization,
        order=order,
    )


@module.route("/checkout/<checkout_item_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(checkout_item_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    order = models.OrderItem.objects(id=checkout_item.order.id).first()

    form = forms.item_checkouts.CheckoutItemForm(obj=checkout_item)
    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())
        items = list(items)
        if checkout_item.item:
            items.append(models.Item.objects(id=checkout_item.item.id).first())
            # print(items)
    if items:
        form.item.choices = [
            (
                item.id,
                (
                    f"{item.barcode_id} ({item.name}) (มีวัสดุทั้งหมด {item.get_items_quantity()})"
                    + (
                        f" ({item.set_unit} {item.piece_unit}ละ {item.piece_per_set})"
                        if item.piece_per_set > 1
                        else f" ({item.set_unit}ละ 1)"
                    )
                    + (
                        f" (จองอยู่ทั้งหมด {item.get_booking_item()})"
                        if item.get_booking_item() != 0
                        else ""
                    )
                ),
            )
            for item in items
        ]
        form.item.process(data=checkout_item.item.id, formdata=form.item.choices)
    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/checkout.html", form=form, organization=organization
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item.user = current_user._get_current_object()
    checkout_item.item = item
    checkout_item.checkout_date = form.checkout_date.data
    checkout_item.set_ = form.set_.data
    checkout_item.quantity = form.quantity.data
    checkout_item.organization = organization
    checkout_item.save()
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            order_id=checkout_item.order.id,
            organization_id=organization_id,
        )
    )


@module.route("/checkout/<checkout_item_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(checkout_item_id):
    organization_id = request.args.get("organization_id")

    checkout_item = models.CheckoutItem.objects(id=checkout_item_id).first()
    checkout_item.status = "disactive"
    checkout_item.save()
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            order_id=checkout_item.order.id,
            organization_id=organization_id,
        )
    )
