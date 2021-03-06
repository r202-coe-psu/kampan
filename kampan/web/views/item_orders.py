from calendar import calendar
from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for,request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime


from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint('item_orders', __name__, url_prefix='/item_orders')

def check_in_time(created_date, calendar_select,calendar_end):
    print(created_date, calendar_select, calendar_select <= created_date <= calendar_end)
    if calendar_select <= created_date <= calendar_end:
        return True
    else:
        return False

@module.route('/',methods=["GET","POST"])
@login_required
def index():
    orders = models.OrderItem.objects()

    form = forms.inventories.InventoryForm()
    return render_template(
        "/item_orders/index.html",
        orders=orders,
        form=form,
        calendar_select=form.calendar_select.data,
        calendar_end = form.calendar_end.data,
        check_in_time=check_in_time,
        )


@module.route('/order', methods=["GET", "POST"])
@login_required
def order():
    items = models.Item.objects()
    form = forms.item_orders.OrderItemForm()
    if not form.validate_on_submit():
        return render_template(
            '/item_orders/order.html',
            form=form,           
             )

    order = models.OrderItem()
        
    form.populate_obj(order)
    order.user = current_user._get_current_object()
    
    order.save()
    

    return redirect(url_for('item_orders.index'))

@module.route("/<order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    order = models.OrderItem.objects().get(id=order_id)
    form = forms.item_orders.OrderItemForm(obj=order)

    if not form.validate_on_submit():
        return render_template(
            "/item_orders/order.html",
            form=form,
        )

    form.populate_obj(order)
    order.save()

    return redirect(url_for("item_orders.index"))

@module.route("/<order_id>/delete")
@login_required
def delete(order_id):
    order = models.OrderItem.objects().get(id=order_id)
    order.delete()

    return redirect(url_for("item_orders.index"))
