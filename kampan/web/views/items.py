from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint('items', __name__, url_prefix='/items')

@module.route('/')
@login_required
def index():
    items = models.Item.objects()
    return render_template(
        "/items/index.html",
        items=items,
        )



@module.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    form = forms.items.ItemForm()
    if not form.validate_on_submit():
        return render_template(
            '/items/add.html',
            form=form,           
             )

    item = models.Item(
        name=form.name.data,
        description=form.description.data,
        weight=form.weight.data,
        categories=form.categories.data,
    )

    item.save()

    return redirect(url_for('items.index'))

    