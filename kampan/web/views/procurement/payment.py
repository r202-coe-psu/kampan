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
from flask import redirect, url_for
from decimal import Decimal, InvalidOperation


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

    errors, form_data = {}, {}

    # --- รับค่า input ---
    new_product_number = request.form.get("product_number")
    amount_input = request.form.get("amount")
    form_data["product_number"] = new_product_number
    form_data["amount"] = amount_input

    # --- ตรวจสอบจำนวนเงิน ---
    try:
        amount = Decimal(amount_input or "0")
        if amount <= 0:
            errors["amount"] = "จำนวนเงินต้องมากกว่า 0"
        elif procurement.amount is not None and amount > procurement.amount:
            errors["amount"] = "จำนวนเงินไม่สามารถเกินยอดรวมของโครงการ"
    except (InvalidOperation, ValueError):
        errors["amount"] = "จำนวนเงินไม่ถูกต้อง"

    # --- ตรวจสอบเลขที่ใบจ่ายเงินซ้ำ (กันชนกับตัวเอง) ---
    existing = models.Procurement.objects(
        product_number=new_product_number, id__ne=procurement.id
    ).first()
    if existing:
        errors["product_number"] = "เลขที่ใบจ่ายเงินนี้ถูกใช้งานแล้ว"

    # --- ถ้ามี error แสดงผลกลับ ---
    if errors:
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            errors=errors,
            form_data=form_data,
            today=datetime.date.today(),
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

    # --- อัปเดตยอดและสถานะ ---
    procurement.paid_period_index = next_period_index
    procurement.payment_status = procurement.get_current_payment_status(
        datetime.date.today()
    )
    procurement.last_updated_by = current_user._get_current_object()

    if new_product_number:
        procurement.product_number = new_product_number

    try:
        procurement.save()
    except:
        errors["product_number"] = "เลขที่ใบจ่ายเงินนี้ถูกใช้งานแล้ว"
        return render_template(
            "procurement/payment/index.html",
            item=procurement,
            organization=organization,
            errors=errors,
            form_data=form_data,
            today=datetime.date.today(),
        )

    return redirect(url_for("procurement.products.index", organization=organization))
