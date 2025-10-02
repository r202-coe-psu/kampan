from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models

import datetime
import decimal


module = Blueprint("payment", __name__, url_prefix="/payment")


@module.route("/<procurement_id>", methods=["GET", "POST"])
def index(procurement_id):
    today = datetime.date.today()
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=procurement_id).first()
    if not procurement:
        abort(404)
    print(procurement.id)
    return render_template(
        "procurement/payment/index.html",
        item=procurement,
        organization=organization,
        today=today,
    )


@module.route("/<procurement_id>/set_paid", methods=["POST"])
@login_required
def set_paid(procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=procurement_id).first()
    next_period_index = len(procurement.payment_records)
    new_product_number = request.form.get("product_number")
    amount = request.form.get("amount", type=decimal.Decimal)

    # Save old product_number in payment record before updating
    procurement.add_payment_record(
        period_index=next_period_index,
        paid_by=current_user._get_current_object(),
        amount=amount,
        product_number=procurement.product_number,
    )
    # หัก amount ที่จ่ายออกจากยอดรวม
    if procurement.amount is not None and amount is not None:
        procurement.amount -= amount

    procurement.paid_period_index = next_period_index
    procurement.payment_status = procurement.get_current_payment_status(
        datetime.date.today()
    )
    procurement.last_updated_by = current_user._get_current_object()

    # Update product_number if new value is provided
    if new_product_number:
        procurement.product_number = new_product_number

    procurement.save()
    return redirect(url_for("procurement.products.index", organization=organization))
