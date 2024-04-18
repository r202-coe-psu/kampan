from calendar import calendar
from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
import mongoengine as me

from kampan.web import forms, acl
from kampan import models

module = Blueprint("item_orders", __name__, url_prefix="/item_orders")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(status="active")

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
    if form.start_date.data or form.end_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=24)

    return render_template(
        "/item_orders/index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/order", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def order():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.item_orders.OrderItemForm()
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/item_orders/order.html", form=form, organization=organization
        )

    order = models.OrderItem()

    form.populate_obj(order)
    order.created_by = current_user._get_current_object()
    if current_user._get_current_object().get_current_division():
        order.division = current_user._get_current_object().get_current_division()

    order.organization = organization
    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))


@module.route("/<order_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects().get(id=order_id)
    form = forms.item_orders.OrderItemForm(obj=order)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/item_orders/order.html", form=form, organization=organization
        )

    form.populate_obj(order)

    order.created_by = current_user._get_current_object()
    print(current_user._get_current_object().get_current_division())
    if current_user._get_current_object().get_current_division():
        order.division = current_user._get_current_object().get_current_division()
    order.organization = organization

    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))


@module.route("/<order_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects().get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order)
    for checkout in checkouts:
        checkout.status = "disactive"
        checkout.save()
    order.status = "disactive"

    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))
