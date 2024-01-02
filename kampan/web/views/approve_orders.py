from calendar import calendar
from crypt import methods
from pyexpat import model
from tabnanny import check
from flask import Blueprint, render_template, redirect, url_for, request, send_file
from flask_login import login_required, current_user
from kampan.models import inventories
from kampan.web import forms
from kampan import models
import datetime

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")


@module.route("/", methods=["GET", "POST"])
@login_required
def index():
    if "admin" in current_user.roles or "supervisor" in current_user.roles:
        orders = models.OrderItem.objects(approval_status="pending", status="active")

        form = forms.inventories.SearchStartEndDateForm()
        if form.start_date.data == None and form.end_date.data != None:
            orders = orders.filter(
                created_date__lte=form.end_date.data,
            )

        elif form.start_date.data and form.end_date.data == None:
            orders = orders.filter(
                created_date__gte=form.start_date.data,
            )

        elif form.start_date.data != None and form.end_date.data != None:
            orders = orders.filter(
                created_date__gte=form.start_date.data,
                created_date__lte=form.end_date.data,
            )
        return render_template(
            "/approve_orders/index.html",
            orders=orders,
            form=form,
        )
    return redirect(url_for("dashboard.daily_dashboard"))


@module.route("<order_id>", methods=["GET"])
def approve(order_id):
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order)
    order.approval_status = "approved"
    order.approved_date = datetime.datetime.now()
    order.save()

    for checkout in checkout_items:
        if checkout.order.approval_status == "approved":
            checkout.approval_status = "approved"
            checkout.approved_date = datetime.datetime.now()
            checkout.save()

    return redirect(url_for("approve_orders.index"))


@module.route("/order-item/<order_id>/items", methods=["GET", "POST"])
@login_required
def item_checkouts(order_id):
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")

    return render_template(
        "/approve_orders/approved_item_checkouts.html",
        checkouts=checkouts,
        order_id=order_id,
    )
