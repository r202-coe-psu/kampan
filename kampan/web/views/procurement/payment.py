"""หน้ารายละเอียด MA (หัวสัญญา + รายการย่อย + งวด) และการบันทึกจ่ายรายงวด"""

import datetime

from bson import ObjectId
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from kampan import models
from kampan.web import forms

from . import ma_permissions

module = Blueprint("payment", __name__, url_prefix="/payment")

NO_PAYMENT_PERMISSION_MESSAGE = "คุณไม่มีสิทธิ์บันทึกการจ่ายของ MA รายการนี้"
DUPLICATE_PAYMENT_NUMBER_MESSAGE = "เลขที่เอกสาร {number} ถูกใช้งานแล้วในหน่วยงานนี้"
INVALID_REQUEST_MESSAGE = "คำขอไม่ถูกต้องหรือหมดอายุ กรุณาโหลดหน้าใหม่แล้วลองอีกครั้ง"
INSTALLMENT_NOT_UPDATED_MESSAGE = "ไม่พบงวดนี้ หรือข้อมูลถูกแก้ไขแล้ว"


def _get_procurement_or_404(procurement_id):
    organization = g.organization
    if not organization:
        abort(404)
    return organization, ma_permissions.get_visible_procurement_or_404(procurement_id, organization)


def _safe_next_url(next_url, default):
    """รับเฉพาะ path ภายในเว็บ (กัน open redirect เช่น //evil.com หรือ /\\evil.com)"""
    if not next_url or not next_url.startswith("/") or next_url.startswith(("//", "/\\")):
        return default
    return next_url


def _detail_url(procurement, organization):
    return url_for("procurement.payment.index", procurement_id=procurement.id, organization_id=organization.id)


@module.route("/<procurement_id>", methods=["GET"])
@login_required
def index(procurement_id):
    organization, procurement = _get_procurement_or_404(procurement_id)
    if procurement.status == "draft":
        flash("รายการนี้เป็นแบบร่าง กรุณาแก้ไขต่อหรือบันทึกเพื่อเปิดใช้งาน", "info")
        return redirect(
            url_for("procurement.products.edit", procurement_id=procurement.id, organization_id=organization.id)
        )

    # สายการต่ออายุ (#32): MA ในสายที่ผู้ใช้มองไม่เห็นแสดงแค่ว่ามีอยู่ ไม่แสดงชื่อและไม่มีลิงก์
    chain = procurement.get_renewal_chain()
    position = chain.index(procurement)
    visible_chain_ids = set(
        ma_permissions.visible_procurements(organization).filter(id__in=[ma.id for ma in chain]).scalar("id")
    )
    member = ma_permissions.get_member(organization)
    items = procurement.get_items()
    can_approve = ma_permissions.can_approve_renewal(organization)
    return render_template(
        "procurement/payment/index.html",
        procurement=procurement,
        items=items,
        organization=organization,
        today=datetime.date.today(),
        can_edit=ma_permissions.can_edit_procurement(procurement, organization),
        can_request_renewal=ma_permissions.can_request_renewal(procurement, organization),
        can_approve_renew=can_approve
        and ma_permissions.renewal_requested_as(procurement, "renew")
        and not procurement.is_renewed(),
        can_approve_stop=can_approve and ma_permissions.renewal_requested_as(procurement, "stop"),
        form=forms.procurement.InstallmentPaymentForm(formdata=None),
        renewal_chain=chain,
        renewed_from_ma=chain[position - 1] if position > 0 else None,
        renewed_to_ma=chain[position + 1] if position + 1 < len(chain) else None,
        visible_chain_ids=visible_chain_ids,
        my_division_id=member.division.id if member and member.division else None,
        reminder_logs=_reminder_logs_by_item(procurement, organization),
        manual_log_form=forms.procurement.ManualReminderLogForm(formdata=None),
        offset_labels=dict(models.ALL_PAYMENT_OFFSET_CHOICES),
        pay_log_users=_pay_log_users(items),
    )


def _pay_log_users(items) -> dict:
    """ผู้กดจ่ายในประวัติของทุกงวด {user_id: User} ด้วย query เดียว (ไม่ dereference ทีละรายการ)"""
    user_ids = {
        entry.get_by_id()
        for item in items
        for installment in item._data.get("installments") or []
        for entry in installment._data.get("pay_log") or []
    } - {None}
    return {user.id: user for user in models.User.objects(id__in=list(user_ids))} if user_ids else {}


def _reminder_logs_by_item(procurement, organization) -> dict:
    """ประวัติการแจ้งเตือนของ MA นี้ แยกตามรายการย่อย ใหม่สุดก่อน {item_id: [log, ...]}"""
    logs_by_item = {}
    logs = models.ReminderLog.objects(organization=organization, procurement=procurement).order_by("-created_date")
    for log in logs:
        logs_by_item.setdefault(log._data["item"].id, []).append(log)
    return logs_by_item


def _get_installment_for_change(procurement_id, item_id, installment_id):
    """โหลด MA / รายการย่อย / งวด (scope ด้วยหน่วยงาน ไม่พบ = 404) แล้วตรวจสิทธิ์ผู้แก้ไข MA ได้"""
    organization, procurement = _get_procurement_or_404(procurement_id)
    if procurement.status == "draft":
        abort(400)
    if not ObjectId.is_valid(item_id) or not ObjectId.is_valid(installment_id):
        abort(404)
    item = models.ProcurementItem.objects(id=item_id, procurement=procurement, organization=organization).first()
    if not item:
        abort(404)
    installment = item.get_installment(installment_id)
    if not installment:
        abort(404)
    allowed = ma_permissions.can_edit_procurement(procurement, organization)
    return organization, procurement, item, installment, allowed


def _payment_number_taken(organization, number: str, item, installment) -> bool:
    """เลขที่เอกสารซ้ำกับงวดอื่นในหน่วยงานเดียวกันไหม (ซ้ำข้ามหน่วยงานได้)"""
    for other in models.ProcurementItem.objects(organization=organization, installments__payment_number=number).only(
        "installments"
    ):
        for other_installment in other.installments:
            if other_installment.payment_number != number:
                continue
            if other.id == item.id and other_installment._id == installment._id:
                continue
            return True
    return False


def _update_installment(organization, item, installment, log_entry, **values) -> bool:
    """แก้งวดเดียวแบบ atomic ด้วย positional operator (ไม่เขียนทับงวด / รายการย่อยที่คนอื่นแก้พร้อมกัน)
    และต่อประวัติการกด (``log_entry``) ในการเขียนครั้งเดียวกัน"""
    updates = {f"set__installments__S__{name}": value for name, value in values.items()}
    # ต่อประวัติด้วย $set ทั้ง array (ไม่ใช้ $push แบบ positional เพราะ mongomock ของเทสต์ไม่รองรับ)
    # กดพร้อมกันบนงวดเดียวกันอาจเหลือประวัติแค่รายการเดียว สถานะจ่ายของงวดยังถูกต้อง
    updates["set__installments__S__pay_log"] = [*installment.pay_log, log_entry]
    return bool(
        models.ProcurementItem.objects(
            id=item.id,
            organization=organization,
            __raw__={"installments._id": installment._id},
        ).update_one(
            set__last_updated_by=current_user._get_current_object(),
            set__updated_date=datetime.datetime.now(),
            **updates,
        )
    )


@module.route("/<procurement_id>/items/<item_id>/installments/<installment_id>/pay", methods=["POST"])
@login_required
def pay_installment(procurement_id, item_id, installment_id):
    organization, procurement, item, installment, allowed = _get_installment_for_change(
        procurement_id, item_id, installment_id
    )
    detail_url = _detail_url(procurement, organization)
    next_url = request.form.get("next") or request.args.get("next")
    redirect_url = _safe_next_url(next_url, detail_url)
    if not allowed:
        flash(NO_PAYMENT_PERMISSION_MESSAGE, "error")
        return redirect(redirect_url)

    form = forms.procurement.InstallmentPaymentForm()
    if not form.validate_on_submit():
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        flash(errors[0] if errors else "ข้อมูลการจ่ายไม่ถูกต้อง", "error")
        return redirect(redirect_url)

    payment_number = (form.payment_number.data or "").strip() or None
    if payment_number and _payment_number_taken(organization, payment_number, item, installment):
        flash(DUPLICATE_PAYMENT_NUMBER_MESSAGE.format(number=payment_number), "error")
        return redirect(redirect_url)

    was_paid = installment.is_paid()
    user = current_user._get_current_object()
    paid_date = datetime.datetime.combine(form.paid_date.data, datetime.time.min)
    log_entry = models.PayLogEntry(
        action="edited" if was_paid else "paid",
        pressed_at=datetime.datetime.now(),
        paid_date=paid_date,
        by=user,
        payment_number=payment_number,
        paid_amount=form.paid_amount.data,
    )
    updated = _update_installment(
        organization,
        item,
        installment,
        log_entry,
        paid_date=paid_date,
        paid_by=user,
        payment_number=payment_number,
        paid_amount=form.paid_amount.data,
    )
    if not updated:
        flash(INSTALLMENT_NOT_UPDATED_MESSAGE, "error")
        return redirect(redirect_url)
    flash(
        "แก้ไขข้อมูลการจ่ายงวดเรียบร้อยแล้ว" if was_paid else "บันทึกการจ่ายงวดเรียบร้อยแล้ว",
        "success",
    )
    return redirect(redirect_url)


@module.route("/<procurement_id>/items/<item_id>/installments/<installment_id>/unpay", methods=["POST"])
@login_required
def unpay_installment(procurement_id, item_id, installment_id):
    organization, procurement, item, installment, allowed = _get_installment_for_change(
        procurement_id, item_id, installment_id
    )
    detail_url = _detail_url(procurement, organization)
    next_url = request.form.get("next") or request.args.get("next")
    redirect_url = _safe_next_url(next_url, detail_url)
    if not allowed:
        flash(NO_PAYMENT_PERMISSION_MESSAGE, "error")
        return redirect(redirect_url)
    if not forms.procurement.ConfirmActionForm().validate_on_submit():
        flash(INVALID_REQUEST_MESSAGE, "error")
        return redirect(redirect_url)

    log_entry = models.PayLogEntry(
        action="unpaid",
        pressed_at=datetime.datetime.now(),
        paid_date=installment.paid_date,
        by=current_user._get_current_object(),
        payment_number=installment.payment_number,
        paid_amount=installment.paid_amount,
    )
    updated = _update_installment(
        organization,
        item,
        installment,
        log_entry,
        paid_date=None,
        paid_by=None,
        payment_number=None,
        paid_amount=None,
    )
    if not updated:
        flash(INSTALLMENT_NOT_UPDATED_MESSAGE, "error")
        return redirect(redirect_url)
    flash("ยกเลิกการบันทึกจ่ายงวดแล้ว", "success")
    return redirect(redirect_url)
