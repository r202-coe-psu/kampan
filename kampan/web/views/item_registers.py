from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint('item_registers', __name__, url_prefix='/item_registers')

@module.route('/')
@login_required
def index():
    item_registers = models.ItemRegisteration.objects()
    return render_template(
        "/item_registers/index.html",
        item_registers=item_registers
        )


@module.route('/register', methods=["GET", "POST"])
@login_required
def register():
    items = models.Item.objects()
    form = forms.item_registers.ItemRegisterationForm()
    form.item.choices = [(str(item.id), item.name) for item in items]
    if not form.validate_on_submit():
        return render_template(
            '/item_registers/register.html',
            form=form,           
            )

    item_register = models.ItemRegisteration(
        item=models.Item.objects.get(id=form.item.data),
        description=form.description.data,
        quantity=form.quantity.data,
        price=form.price.data,
        user=current_user._get_current_object(),
        )

    item_register.save()

    return redirect(url_for('item_registers.index'))