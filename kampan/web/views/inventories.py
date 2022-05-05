from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models

module = Blueprint("inventories", __name__, url_prefix="/inventories")


@module.route("/")
@login_required
def index():
    item_register_id = request.args.get("item_register_id")
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    inventories = models.Inventory.objects(registration=item_register)

    total = total_quantity()
    print(total)

    return render_template(
        "/inventories/index.html",
        inventories=inventories,
        item_register=item_register,
        total=total,
    )


def total_quantity():
    register = models.RegistrationItem.objects()
    quantities = 0

    for item in register:
        item_register = item.id
        inventories = models.Inventory.objects(registration=item_register)

        for item in inventories:
            quantities += item.quantity
    return quantities


@module.route("/register", methods=["GET", "POST"], defaults=dict(inventory_id=None))
@module.route("/<inventory_id>/edit", methods=["GET", "POST"])
@login_required
def register(inventory_id):
    form = forms.inventories.InventoryForm()
    item_register_id = request.args.get("item_register_id")
    # print(item_register_id)
    item_register = models.RegistrationItem.objects.get(id=item_register_id)
    inventory = models.Inventory.objects(registration=item_register)

    # inventory = None
    if inventory_id:
        inventory = models.Inventory.objects(registration=item_register).get(
            id=inventory_id
        )
        form = forms.inventories.InventoryForm(obj=inventory)

    if not form.validate_on_submit():
        return render_template(
            "/inventories/register.html",
            form=form,
            item_register=item_register,
        )

    if not inventory_id:
        inventory = models.Inventory()

    form.populate_obj(inventory)
    inventory.user = current_user._get_current_object()
    inventory.registration = item_register
    inventory.remain = inventory.quantity
    inventory.save()

    return redirect(url_for("inventories.index", item_register_id=item_register.id))
