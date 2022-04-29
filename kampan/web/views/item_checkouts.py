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

module = Blueprint('item_checkouts', __name__, url_prefix='/item_checkouts')

@module.route('/')
@login_required
def index():
    checkouts = models.CheckoutItem.objects()
    return render_template(
        "/item_checkouts/index.html",
        checkouts=checkouts,
        )


@module.route('/checkout', methods=["GET", "POST"])
@login_required
def checkout():
    items = models.Item.objects()
    form = forms.item_checkouts.BaseCheckoutItemForm()
    if not form.validate_on_submit():
        return render_template(
            '/item_checkouts/checkout.html',
            form=form,           
             )

    checkout = models.CheckoutItem()
        
    form.populate_obj(checkout)
    checkout.user = current_user._get_current_object()
    
    checkout.save()
    

    return redirect(url_for('item_checkouts.index'))

