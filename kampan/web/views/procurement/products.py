import logging
import datetime
from collections import Counter
from decimal import Decimal
from io import BytesIO

import mongoengine as me
import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
    g,
)
from flask_login import current_user, login_required
from mongoengine.queryset.visitor import Q

from kampan import models
from kampan.models.procurement import _reference_id, payment_statuses, procurement_ids_of, renewal_status_statuses
from kampan.utils import ma_assignments
from kampan.utils.date_utils import format_thai_date_input
from kampan.web import acl, forms
from kampan.web.forms.procurement import PSU_NUMBER_REQUIRED_MESSAGE

from . import ma_permissions
from .ma_pagination import paginate_sorted, resolve_sort

logger = logging.getLogger(__name__)

module = Blueprint("products", __name__, url_prefix="/products")

NO_EDIT_PERMISSION_MESSAGE = "คุณไม่มีสิทธิ์แก้ไข MA รายการนี้"
NO_RENEW_PERMISSION_MESSAGE = "คุณไม่มีสิทธิ์ต่ออายุ MA รายการนี้"
ALREADY_RENEWED_MESSAGE = "MA รายการนี้ต่ออายุไปแล้ว"
NOT_RENEWAL_APPROVER_MESSAGE = "เฉพาะเจ้าหน้าที่พัสดุ (admin) เท่านั้นที่อนุมัติการต่ออายุได้"
RENEW_NOT_REQUESTED_MESSAGE = "ผู้รับผิดชอบยังไม่ได้ขอต่ออายุ MA รายการนี้ หรือสถานะเปลี่ยนไปแล้ว"
ITEM_FORM_MISMATCH_MESSAGE = "ข้อมูลรายการย่อยไม่ตรงกับรายการที่เลือกแก้ไข กรุณาเปิดหน้าแก้ไขใหม่"
STALE_FORM_MESSAGE = "MA นี้ถูกแก้ไขหรือบันทึกจ่ายงวดโดยผู้อื่นหลังจากคุณเปิดฟอร์ม กรุณาเปิดหน้าแก้ไขใหม่แล้วบันทึกอีกครั้ง"


def calculate_months_days(start_date, end_date):
    """Calculate the number of months and days between two dates."""
    if not start_date or not end_date:
        return None, None
    start = start_date.date() if hasattr(start_date, "date") else start_date
    end = end_date.date() if hasattr(end_date, "date") else end_date

    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day >= start.day:
        days = end.day - start.day
    else:
        months -= 1
        from calendar import monthrange

        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month != 1 else end.year - 1
        last_day_prev_month = monthrange(prev_year, prev_month)[1]
        days = last_day_prev_month - start.day + end.day
    return months, days


# สถานะการต่ออายุที่กรองในรายการ MA ได้ (แบบร่างแยกอยู่ที่ปุ่ม "แบบร่าง")
FILTERABLE_RENEWAL_STATUSES = ("review", "renewal-requested", "renewed", "disactive")


def search_procurements(procurements, organization, text: str):
    """ค้นด้วยเลขที่ ม.อ.เบิกจ่าย, ชื่อหัวสัญญา, ชื่อรายการย่อย หรือยี่ห้อ / รุ่น / รายละเอียดของแถวย่อย (scope ด้วยหน่วยงาน)"""
    text = (text or "").strip()
    if not text:
        return procurements
    item_matches = models.ProcurementItem.objects(organization=organization).filter(
        Q(name__icontains=text)
        | Q(sub_items__brand__icontains=text)
        | Q(sub_items__model_name__icontains=text)
        | Q(sub_items__serial_number__icontains=text)
        | Q(sub_items__asset_code__icontains=text)
        | Q(sub_items__details__icontains=text)
    )
    return procurements.filter(
        Q(psu_disbursement_number__icontains=text)
        | Q(name__icontains=text)
        | Q(id__in=procurement_ids_of(item_matches))
    )


@module.route("", methods=["GET", "POST"])
@login_required
def index():
    form = forms.procurement.ProductFilterForm(request.args)
    organization = g.organization
    if not organization:
        abort(404)
    today = datetime.date.today()
    category = request.args.get("category")
    payment_status = request.args.get("payment_status")
    usage_status = request.args.get("usage_status")
    renewal_status = request.args.get("renewal_status")
    upload_success = request.args.get("upload_success", "")

    only_my_division = request.args.get("division") == "mine"
    visible_qs = ma_permissions.visible_procurements(organization, only_my_division=only_my_division)

    # แบบร่างแยกออกจากตาราง แสดงเป็นตัวเลือกตอนกด "เพิ่ม MA" (เฉพาะแบบร่างที่ผู้ใช้แก้ไขได้)
    can_edit = ma_permissions.edit_checker(organization)
    drafts = [
        draft
        for draft in visible_qs.filter(status="draft", parent_procurement=None).order_by("-updated_date").limit(50)
        if can_edit(draft)
    ][:10]
    visible_qs = visible_qs.filter(status__ne="draft")

    # หากสัญญาหลักมีการ duplicate แยกรายการย่อยออกไปแล้ว ให้แสดงเฉพาะรายการย่อยที่แยกออกมาในตาราง
    parent_ids = list({
        _reference_id(child, "parent_procurement")
        for child in models.Procurement.objects(
            organization=organization, parent_procurement__ne=None
        ).only("parent_procurement")
    } - {None})
    if parent_ids:
        visible_qs = visible_qs.filter(id__nin=parent_ids)

    # ตัวนับสถานะนับจาก MA ที่เห็นทั้งหมด ไม่ขึ้นกับคำค้นหรือ filter
    statuses = payment_statuses(visible_qs.scalar("id"), organization, today)
    status_count = Counter(statuses.values())
    status_count = {status: status_count.get(status, 0) for status, _ in models.PAYEMENT_STATUS_CHOICES}

    procurement_qs = search_procurements(visible_qs, organization, request.args.get("name"))
    if category:
        category_items = models.ProcurementItem.objects(organization=organization, category=category)
        procurement_qs = procurement_qs.filter(id__in=procurement_ids_of(category_items))
    if payment_status:
        procurement_qs = procurement_qs.filter(
            id__in=[procurement_id for procurement_id, status in statuses.items() if status == payment_status]
        )
    if usage_status in dict(models.USAGE_STATUS_CHOICES):
        procurement_qs = procurement_qs.filter(usage_status=usage_status)
    if renewal_status in FILTERABLE_RENEWAL_STATUSES:
        procurement_qs = procurement_qs.filter(status__in=renewal_status_statuses(renewal_status))

    sort = resolve_sort("created_desc")
    form.sort.data = sort
    paginated_procurements, procurements = paginate_sorted(procurement_qs, organization, sort, default_per_page=6)

    for procurement in procurements:
        end_date = procurement.get_end_date()
        procurement.is_expired = bool(end_date and end_date.date() < today)
        months, days = (None, None) if procurement.is_expired else calculate_months_days(today, end_date)
        procurement.duration_months = months
        procurement.duration_days = days

    return render_template(
        "/procurement/products/index.html",
        organization=organization,
        procurements=procurements,
        paginated_procurements=paginated_procurements,
        form=form,
        today=today,
        upload_success=upload_success,
        status_count=status_count,
        can_edit=can_edit,
        drafts=drafts,
        my_division=ma_permissions.my_division_filter(organization),
        only_my_division=only_my_division,
    )


# ---------------------------------------------------------------------------
# ฟอร์มสร้าง / แก้ไข MA
# ---------------------------------------------------------------------------


def _member_choices(organization) -> list[tuple[str, str]]:
    members = models.OrganizationUserRole.objects(organization=organization, status="active")
    return [(str(member.id), member.display_user_fullname()) for member in members]


def _division_choices(organization, extra_division_ids=()) -> list[tuple[str, str]]:
    query = models.Division.objects(organization=organization)
    divisions = list(query.filter(status="active").order_by("name"))
    active_ids = {division.id for division in divisions}
    if extra_division_ids:
        missing_ids = [did for did in extra_division_ids if did not in active_ids]
        if missing_ids:
            extra = list(query.filter(id__in=missing_ids).order_by("name"))
            divisions.extend(extra)
    return [(str(division.id), division.name) for division in divisions]


def _as_date(value):
    return value.date() if isinstance(value, datetime.datetime) else value


def _as_datetime(value):
    if value is None:
        return None
    return datetime.datetime.combine(value, datetime.time.min)


def _blank_item_data(member) -> dict:
    my_division_id = str(member.division.id) if member and getattr(member, "division", None) else None
    return {
        "quantity": 1,
        "unit": "",
        "unit_price": None,
        "responsible_divisions": [my_division_id] if my_division_id else [],
        "responsible_by": [str(member.id)] if member else [],
        "reminder_kind": "ma",
        "expiry_reminder_offsets": list(models.DEFAULT_REMINDER_OFFSETS),
        "payment_reminder_offsets": list(models.DEFAULT_PAYMENT_REMINDER_OFFSETS),
        "has_sub_item_sn": False,
        "has_sub_item_asset": False,
        "sub_items": [{}],
        "installment_mode": False,
        "installments": [{}],
    }


def _reminder_settings_data(item, include_custom_dates: bool = True) -> dict:
    data = {
        "expiry_reminder_offsets": list(item.expiry_reminder_offsets or []),
        "payment_reminder_offsets": [
            value for value in item.payment_reminder_offsets or [] if value in dict(models.PAYMENT_REMINDER_OFFSET_CHOICES)
        ],
        "reminder_offsets_days": [str(days) for days in item.reminder_offsets_days or []],
    }
    if include_custom_dates:
        data["custom_reminder_dates"] = [format_thai_date_input(value) for value in item.custom_reminder_dates or []]
    return data


def _sub_items_form_data(item) -> list[dict]:
    return [
        {
            "brand": row.brand,
            "model_name": row.model_name,
            "serial_number": row.serial_number or (row.get_serial_number() if hasattr(row, "get_serial_number") else ""),
            "asset_code": row.asset_code or (row.get_asset_code() if hasattr(row, "get_asset_code") else ""),
            "details": row.details,
        }
        for row in item.sub_items
    ]


def _build_sub_items(sub_item_entries) -> list:
    """แถวที่ว่างทุกช่องไม่บันทึก"""
    return [
        models.ItemDetail(
            brand=(entry.form.brand.data or "").strip() or None,
            model_name=(entry.form.model_name.data or "").strip() or None,
            serial_number=(entry.form.serial_number.data or "").strip() or None,
            asset_code=(entry.form.asset_code.data or "").strip() or None,
            details=(entry.form.details.data or "").strip() or None,
        )
        for entry in sub_item_entries
        if not entry.form.is_blank()
    ]


def _item_form_data(item) -> dict:
    return {
        "item_id": str(item.id),
        "name": item.name,
        "category": item.category,
        "quantity": getattr(item, "quantity", 1) or 1,
        "unit": getattr(item, "unit", "") or "",
        "account_code": item.account_code or "",
        "start_date": _as_date(item.start_date),
        "end_date": _as_date(item.end_date),
        "amount": item.amount,
        "has_sub_item_sn": item.has_sn(),
        "has_sub_item_asset": item.has_asset(),
        "sub_items": _sub_items_form_data(item),
        "winner": item.winner,
        "unit_price": item.unit_price,
        "note": item.note,
        "responsible_divisions": [str(div.id) for div in item.responsible_divisions or [] if div],
        "responsible_by": [str(member_id) for member_id in item.get_responsible_ids()],
        "reminder_kind": item.reminder_kind,
        "requires_activation": item.requires_activation,
        **_reminder_settings_data(item),
        "installment_mode": item.pays_in_installments(),
        "installments": [
            {
                "installment_id": str(installment._id),
                "due_date": _as_date(installment.due_date),
                "amount": installment.amount,
            }
            for installment in item.get_sorted_installments()
        ],
    }


def _renew_item_data(item, active_member_ids: set) -> dict:
    """รายการย่อยของ MA ใหม่ที่ต่ออายุจาก ``item``

    เว้นว่างวันเริ่ม-สิ้นสุด และไม่ copy งวด / สถานะการจ่าย (เหลือ 1 งวดว่างให้กรอก)
    copy ค่าตั้งการเตือน (ช่วงเตือนและจำนวนวันที่กรอกเอง) แต่ไม่ copy วันที่เตือนเจาะจง เพราะเป็นวันของสัญญาเดิม
    """
    return {
        "name": item.name,
        "category": item.category,
        "quantity": getattr(item, "quantity", 1) or 1,
        "unit": getattr(item, "unit", "") or "",
        "account_code": item.account_code or "",
        "amount": item.amount,
        "has_sub_item_sn": item.has_sn(),
        "has_sub_item_asset": item.has_asset(),
        "sub_items": _sub_items_form_data(item),
        "winner": item.winner,
        "unit_price": item.unit_price,
        "note": item.note,
        "responsible_divisions": [str(div.id) for div in item.responsible_divisions or [] if div],
        # ผู้รับผิดชอบที่ออกจากหน่วยงานแล้วเลือกไม่ได้ จึงไม่ copy
        "responsible_by": [str(member_id) for member_id in item.get_responsible_ids() if member_id in active_member_ids],
        "reminder_kind": item.reminder_kind,
        "requires_activation": item.requires_activation,
        **_reminder_settings_data(item, include_custom_dates=False),
        "installment_mode": False,
        "installments": [{}],
    }


def _renew_form_data(organization, old, target_item=None) -> dict:
    """ข้อมูลตั้งต้นของฟอร์มต่ออายุ: หัวสัญญาและรายการย่อย 1 รายการจาก MA เดิม เว้นว่างเลขที่ ม.อ.เบิกจ่าย"""
    active_member_ids = set(
        models.OrganizationUserRole.objects(organization=organization, status="active").scalar("id")
    )
    items = old.get_items()
    if target_item is None and items:
        target_item = items[0]

    renew_items = [_renew_item_data(target_item, active_member_ids)] if target_item else []
    total_amount = target_item.amount if target_item else old.total_amount
    name = old.name
    if target_item and len(items) > 1 and target_item.name not in old.name:
        name = f"{old.name} - {target_item.name}"

    return {
        "name": name,
        "company": old.company,
        "total_amount": total_amount,
        "items": renew_items,
    }


def _build_form(
    organization, procurement=None, member=None, renew_from=None, target_item=None, is_draft=False, mode="full"
) -> forms.procurement.ProcurementHeaderForm:
    """mode: full / header / item ดู ProcurementHeaderForm (header และ item ใช้กับการแก้ MA ที่ไม่ใช่แบบร่างเท่านั้น)"""
    if request.method == "POST":
        form = forms.procurement.ProcurementHeaderForm(is_draft=is_draft, mode=mode)
    elif renew_from:
        form = forms.procurement.ProcurementHeaderForm(
            formdata=None, data=_renew_form_data(organization, renew_from, target_item=target_item), is_draft=is_draft
        )
    elif procurement:
        form = forms.procurement.ProcurementHeaderForm(
            formdata=None,
            data={
                "psu_disbursement_number": procurement.psu_disbursement_number,
                "disbursement_date": _as_date(procurement.disbursement_date),
                "name": procurement.name,
                "company": procurement.company,
                "total_amount": procurement.total_amount,
                "items": [_item_form_data(item) for item in (procurement.get_items() if mode != "item" else [target_item])],
                "version": procurement.get_version(),
            },
            is_draft=is_draft,
            mode=mode,
        )
    else:
        form = forms.procurement.ProcurementHeaderForm(formdata=None, data={"items": [_blank_item_data(member)]}, is_draft=is_draft)
    form.set_member_choices(_member_choices(organization))
    extra_division_ids = []
    source_items = _source_items(procurement, renew_from, target_item, mode)
    for it in source_items:
        for div in it.responsible_divisions or []:
            if div:
                extra_division_ids.append(getattr(div, "id", div))
    form.set_division_choices(_division_choices(organization, extra_division_ids))
    return form


def _source_items(procurement, renew_from, target_item, mode="full") -> list:
    if mode == "item":
        return [target_item]
    if procurement:
        return procurement.get_items()
    if target_item:
        return [target_item]
    return renew_from.get_items() if renew_from else []


def _render_form(
    form, organization, member, procurement=None, form_errors=(), renew_from=None, target_item=None, mode="full"
):
    choices = _member_choices(organization)
    extra_division_ids = []
    source_items = _source_items(procurement, renew_from, target_item, mode)
    for it in source_items:
        for div in it.responsible_divisions or []:
            if div:
                extra_division_ids.append(getattr(div, "id", div))
    division_choices = _division_choices(organization, extra_division_ids)
    item_prototype = forms.procurement.ProcurementItemForm(
        formdata=None, prefix="items-__I__-", data=_blank_item_data(member)
    )
    item_prototype.responsible_by.choices = choices
    item_prototype.responsible_divisions.choices = division_choices
    installment_prototype = forms.procurement.InstallmentForm(formdata=None, prefix="items-__I__-installments-__J__-")
    return render_template(
        "/procurement/products/create.html",
        form=form,
        organization=organization,
        procurement=procurement,
        item_prototype=item_prototype,
        installment_prototype=installment_prototype,
        form_errors=[error for error in form_errors if error],
        renew_from=renew_from,
        target_item=target_item,
        mode=mode,
    )


class InstallmentChangeError(Exception):
    """แก้งวดตามฟอร์มไม่ได้ (เช่นลบงวดที่จ่ายแล้ว) ข้อความใช้แสดงในฟอร์ม"""


INSTALLMENT_OUT_OF_RANGE_MESSAGE = "{item}: งวดครบกำหนด {due} อยู่นอกช่วงของรายการย่อย ({start} - {end}) กรุณาเลือกวันที่ในช่วงสัญญา"
PAID_INSTALLMENT_REMOVED_MESSAGE = "งวดที่จ่ายแล้วลบไม่ได้ ({item}: งวดครบกำหนด {due})"
PAID_INSTALLMENTS_MODE_OFF_MESSAGE = "{item}: มีงวดที่จ่ายแล้ว ปิดการแบ่งจ่ายเป็นงวดไม่ได้ (จะทำให้ประวัติการจ่ายหาย)"


def _due_label(installment) -> str:
    due = _as_date(installment.due_date)
    return f"{due.day:02d}/{due.month:02d}/{due.year + 543}" if due else "-"


def _check_installments_within_item_period(item) -> None:
    """วันครบกำหนดของงวดต้องอยู่ในช่วงเริ่มต้น-สิ้นสุดของรายการย่อย (งวดที่จ่ายแล้วเป็นประวัติ ไม่ตรวจ)"""
    start, end = _as_date(item.start_date), _as_date(item.end_date)
    for installment in item.installments:
        due = _as_date(installment.due_date)
        if installment.is_paid() or not due:
            continue
        if (start and due < start) or (end and due > end):
            raise InstallmentChangeError(
                INSTALLMENT_OUT_OF_RANGE_MESSAGE.format(
                    item=item.name,
                    due=_due_label(installment),
                    start=_due_label(models.Installment(due_date=item.start_date)) if start else "-",
                    end=_due_label(models.Installment(due_date=item.end_date)) if end else "-",
                )
            )


def _build_installments(item_name, installment_entries, existing_installments) -> list:
    """งวดจากฟอร์ม (โหมดแบ่งงวด) จับคู่กับงวดเดิมด้วย installment_id เก็บสถานะการจ่ายและประวัติของงวดเดิมไว้เหมือนเดิม
    งวดเดิมที่ไม่ได้ส่งมาลบได้เฉพาะที่ยังไม่จ่าย"""
    existing = {str(installment._id): installment for installment in existing_installments}
    installments = []
    for entry in installment_entries:
        installment = existing.pop(entry.form.installment_id.data or "", None) or models.Installment()
        installment.due_date = _as_datetime(entry.form.due_date.data)
        installment.amount = entry.form.amount.data
        installments.append(installment)
    for removed in existing.values():
        if removed.is_paid():
            raise InstallmentChangeError(PAID_INSTALLMENT_REMOVED_MESSAGE.format(item=item_name, due=_due_label(removed)))
    return installments


def _build_items(form, organization, existing_items, user, is_draft=False, fallback_name=None):
    """แปลงฟอร์มเป็นรายการย่อย คืน (รายการที่จะบันทึก, รายการเดิมที่ถูกลบออกจากฟอร์ม)

    item_id ในฟอร์มใช้ได้เฉพาะ id ของรายการย่อยใน MA นี้ id อื่นถือเป็นรายการใหม่
    """
    existing = {str(item.id): item for item in existing_items}
    member_ids = {member_id for entry in form.item_entries() for member_id in entry.form.responsible_by.data or []}
    members = {
        str(member.id): member
        for member in models.OrganizationUserRole.objects(
            id__in=list(member_ids), organization=organization, status="active"
        )
    }
    items = []
    for entry in form.item_entries():
        data = entry.form
        item = existing.pop(data.item_id.data or "", None) or models.ProcurementItem(created_by=user)
        raw_name = (data.name.data or "").strip()
        item.name = raw_name or (fallback_name or form.name.data or "รายการ 1").strip()
        item.category = data.category.data or "ma"
        item.quantity = data.quantity.data or 1
        item.unit = (data.unit.data or "").strip()
        item.account_code = data.account_code.data or None
        item.start_date = _as_datetime(data.start_date.data) if data.start_date.data else None
        item.end_date = _as_datetime(data.end_date.data) if data.end_date.data else None
        item.amount = data.amount.data if data.amount.data is not None else Decimal("0")
        item.has_sub_item_sn = bool(data.has_sub_item_sn.data)
        item.has_sub_item_asset = bool(data.has_sub_item_asset.data)
        item.sub_items = _build_sub_items(data.sub_items)
        item.winner = (data.winner.data or "").strip() or None
        item.unit_price = data.unit_price.data
        item.note = data.note.data or ""
        item.responsible_divisions = []
        item.has_custom_responsible_divisions = False
        item.responsible_by = [members[member_id] for member_id in data.responsible_by.data or [] if member_id in members]
        item.reminder_kind = data.reminder_kind.data or "ma"
        item.requires_activation = bool(data.requires_activation.data)
        item.expiry_reminder_offsets = list(data.expiry_reminder_offsets.data or [])
        # จ่ายครั้งเดียว: ช่องเตือนล่วงหน้าถูกซ่อน (ไม่ส่งค่ามา) จึงไม่มีช่วงล่วงหน้า เตือนเฉพาะวันครบกำหนด
        item.payment_reminder_offsets = list(data.payment_reminder_offsets.data or []) if data.installment_mode.data else []
        item.reminder_offsets_days = data.get_reminder_offsets_days()
        item.custom_reminder_dates = data.get_custom_reminder_dates()
        was_paying = item.pays_in_installments()
        item.installment_mode = bool(data.installment_mode.data)
        if item.installment_mode:
            item.installments = _build_installments(item.name, data.installments, item.installments)
            _check_installments_within_item_period(item)
        else:
            # ไม่แบ่งงวด = ไม่มีการจ่าย: ไม่เก็บงวด (แถวที่ส่งมาและงวดเดิมถูกทิ้ง) แต่ห้ามทิ้งงวดที่จ่ายแล้ว (ประวัติการจ่าย)
            if was_paying and any(installment.is_paid() for installment in item.installments):
                raise InstallmentChangeError(PAID_INSTALLMENTS_MODE_OFF_MESSAGE.format(item=item.name))
            item.installments = []
        item.last_updated_by = user
        items.append(item)
    return items, list(existing.values())


def _apply_header(form, procurement, user, items=(), is_draft=False) -> None:
    if form.mode == "item":
        procurement.last_updated_by = user
        return
    procurement.psu_disbursement_number = (form.psu_disbursement_number.data or "").strip()
    procurement.disbursement_date = _as_datetime(form.disbursement_date.data) if form.disbursement_date.data else None
    procurement.name = (form.name.data or "").strip() or "แบบร่าง MA"
    procurement.company = (form.company.data or "").strip() or ("-" if is_draft else "")
    if form.mode == "header":
        pass  # ยอดรวมของ MA ที่ไม่ใช่แบบร่างเท่ากับผลรวมรายการย่อยเสมอ ไม่รับจากฟอร์มหัว
    elif form.total_amount.data is not None:
        procurement.total_amount = form.total_amount.data
    elif is_draft:
        from kampan.utils.money import money_sum

        procurement.total_amount = money_sum(item.amount for item in items if getattr(item, "amount", None))
    elif procurement.total_amount is None:
        procurement.total_amount = Decimal("0")
    procurement.last_updated_by = user


def _clone_item_for_procurement(item: models.ProcurementItem, new_procurement: models.Procurement) -> models.ProcurementItem:
    sub_items = [
        models.ItemDetail(
            brand=sub.brand,
            model_name=sub.model_name,
            serial_number=sub.serial_number,
            asset_code=sub.asset_code,
            details=sub.details,
        )
        for sub in item.sub_items or []
    ]
    installments = [
        models.Installment(
            due_date=inst.due_date,
            amount=inst.amount,
            paid_date=inst.paid_date,
            paid_by=inst.paid_by,
            payment_number=inst.payment_number,
            paid_amount=inst.paid_amount,
            pay_log=[
                models.PayLogEntry(
                    action=p.action,
                    pressed_at=p.pressed_at,
                    paid_date=p.paid_date,
                    by=p.by,
                    payment_number=p.payment_number,
                    paid_amount=p.paid_amount,
                )
                for p in inst.pay_log or []
            ],
        )
        for inst in (item.installments if item.pays_in_installments() else [])
    ]
    return models.ProcurementItem(
        organization=new_procurement.organization,
        procurement=new_procurement,
        name=item.name,
        category=item.category,
        quantity=getattr(item, "quantity", 1) or 1,
        unit=getattr(item, "unit", "") or "",
        account_code=item.account_code,
        start_date=item.start_date,
        end_date=item.end_date,
        amount=item.amount,
        sub_items=sub_items,
        has_sub_item_sn=item.has_sub_item_sn,
        has_sub_item_asset=item.has_sub_item_asset,
        winner=item.winner,
        unit_price=item.unit_price,
        note=item.note,
        responsible_by=list(item.responsible_by or []),
        responsible_divisions=list(item.responsible_divisions or []),
        has_custom_responsible_divisions=item.has_custom_responsible_divisions,
        reminder_kind=item.reminder_kind,
        requires_activation=item.requires_activation,
        expiry_reminder_offsets=list(item.expiry_reminder_offsets or []),
        payment_reminder_offsets=list(item.payment_reminder_offsets or []),
        reminder_offsets_days=list(item.reminder_offsets_days or []),
        installment_mode=item.installment_mode,
        installments=installments,
    )


def _duplicate_child_procurements(parent_procurement, items, user):
    for item in items:
        # ชื่อโครงการอยู่ที่สัญญาหลัก สัญญาย่อยใช้ชื่อรายการย่อยตรง ๆ ไม่ต่อชื่อโครงการ
        child_name = item.name
        child = models.Procurement(
            organization=parent_procurement.organization,
            name=child_name,
            company=parent_procurement.company,
            psu_disbursement_number=parent_procurement.psu_disbursement_number,
            disbursement_date=parent_procurement.disbursement_date,
            total_amount=item.amount,
            parent_procurement=parent_procurement,
            created_by=user,
            last_updated_by=user,
            status=parent_procurement.status,
        )
        child_item = _clone_item_for_procurement(item, child)
        child.save_with_items([child_item])


def _publish_draft_children(parent):
    """เผยแพร่แบบร่างของสัญญาหลัก: สัญญาย่อยที่ยังเป็นแบบร่างเริ่มที่ review (สัญญาย่อยที่เปิดใช้แล้วมีสถานะของตัวเอง ไม่ถูกแตะ)"""
    for child in models.Procurement.objects(parent_procurement=parent, organization=parent.organization, status="draft"):
        claimed = models.Procurement.objects(id=child.id, organization=parent.organization, status="draft").update_one(
            set__status="review"
        )
        if claimed:
            child.status = "review"
            child.refresh_usage_status()


def _save_form(
    form, organization, procurement, existing_items, member, is_draft=False, target_item=None, responsibles_before=None
):
    user = current_user._get_current_object()
    is_new = procurement.pk is None
    mode = form.mode
    render_kwargs = {"mode": mode, "target_item": target_item}
    removed_items = []
    if mode == "header":
        # แก้เฉพาะหัว: รายการย่อยทุกรายการคงเดิม ไม่อ่านช่องรายการจากฟอร์ม
        items = list(existing_items)
    elif mode == "item":
        # แก้รายการเดียว: ฟอร์มต้องมีรายการเดียวและเป็นรายการที่เลือก ส่วนรายการอื่นคงเดิม
        entries = form.item_entries()
        if len(entries) != 1 or (entries[0].form.item_id.data or "") != str(target_item.id):
            return _render_form(form, organization, member, procurement, [ITEM_FORM_MISMATCH_MESSAGE], **render_kwargs)
        try:
            built, _ = _build_items(form, organization, [target_item], user, fallback_name=procurement.name)
        except InstallmentChangeError as error:
            return _render_form(form, organization, member, procurement, [str(error)], **render_kwargs)
        items = [built[0] if existing.pk == target_item.pk else existing for existing in existing_items]
        from kampan.utils.money import money_sum

        procurement.total_amount = money_sum(item.amount for item in items if item.amount)
    else:
        try:
            items, removed_items = _build_items(form, organization, existing_items, user, is_draft=is_draft)
        except InstallmentChangeError as error:
            return _render_form(form, organization, member, procurement, [str(error)], **render_kwargs)

    if not is_draft and mode in ("header", "item"):
        # โหมดเต็มตรวจในฟอร์มแล้ว: เลขที่ ม.อ.เบิกจ่ายของหัวจำเป็นเมื่อมีรายการที่ไม่แบ่งจ่ายเป็นงวด (จ่ายแล้วตอนสร้าง MA)
        psu_number = form.psu_disbursement_number.data if mode == "header" else procurement.psu_disbursement_number
        if not (psu_number or "").strip() and any(not item.pays_in_installments() for item in items):
            return _render_form(form, organization, member, procurement, [PSU_NUMBER_REQUIRED_MESSAGE], **render_kwargs)

    _apply_header(form, procurement, user, items=items, is_draft=is_draft)
    try:
        procurement.save_with_items(items, removed_items)
    except models.ConcurrentEditConflict:
        return _render_form(form, organization, member, procurement, [STALE_FORM_MESSAGE], **render_kwargs)
    except me.ValidationError as error:
        return _render_form(form, organization, member, procurement, [error.message], **render_kwargs)

    has_children = models.Procurement.objects(parent_procurement=procurement).count() > 0
    if len(items) > 1 and not has_children:
        # สร้างใหม่ หรือแบบร่างที่เพิ่งเพิ่มรายการที่ 2 ต้องแยกเป็นสัญญาย่อยตามรายการ
        _duplicate_child_procurements(procurement, items, user)
    elif has_children and procurement.status != "draft":
        _publish_draft_children(procurement)

    ma_assignments.notify_new_assignments(
        procurement,
        items,
        responsibles_before or {},
        current_user._get_current_object(),
        current_app.config,
    )

    if is_draft:
        flash("บันทึกแบบร่างเรียบร้อยแล้ว", "success")
        return redirect(url_for("procurement.products.index", organization_id=organization.id))
    else:
        flash("บันทึก MA เรียบร้อยแล้ว", "success")
        return redirect(url_for("procurement.payment.index", procurement_id=procurement.id, organization_id=organization.id))


@module.route("/create", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required(*(role for role, _ in models.organizations.ORGANIZATION_ROLES))
def create():
    organization = g.organization
    # ผู้ดูแลระบบระดับ global ผ่าน decorator ไปก่อนที่จะมีการตรวจหน่วยงาน
    if not organization:
        abort(404)

    # สมาชิกทุก role สร้าง MA ได้ (ผู้สร้างแก้ไขและเห็น MA ของตัวเองได้เสมอ) แต่ต้องเป็นสมาชิกที่ active
    member = ma_permissions.get_member(organization)
    if not member and "admin" not in current_user.roles:
        abort(403)

    action = request.form.get("action", "save") if request.method == "POST" else None
    is_draft = action == "draft"

    # MA สร้างจากหน้ารายการ MA เท่านั้น ไม่รับค่าตั้งต้นจาก query string
    form = _build_form(organization, member=member, is_draft=is_draft)
    if not form.validate_on_submit():
        return _render_form(form, organization, member)

    procurement = models.Procurement(
        organization=organization,
        status="draft" if is_draft else "review",
        created_by=current_user._get_current_object(),
    )
    return _save_form(form, organization, procurement, [], member, is_draft=is_draft)


@module.route("/<procurement_id>/edit", methods=["GET", "POST"])
@login_required
def edit(procurement_id):
    organization = g.organization
    if not organization:
        abort(404)
    procurement = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)

    if not ma_permissions.can_edit_procurement(procurement, organization):
        flash(NO_EDIT_PERMISSION_MESSAGE, "error")
        return redirect(
            url_for("procurement.payment.index", procurement_id=procurement.id, organization_id=organization.id)
        )

    member = ma_permissions.get_member(organization)
    # ผู้รับผิดชอบก่อนแก้ ใช้หาผู้ที่ถูกเพิ่มใหม่ (ต้องเก็บก่อนฟอร์มแก้ object ของรายการย่อย)
    responsibles_before = ma_assignments.snapshot_responsibles(procurement)
    action = request.form.get("action") if request.method == "POST" else None
    was_draft = procurement.status == "draft"
    # แบบร่าง = ฟอร์มเต็ม · MA ที่ไม่ใช่แบบร่างแก้ได้แค่หัว หรือรายการเดียว (?item_id=) และเปลี่ยนกลับเป็นแบบร่างไม่ได้
    is_draft = was_draft and action == "draft"
    mode = "full"
    target_item = None
    if not was_draft:
        item_id = request.args.get("item_id")
        if item_id:
            target_item = _find_item_or_404(procurement, item_id)
            mode = "item"
        else:
            mode = "header"

    form = _build_form(
        organization, procurement=procurement, member=member, is_draft=is_draft, target_item=target_item, mode=mode
    )
    if not form.validate_on_submit():
        return _render_form(form, organization, member, procurement, target_item=target_item, mode=mode)

    if form.version.data != procurement.get_version():
        return _render_form(form, organization, member, procurement, [STALE_FORM_MESSAGE], target_item=target_item, mode=mode)

    if is_draft:
        procurement.status = "draft"
    elif was_draft:
        procurement.status = "review"

    return _save_form(
        form,
        organization,
        procurement,
        procurement.get_items(),
        member,
        is_draft=is_draft,
        target_item=target_item,
        responsibles_before=responsibles_before,
    )


def _find_item_or_404(procurement, item_id) -> models.ProcurementItem:
    """รายการย่อยของ MA นี้ (ในหน่วยงานเดียวกัน) ตาม id ไม่พบ = 404"""
    for item in procurement.get_items():
        if str(item.id) == str(item_id):
            return item
    abort(404)


@module.route("/<procurement_id>/items/<item_id>/delete", methods=["POST"])
@login_required
def delete_item(procurement_id, item_id):
    """ลบรายการย่อยของ MA ที่ไม่ใช่แบบร่าง (ปุ่มที่หน้ารายละเอียด): ห้ามลบรายการสุดท้ายหรือรายการที่มีงวดจ่ายแล้ว"""
    organization = g.organization
    if not organization:
        abort(404)
    procurement = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)
    detail_url = url_for("procurement.payment.index", procurement_id=procurement.id, organization_id=organization.id)

    if not ma_permissions.can_edit_procurement(procurement, organization):
        flash(NO_EDIT_PERMISSION_MESSAGE, "error")
        return redirect(detail_url)

    item = _find_item_or_404(procurement, item_id)
    form = forms.post_action.PostActionForm()
    if not form.validate_on_submit():
        flash("คำขอไม่ถูกต้องหรือหมดอายุ กรุณาลองใหม่อีกครั้ง", "error")
        return redirect(detail_url)

    item_name = item.name
    try:
        procurement.delete_item(item, user=current_user._get_current_object())
    except models.ItemDeleteError as error:
        flash(str(error), "error")
        return redirect(detail_url)
    except models.ConcurrentEditConflict:
        flash(STALE_FORM_MESSAGE, "error")
        return redirect(detail_url)

    flash(f"ลบรายการ '{item_name}' เรียบร้อยแล้ว", "success")
    return redirect(detail_url)


@module.route("/<procurement_id>/delete", methods=["POST"])
@login_required
def delete(procurement_id):
    """ลบแบบร่าง MA: อนุญาตเฉพาะรายการที่มีสถานะ draft เท่านั้น"""
    organization = g.organization
    if not organization:
        abort(404)
    procurement = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)

    if not ma_permissions.can_edit_procurement(procurement, organization):
        flash(NO_EDIT_PERMISSION_MESSAGE, "error")
        return redirect(url_for("procurement.products.index", organization_id=organization.id))

    if procurement.status != "draft":
        flash("สามารถลบได้เฉพาะรายการที่เป็นแบบร่างเท่านั้น", "error")
        return redirect(url_for("procurement.products.index", organization_id=organization.id))

    name = procurement.name
    # ลบรายการย่อยและสัญญาที่เกี่ยวข้อง
    models.ProcurementItem.objects(procurement=procurement, organization=organization).delete()
    for child in models.Procurement.objects(parent_procurement=procurement, organization=organization):
        models.ProcurementItem.objects(procurement=child, organization=organization).delete()
        try:
            if child.image:
                child.image.delete()
        except Exception:
            pass
    models.Procurement.objects(parent_procurement=procurement, organization=organization).delete()

    try:
        if procurement.image:
            procurement.image.delete()
    except Exception:
        pass
    models.Procurement.objects(id=procurement.id).delete()

    flash(f"ลบแบบร่าง '{name}' เรียบร้อยแล้ว", "success")
    return redirect(url_for("procurement.products.index", organization_id=organization.id))


@module.route("/<procurement_id>/renew", methods=["GET", "POST"])
@login_required
def renew(procurement_id):
    """ต่ออายุ MA (#32): เปิดฟอร์มสร้าง MA ที่เติมข้อมูลจาก MA เดิม บันทึกแล้วได้ MA ใหม่ และ MA เดิมเป็น "ต่ออายุแล้ว" """
    organization = g.organization
    if not organization:
        abort(404)
    old = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)
    if old.status == "draft":
        flash("ไม่สามารถต่ออายุรายการแบบร่างได้", "warning")
        return redirect(url_for("procurement.products.edit", procurement_id=old.id, organization_id=organization.id))
    detail_url = url_for("procurement.payment.index", procurement_id=old.id, organization_id=organization.id)
    if not ma_permissions.can_edit_procurement(old, organization):
        flash(NO_RENEW_PERMISSION_MESSAGE, "error")
        return redirect(detail_url)
    if old.is_renewed():
        flash(ALREADY_RENEWED_MESSAGE, "error")
        return redirect(detail_url)
    if not ma_permissions.can_approve_renewal(organization):
        flash(NOT_RENEWAL_APPROVER_MESSAGE, "error")
        return redirect(detail_url)
    if not ma_permissions.renewal_requested_as(old, "renew"):
        flash(RENEW_NOT_REQUESTED_MESSAGE, "error")
        return redirect(detail_url)

    if request.method == "POST" and request.form.get("expected_request") != "renew":
        # คำขอที่ admin เห็นตอนเปิดฟอร์มไม่ใช่ "ต่ออายุ" แล้ว (ผู้รับผิดชอบเปลี่ยนคำขอ) ไม่ต่ออายุ
        flash(RENEW_NOT_REQUESTED_MESSAGE, "error")
        return redirect(detail_url)

    member = ma_permissions.get_member(organization)
    items = old.get_items()
    item_id = request.args.get("item_id")
    target_item = None
    if item_id:
        for it in items:
            if str(it.id) == str(item_id):
                target_item = it
                break
    if not target_item and items:
        target_item = items[0]

    form = _build_form(organization, member=member, renew_from=old, target_item=target_item)
    if not form.validate_on_submit():
        return _render_form(form, organization, member, renew_from=old, target_item=target_item)

    user = current_user._get_current_object()
    items_to_save, _ = _build_items(form, organization, [], user)

    new = models.Procurement(organization=organization, status="review", created_by=user)
    _apply_header(form, new, user)
    if old.parent_procurement:
        new.parent_procurement = old.parent_procurement
    elif len(items) > 1:
        new.parent_procurement = old

    try:
        old.renew_into(new, items_to_save)
    except models.RenewalConflict:
        flash(ALREADY_RENEWED_MESSAGE, "error")
        return redirect(detail_url)
    except me.ValidationError as error:
        return _render_form(form, organization, member, form_errors=[error.message], renew_from=old, target_item=target_item)

    try:
        ma_assignments.notify_new_assignments(new, items_to_save, {}, user, current_app.config)
    except Exception:
        # อีเมลแจ้งมอบหมายไม่ทำให้การต่ออายุล้ม
        logger.exception("notifying assignments of renewed procurement %s failed", new.pk)
    try:
        old.pay_single_installments_on_renewal(user)
    except Exception:
        # ต่ออายุสำเร็จแล้ว แต่บันทึกจ่ายงวดเดียวของ MA เดิมไม่สำเร็จ: แจ้งผู้ใช้ให้บันทึกเองและ log สาเหตุ
        logger.exception("recording single installments of %s on renewal failed", old.pk)
        flash("ต่ออายุแล้ว แต่บันทึกการจ่ายงวดของ MA เดิมไม่สำเร็จ กรุณาบันทึกจ่ายที่หน้ารายละเอียด MA เดิม", "warning")
    flash("ต่ออายุ MA เรียบร้อยแล้ว", "success")
    return redirect(url_for("procurement.payment.index", procurement_id=new.id, organization_id=organization.id))



@module.route("/<organization_id>/download_template")
@login_required
@acl.organization_roles_required("admin")
def download_template(organization_id):
    organization = models.Organization.objects(id=organization_id, status="active").first()
    if not organization:
        abort(404)
    template_data = {
        "product_number": ["มอ. 011/2567-0001"],
        "ชื่อรายการ": ["เครื่องคอมพิวเตอร์"],
        "รหัสครุภัณฑ์": ["CC/www-x-yy/zz"],
        "วันที่เริ่มต้น": ["14 พฤศจิกายน 2567"],
        "วันที่สิ้นสุด": ["14 พฤศจิกายน 2568"],
        "ระยะเวลา (เดือน)": [12],
        "จำนวน (งวด)": [1],
        "ประเภท": ["จ้างเหมาบริการ"],
        "ชื่อผู้รับผิดชอบ": ["นายสมชาย ใจดี"],
        "จำนวนเงิน": [50000],
        "ชื่อบริษัท/ร้านค้า ผู้จำหน่ายผลิตภัณฑ์": ["บริษัท เทคโนโลยี จำกัด"],
        "หมายเหตุ": ["สำหรับใช้ในสำนักงาน"],
    }
    df = pd.DataFrame(template_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="แม่แบบข้อมูล", index=False)
        worksheet = writer.sheets["แม่แบบข้อมูล"]
        for column in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in column), default=0)
            column_letter = column[0].column_letter
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"Template_{organization.name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@module.route("/<procurement_id>/picture/<filename>")
@login_required
def image(procurement_id, filename):
    organization = g.organization
    if not organization:
        abort(404)

    procurement = ma_permissions.get_visible_procurement_or_404(procurement_id, organization)
    if not procurement.image or procurement.image.filename != filename:
        return abort(403)
    return send_file(
        procurement.image,
        download_name=procurement.image.filename,
        mimetype=procurement.image.content_type,
    )
