from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    abort,
)
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models

import datetime


module = Blueprint("payment", __name__, url_prefix="/payment")


@module.route("/<procurement_id>", methods=["GET", "POST"])
def index(procurement_id):
    today = datetime.date.today()
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=procurement_id).first()
    if not procurement:
        abort(404)
    print(procurement.id)
    form = forms.procurement.PaymentForm()
    return render_template(
        "procurement/payment/index.html",
        item=procurement,
        organization=organization,
        today=today,
        form=form,
        is_last_period=procurement.is_last_period(),
        remaining_amount=(
            procurement.get_remaining_amount() if procurement.is_last_period() else None
        ),
    )


@module.route("/<procurement_id>/set_paid", methods=["POST"])
@login_required
def set_paid(procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=procurement_id).first()
    if not procurement:
        abort(404)

    form = forms.procurement.PaymentForm()

    if not form.validate_on_submit():
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            form=form,
            today=datetime.date.today(),
            is_last_period=procurement.is_last_period(),
            remaining_amount=(
                procurement.get_remaining_amount()
                if procurement.is_last_period()
                else None
            ),
        )

    amount = form.amount.data
    new_product_number = form.product_number.data

    # --- ตรวจสอบจำนวนเงิน ---
    if procurement.amount is not None and amount > procurement.amount:
        form.amount.errors.append("จำนวนเงินไม่สามารถเกินยอดรวมของโครงการ")
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            form=form,
            today=datetime.date.today(),
            is_last_period=procurement.is_last_period(),
            remaining_amount=(
                procurement.get_remaining_amount()
                if procurement.is_last_period()
                else None
            ),
        )

    # --- ตรวจสอบเลขที่ใบจ่ายเงินซ้ำ ---
    existing = models.Procurement.objects(
        product_number=new_product_number, id__ne=procurement.id
    ).first()
    if existing:
        form.product_number.errors.append("เลขที่ใบจ่ายเงินนี้ถูกใช้งานแล้ว")
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            form=form,
            today=datetime.date.today(),
            is_last_period=procurement.is_last_period(),
            remaining_amount=(
                procurement.get_remaining_amount()
                if procurement.is_last_period()
                else None
            ),
        )

    # --- บันทึกข้อมูลการจ่าย ---
    next_period_index = len(procurement.payment_records)

    final_amount = (
        procurement.get_remaining_amount() if procurement.is_last_period() else amount
    )
    print(f"Final amount: {final_amount}")

    procurement.add_payment_record(
        period_index=next_period_index,
        paid_by=current_user._get_current_object(),
        amount=final_amount,
        product_number=procurement.product_number,
    )

    procurement.paid_period_index = next_period_index
    procurement.payment_status = procurement.get_current_payment_status(
        datetime.date.today()
    )
    procurement.last_updated_by = current_user._get_current_object()

    if new_product_number:
        procurement.product_number = new_product_number

    try:
        procurement.save()
    except Exception:
        form.product_number.errors.append("เลขที่ใบจ่ายเงินนี้ถูกใช้งานแล้ว")
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            form=form,
            today=datetime.date.today(),
            is_last_period=procurement.is_last_period(),
            remaining_amount=(
                procurement.get_remaining_amount()
                if procurement.is_last_period()
                else None
            ),
        )

    return redirect(url_for("procurement.products.index", organization=organization))
