from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

module = Blueprint('checkin_items', __name__, url_prefix='/checkin_items')

@module.route('/')
@login_required
def index():
    checkin_items = models.CheckinItem.objects()
    return render_template(
        "/checkin_items/index.html",
        checkin_items=checkin_items
        )


@module.route('/checkin', methods=["GET", "POST"], defaults=dict(checkin_item_id=None))
@module.route("/<checkin_item_id>/edit", methods=["GET", "POST"])
@login_required
def register(checkin_item_id):
    form = forms.checkin_items.CheckinItemForm()
    
    checkin_item = None
    if checkin_item_id:
        checkin_item = models.CheckinItem.objects().get(id=checkin_item_id)
        form = forms.checkin_items.CheckinItemForm(obj=checkin_item)

    if not form.validate_on_submit():
        return render_template(
            '/checkin_items/checkin.html',
            form=form,           
            )
    
    if not checkin_item:
        checkin_item = models.CheckinItem()

    form.populate_obj(checkin_item)
    checkin_item.user = current_user._get_current_object()
    checkin_item.save()

    return redirect(url_for('checkin_items.index'))