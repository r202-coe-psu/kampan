from calendar import calendar
from crypt import methods
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

module = Blueprint("item_registers", __name__, url_prefix="/item_registers")


def check_in_time(created_date, calendar_select, calendar_end):
    print(
        created_date, calendar_select, calendar_select <= created_date <= calendar_end
    )
    if calendar_select <= created_date <= calendar_end:
        return True
    else:
        return False


@module.route("/", methods=["GET", "POST"])
@login_required
def index():
    item_registers = models.RegistrationItem.objects()
    form = forms.inventories.InventoryForm()

    if request.method == "POST":
        print(form.calendar_select.data)
        print(form.calendar_end.data)

    return render_template(
        "/item_registers/index.html",
        item_registers=item_registers,
        form=form,
        calendar_select=form.calendar_select.data,
        calendar_end=form.calendar_end.data,
        check_in_time=check_in_time,
    )


@module.route(
    "/register", methods=["GET", "POST"], defaults=dict(item_register_id=None)
)
@login_required
def register(item_register_id):
    form = forms.item_registers.ItemRegisterationForm()

    item_register = None
    if item_register_id:
        item_register = models.RegistrationItem.objects().get(id=item_register_id)
        form = forms.item_registers.ItemRegisterationForm(obj=item_register)

    if not form.validate_on_submit():
        return render_template(
            "/item_registers/register.html",
            form=form,
        )

    if not item_register:
        item_register = models.RegistrationItem()

    if form.bill_file.data:
        item_register.bill.put(
            form.bill_file.data,
            filename=form.bill_file.data.filename,
            content_type=form.bill_file.data.content_type,
        )

    form.populate_obj(item_register)
    item_register.user = current_user._get_current_object()
    item_register.save()

    return redirect(url_for("item_registers.index"))


@module.route("/<item_register_id>/edit", methods=["GET", "POST"])
@login_required
def edit(item_register_id):
    item_register = models.RegistrationItem.objects().get(id=item_register_id)
    form = forms.item_registers.ItemRegisterationForm(obj=item_register)

    if not form.validate_on_submit():
        return render_template(
            "/item_registers/register.html",
            form=form,
        )
    if form.bill_file.data:
        if item_register.bill:
            item_register.bill.replace(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )
        else:
            item_register.bill.put(
                form.bill_file.data,
                filename=form.bill_file.data.filename,
                content_type=form.bill_file.data.content_type,
            )
    form.populate_obj(item_register)
    item_register.save()

    return redirect(url_for("item_registers.index"))


@module.route("/<item_register_id>/delete")
@login_required
def delete(item_register_id):
    item_register = models.RegistrationItem.objects().get(id=item_register_id)
    item_register.delete()

    return redirect(url_for("item_registers.index"))
