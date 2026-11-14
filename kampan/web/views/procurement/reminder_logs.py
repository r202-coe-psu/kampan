"""เพิ่ม log การแจ้งเตือนเอง (#30) ประวัติแสดงในหน้ารายละเอียด MA (payment.index)"""

from bson import ObjectId
from flask import Blueprint, abort, flash, g, redirect, url_for
from flask_login import current_user, login_required

from kampan import models
from kampan.web import forms

from . import ma_permissions

module = Blueprint("reminder_logs", __name__, url_prefix="/reminder_logs")

NO_LOG_PERMISSION_MESSAGE = "คุณไม่มีสิทธิ์เพิ่มบันทึกการแจ้งเตือนของ MA รายการนี้"


@module.route("/<procurement_id>/items/<item_id>/manual", methods=["POST"])
@login_required
def create_manual(procurement_id, item_id):
    organization = g.organization
    if not organization:
        abort(404)
    procurement = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)
    if not ObjectId.is_valid(item_id):
        abort(404)
    item = models.ProcurementItem.objects(id=item_id, procurement=procurement, organization=organization).first()
    if not item:
        abort(404)

    detail_url = url_for(
        "procurement.payment.index",
        procurement_id=procurement.id,
        organization_id=organization.id,
        _anchor=f"item-{item.id}",
    )
    if not ma_permissions.can_edit_procurement(procurement, organization):
        flash(NO_LOG_PERMISSION_MESSAGE, "error")
        return redirect(detail_url)

    form = forms.procurement.ManualReminderLogForm()
    if not form.validate_on_submit():
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        flash(errors[0] if errors else "ข้อมูลบันทึกไม่ถูกต้อง", "error")
        return redirect(detail_url)

    recipients = (form.recipients.data or "").strip()
    models.ReminderLog(
        organization=organization,
        procurement=procurement,
        item=item,
        kind="manual",
        status="manual",
        trigger_date=form.get_contact_date(),
        recipients=[recipients] if recipients else [],
        note=form.note.data.strip(),
        created_by=current_user._get_current_object(),
    ).save()
    flash("เพิ่มบันทึกการแจ้งเตือนเรียบร้อยแล้ว", "success")
    return redirect(detail_url)
