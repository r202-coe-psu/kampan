from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for, request, send_file
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")


@module.route("/")
@login_required
def index():
    orders = models.OrderItem.objects()

    return render_template(
        "/approve_orders/index.html",
        orders=orders,
    )

@module.route("<order_id>")
def approve(order_id):
    order = models.OrderItem.objects.get(id=order_id)
    form = forms.item_orders.OrderItemForm(obj=order)

    form.populate_obj(order)
    order.status = "Approved"
    order.save()

    return redirect(url_for("approve_orders.index"))
