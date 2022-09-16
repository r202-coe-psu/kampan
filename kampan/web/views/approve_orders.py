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
    orders = models.OrderItem.objects()

    form = forms.inventories.InventoryForm()
    
    return render_template(
        "/approve_orders/index.html",
        orders=orders,
        form=form,
        calendar_select=form.calendar_select.data,
        calendar_end = form.calendar_end.data,
        check_in_time=check_in_time,
    )

@module.route("<order_id>", methods=["GET", "POST"])
def approve(order_id):
    # checkout_item = models.CheckoutItem.objects.get(id=checkout_item_id)
    form = forms.item_orders.OrderItemForm()
    # order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order)
    
    order.status = "approved"
    form.populate_obj(order)
    order.save()


    for checkout in checkout_items:
        if checkout.order.status == "approved":
            checkout.status = "approved"
            form.populate_obj(checkout)
            checkout.save()
    
    # return redirect(url_for("item_checkouts.bill_checkout"))


    
    return redirect(url_for("approve_orders.index"))
