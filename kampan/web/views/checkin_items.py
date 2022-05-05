from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models

module = Blueprint('checkin_items', __name__, url_prefix='/checkin_items')

@module.route('/')
@login_required
def index():
    item_register_id = request.args.get("item_register_id")
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    checkin_items = models.CheckinItem.objects(registration=item_register)

    total = total_quantity()
    print(total)

    return render_template(
        "/checkin_items/index.html",
        checkin_items=checkin_items,
        item_register=item_register,
        total=total,
        )

def total_quantity():
    register = models.RegistrationItem.objects()
    quantities = 0

    for item in register:
        item_register = item.id
        checkin_items = models.CheckinItem.objects(registration=item_register)

        for item in checkin_items:
            quantities += item.quantity
    return quantities




@module.route('/checkin', methods=["GET", "POST"], defaults=dict(checkin_item_id=None))
@module.route("/<checkin_item_id>/edit", methods=["GET", "POST"])
@login_required
def register(checkin_item_id):
    form = forms.checkin_items.CheckinItemForm()
    item_register_id = request.args.get("item_register_id")
    # print(item_register_id)
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    checkin_item = models.CheckinItem.objects(registration=item_register)

    # checkin_item = None
    if checkin_item_id:
        checkin_item = models.CheckinItem.objects(registration=item_register).get(id=checkin_item_id)
        form = forms.checkin_items.CheckinItemForm(obj=checkin_item)

    if not form.validate_on_submit():
        return render_template(
            '/checkin_items/checkin.html',
            form=form,
            item_register=item_register,
            )
    
    if not checkin_item_id:
        checkin_item = models.CheckinItem()

    form.populate_obj(checkin_item)
    checkin_item.user = current_user._get_current_object()
    checkin_item.registration = item_register
    checkin_item.remain = checkin_item.quantity
    checkin_item.save()

    return redirect(url_for('checkin_items.index', item_register_id=item_register.id))