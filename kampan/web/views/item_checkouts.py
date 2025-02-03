from atexit import register
from calendar import calendar
from crypt import methods
from pyexpat import model
from typing import OrderedDict
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms, acl
from kampan import models, utils
import mongoengine as me
import datetime


module = Blueprint("item_checkouts", __name__, url_prefix="/item_checkouts")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if current_user.has_organization_roles("admin", "supervisor supplier"):
        checkout_items = models.CheckoutItem.objects(
            status="active", organization=organization
        ).order_by("-created_date")
    else:
        checkout_items = models.CheckoutItem.objects(
            status="active", organization=organization, user=current_user
        ).order_by("-created_date")

    items = models.Item.objects(status="active")
    form = forms.inventories.SearchStartEndDateForm()
    form.item.choices = [("", "เลือกวัสดุ")] + [
        (str(item.id), f"{item.barcode_id} ({item.name})") for item in items
    ]

    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    if form.start_date.data == None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__lt=form.end_date.data,
        )
        # approved_checkout_items = approved_checkout_items.filter(
        #     created_date__lt=form.end_date.data,
        # )
    elif form.start_date.data and form.end_date.data == None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
        )
        # approved_checkout_items = approved_checkout_items.filter(
        #     created_date__gte=form.start_date.data,
        # )
    elif form.start_date.data != None and form.end_date.data != None:
        checkout_items = checkout_items.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
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
    checkouts = sorted(checkouts, key=lambda k: k["created_date"], reverse=True)

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


@module.route("/order/<order_id>/catalogs", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def catalogs(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects(id=order_id).first()
    form = forms.items.SearchItemForm()

    items = models.Item.objects(
        status__in=["active"], organization=organization
    ).order_by("status", "-created_date")

    form.item.choices = [("", "เลือกวัสดุ")] + [
        (
            str(item.id),
            f"{item.name} " + (f"({item.barcode_id}) " if item.barcode_id else ""),
        )
        for item in items
    ]

    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    if not form.validate_on_submit():

        item_name = request.args.get("item_name")
        if item_name:
            form.item_name.data = item_name
            items = items.filter(name__icontains=form.item_name.data)

        item_select_id = request.args.get("item_select_id")
        if item_select_id:
            form.item.data = item_select_id
            items = items.filter(id=form.item.data)

        categories = request.args.get("categories")

        if categories:
            form.categories.data = categories
            items = items.filter(categories=form.categories.data)

        page = request.args.get("page", default=1, type=int)
        try:
            paginated_items = Pagination(items, page=page, per_page=24)
        except:
            paginated_items = Pagination(items, page=1, per_page=24)

        return render_template(
            "/item_checkouts/catalogs.html",
            paginated_items=paginated_items,
            items=items,
            form=form,
            organization=organization,
            order=order,
        )
    item_name = form.item_name.data
    item_select_id = form.item.data
    categories = form.categories.data
    organization_id = organization.id
    return redirect(
        url_for(
            "item_checkouts.catalogs",
            organization_id=organization_id,
            item_name=item_name,
            categories=categories,
            item_select_id=item_select_id,
            order_id=order_id,
        )
    )


@module.route("/checkout", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def checkout():
    organization_id = request.args.get("organization_id")
    item_id = request.args.get("item_id")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    # items = models.Item.objects()
    form = forms.item_checkouts.CheckoutItemForm()
    order = models.OrderItem.objects(id=request.args.get("order_id")).first()
    checkout_item = None
    if order:
        checkout_item = models.CheckoutItem.objects(item=item_id, order=order, status__ne="disactive").first()
    if checkout_item:
        return redirect(
            url_for(
                "item_checkouts.edit",
                checkout_item_id=checkout_item.id,
                order_id=checkout_item.order.id,
                organization_id=organization_id,
            )
        )
    items = models.Item.objects(status="active")
    if order.get_item_in_bill():
        items = items.filter(id__nin=order.get_item_in_bill())

    if items:
        form.item.choices = [
            (
                item.id,
                (
                    f"{item.barcode_id} {item.name} (มีวัสดุทั้งหมด {item.get_items_quantity()})"
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
                    + (f" หมายเหตุ {item.remark}" if item.remark else "")
                ),
            )
            for item in items
        ]
    if not form.validate_on_submit():
        if item_id:
            form.item.data = item_id
        return render_template(
            "/item_checkouts/checkout.html",
            form=form,
            order=order,
            organization=organization,
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item = models.CheckoutItem()
    checkout_item.user = current_user._get_current_object()
    checkout_item.order = order
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    # checkout_item.set_ = form.set_.data
    checkout_item.piece = form.piece.data
    checkout_item.quantity = form.piece.data
    checkout_item.organization = organization
    checkout_item.save()

    return render_template(
        "/item_checkouts/checkout.html",
        form=form,
        order=order,
        organization=organization,
        success=True,
    )


@module.route("/all-checkout", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
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
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
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
            "/item_checkouts/checkout.html",
            form=form,
            organization=organization,
            order=order,
        )
    item = models.Item.objects(id=form.item.data).first()
    checkout_item.user = current_user._get_current_object()
    checkout_item.item = item
    checkout_item.created_date = form.created_date.data
    checkout_item.quantity = form.piece.data
    checkout_item.piece = form.piece.data
    checkout_item.organization = organization
    checkout_item.save()
    return render_template(
        "/item_checkouts/checkout.html",
        form=form,
        organization=organization,
        order=order,
        success=True,
    )


@module.route("/checkout/<checkout_item_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
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


@module.route("/order/<order_id>/upload_file_items", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_file(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.get("errors")
    order = models.OrderItem.objects(id=order_id).first()

    if not form.validate_on_submit():
        return render_template(
            "/item_checkouts/upload_file.html",
            organization=organization,
            errors=errors,
            form=form,
            order_id=order.id,
            order=order,
        )

    if form.upload_file.data:
        errors = utils.item_checkouts.validate_items_upload_engagement(
            form.upload_file.data, organization
        )
        if not errors:
            completed = utils.item_checkouts.process_items_upload_file(
                form.upload_file.data, organization, order
            )
        else:
            return render_template(
                "/item_checkouts/upload_file.html",
                organization=organization,
                errors=errors,
                form=form,
                order_id=order_id,
                order=order,
            )
    else:
        return redirect(
            url_for(
                "item_checkouts.upload_file",
                organization_id=organization_id,
                errors=["ไม่พบไฟล์"],
                order_id=order_id,
            )
        )
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            organization_id=organization_id,
            order_id=order.id,
        )
    )
