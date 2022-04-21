from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint('item_checkouts', __name__, url_prefix='/item_checkouts')

@module.route('/')
@login_required
def index():
    checkouts = models.Checkout.objects()
    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts
        )


@module.route('/checkout', methods=["GET", "POST"])
@login_required
def checkout():
    items = models.Item.objects()
    form = forms.item_checkouts.ItemCheckoutForm()
    form.item.choices = [(str(item.id), item.name) for item in items]
    if not form.validate_on_submit():
        return render_template(
            '/item_checkouts/checkout.html',
            form=form,           
             )

    checkout = models.Checkout(
        description=form.description.data,
        user=current_user._get_current_object(),
    )
    
    item_checkout = models.ItemCheckout(
        item=models.Item.objects.get(id=form.item.data),
        quantity=form.quantity.data,
        price=form.price.data,
        checkout=checkout,
        )
    
    checkout.save()
    item_checkout.save()

    return redirect(url_for('item_checkouts.index'))