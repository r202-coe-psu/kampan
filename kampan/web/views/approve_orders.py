from calendar import calendar
from crypt import methods
from pyexpat import model
from tabnanny import check
from flask import Blueprint, render_template, redirect, url_for, request, send_file
from flask_login import login_required, current_user
from kampan.models import inventories
from kampan.web import forms
from kampan import models
from kampan.web.views.lost_breaks import check_in_time

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")

def check_in_time(created_date, calendar_select,calendar_end):
    print(created_date, calendar_select, calendar_select <= created_date <= calendar_end)
    if calendar_select <= created_date <= calendar_end:
        return True
    else:
        return False


@module.route("/",methods=["GET","POST"])
@login_required
def index():
    if "admin" in current_user.roles or "supervisor" in current_user.roles:
        orders = models.OrderItem.objects(status="pending")

        form = forms.inventories.InventoryForm()
        
        return render_template(
            "/approve_orders/index.html",
            orders=orders,
            form=form,
            calendar_select=form.calendar_select.data,
            calendar_end = form.calendar_end.data,
            check_in_time=check_in_time,
        )
    return redirect(url_for("dashboard.daily_dashboard"))

@module.route("<order_id>", methods=["GET"])
def approve(order_id):
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order)
    
    order.status = "approved"
    order.save()

    for checkout in checkout_items:
        if checkout.order.status == "approved":
            checkout.status = "approved"
            checkout.save()
    
    return redirect(url_for("approve_orders.index"))
