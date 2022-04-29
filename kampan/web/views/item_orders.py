from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for
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

@module.route('/')
@login_required
def index():
    orders = models.OrderItem.objects()
    return render_template(
        "/item_orders/index.html",
        orders=orders,
        )


@module.route('/order', methods=["GET", "POST"])
@login_required
def order():
    items = models.Item.objects()
    form = forms.item_orders.BaseOrderItemForm()
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

