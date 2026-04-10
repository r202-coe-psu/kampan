from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
    Response,
    current_app,
)
from io import BytesIO
from PyPDF2 import PdfMerger
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import forms, acl
from kampan import models, utils
from kampan.utils.hash import hash_mongo_metadata
from ... import redis_rq
import datetime
import json
import hashlib


module = Blueprint("requisition_timeline", __name__, url_prefix="/requisition_timeline")

PROGRESS_STATUS_ORDER = [
    "request_created",
    "vendor_contacted",
    "details_specified",
    "order_confirmed",
    "awaiting_delivery",
    "inspection",
    "payment_processed",
    "completed",
]


def get_next_status(progress_list):
    if progress_list == []:
        return "request_created"
    else:
        last_status = progress_list[-1].progress_status
        last_index = PROGRESS_STATUS_ORDER.index(last_status)
        if last_index + 1 < len(PROGRESS_STATUS_ORDER):
            return f"{PROGRESS_STATUS_ORDER[last_index + 1]}"
        else:
            return None


# สําหรับกรอง id ของ requisition สําหรับ progress ล่าสุด
def filtered_requisition_timeline_by_progress(requisition_timeline, progress):
    filtered_timelines = []
    for timeline in requisition_timeline:
        if timeline.progress and len(timeline.progress) > 0:
            latest_status = timeline.progress[-1].progress_status
            if latest_status == progress:
                filtered_timelines.append(timeline)
    return filtered_timelines


# return ตําเเหน่งของ progress_status ใน progress_list
def get_progress_index(progress_list, progress_status):
    if not progress_list:
        return 0
    progress_index = None
    # หา index ของ progress_status ที่กําลังจะเพิ่ม
    order_index = PROGRESS_STATUS_ORDER.index(progress_status)
    # หา index ของ progress_status ที่มีอยู่ใน progress_list
    for i, progress in enumerate(progress_list):
        current_index = PROGRESS_STATUS_ORDER.index(progress.progress_status)
        if current_index >= order_index:
            progress_index = i
            break
    # สําหรับกรณีที่ progress_status ที่จะเพิ่มอยู่ท้ายสุด
    if progress_index is None:
        progress_index = len(progress_list)

    return progress_index


def add_progress_in_order(
    requisition_timeline,
    new_progress_status,
    current_user,
    request,
):
    progress_index = get_progress_index(
        requisition_timeline.progress,
        new_progress_status,
    )
    if progress_index < len(requisition_timeline.progress):
        requisition_timeline.progress = requisition_timeline.progress[:progress_index]

    new_progress = models.Progress(
        progress_status=new_progress_status,
        created_by=current_user._get_current_object(),
        last_ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        timestamp=datetime.datetime.now(),
    )

    # ช็คว่า step ต่อไปเป็น payment_processed ไหม (step ปัจจุบันคือ inspection)
    if new_progress_status == "payment_processed":
        inspection_date_str = request.form.get("inspection_date")
        if inspection_date_str:
            try:
                requisition_timeline.inspection_date = datetime.datetime.strptime(
                    inspection_date_str, "%Y-%m-%d"
                )
            except ValueError:
                pass

    requisition_timeline.progress.append(new_progress)

    # อัปเดตข้อมูลอื่นๆ
    requisition_timeline.last_updated_by = current_user._get_current_object()
    requisition_timeline.updated_date = datetime.datetime.now()

    requisition_timeline.save()

    return requisition_timeline


def generate_requisition_items(requisition_timeline):
    """For each RequisitionItem, ensure `quantity` RequisitionTimelineItem docs exist.
    Returns dict: { str(item._id) -> [RequisitionTimelineItem, ...] }
    """
    items_by_type = {}
    requisition = requisition_timeline.requisition

    for req_item in requisition.items:
        item_id = req_item._id
        existing = list(
            models.RequisitionTimelineItem.objects(
                requisition_timeline=requisition_timeline,
                requisition_item_id=item_id,
            ).order_by("created_date")
        )

        # Create missing items up to the quantity
        while len(existing) < req_item.quantity:
            new_item = models.RequisitionTimelineItem(
                requisition_timeline=requisition_timeline,
                requisition=requisition,
                requisition_item_id=item_id,
                requisition_item=req_item.product_name,
                running_number=len(existing) + 1,
                insurance_start_date="",
                seller="",
                insurance_end_date="",
                serial_number="",
                requisition_item_code="",
                location="",
                created_by=requisition_timeline.created_by,
            )
            new_item.save()
            existing.append(new_item)

        items_by_type[str(item_id)] = existing

    return items_by_type


@module.route("", methods=["GET", "POST"])
@login_required
def index():
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)
    progress = request.args.get("progress", default=None, type=str)
    requisition_code = request.args.get("requisition_code", default=None, type=str)
    form = forms.requisition_timeline.RequisitionTimelineFilterForm(request.args)
    inspection_form = forms.requisition_timeline.RequisitionInspectionForm()

    # query zone
    progress_choices = models.requisition_timeline.PROGRESS_STATUS_CHOICES
    organization = current_user.user_setting.current_organization
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object()
    ).first()
    # query เเรกของ requisition timeline
    requisition_timeline = models.RequisitionTimeline.objects.order_by("-updated_date")
    is_admin = current_user.has_organization_roles("admin")

    if progress:
        # กรองโดยตรวจสอบ progress ล่าสุด
        filtered_timelines = [
            rt.id
            for rt in filtered_requisition_timeline_by_progress(
                requisition_timeline, progress
            )
        ]
        # สร้าง query ใหม่จาก IDs ที่กรองแล้ว
        requisition_timeline = models.RequisitionTimeline.objects(
            id__in=filtered_timelines
        ).order_by("-updated_date")

    if requisition_code:
        # ดึง requisitions ที่มี requisition_code ตรงกับเงื่อนไข
        requisitions = models.Requisition.objects(
            requisition_code__icontains=requisition_code
        ).only("id")
        # กรอง requisition_timeline โดยใช้ requisition IDs
        requisition_ids = [req.id for req in requisitions]
        requisition_timeline = requisition_timeline.filter(
            requisition__in=requisition_ids
        )

    # เช็คสิทธิ์ถ้าไม่ใช่ admin ให้กรองเฉพาะรายการของผู้ใช้คนนั้น
    if not is_admin:
        requisition_timeline = requisition_timeline.filter(purchaser=org_user_role)

    paginated_requisition_timeline = Pagination(
        requisition_timeline,
        page=page,
        per_page=per_page,
    )

    page_requisition_ids = [
        item.requisition.id
        for item in paginated_requisition_timeline.items
        if item.requisition
    ]
    page_reservations = models.Reservation.objects(requisition__in=page_requisition_ids)
    reservations_map = {}
    for res in page_reservations:
        key = str(res.requisition.id)
        reservations_map.setdefault(key, []).append(res)

    return render_template(
        "/procurement/requisitions/requisition_timeline.html",
        paginated_requisition_timeline=paginated_requisition_timeline,
        requisition_timeline_list=requisition_timeline,
        organization=organization,
        form=form,
        progress_choices=progress_choices,
        is_admin=is_admin,
        PROGRESS_STATUS_ORDER=PROGRESS_STATUS_ORDER,
        reservations_map=reservations_map,
        inspection_form=inspection_form,
    )


@module.route("/<requisition_timeline_id>/add_progress", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_progress(requisition_timeline_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    requisition_timeline = models.RequisitionTimeline.objects.get(
        id=requisition_timeline_id
    )
    new_progress_status = request.form.get("progress")

    if new_progress_status:
        add_progress_in_order(
            requisition_timeline,
            new_progress_status,
            current_user,
            request,
        )
        requisition_timeline_logs = models.RequisitionTimelineLogs(
            requisition_timeline=requisition_timeline,
            metadata=requisition_timeline.to_mongo().to_dict(),
            hashed_metadata=hash_mongo_metadata(requisition_timeline),
            progress_status=new_progress_status,
            created_by=current_user._get_current_object(),
            last_ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        requisition_timeline_logs.save()

    return redirect(
        url_for(
            "procurement.requisition_timeline.index",
            organization_id=organization.id,
        )
    )


@module.route("/<requisition_timeline_id>/cancel", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def cancel(requisition_timeline_id):
    form = forms.requisition_timeline.RequisitionCancelForm()
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    requisition_timeline = models.RequisitionTimeline.objects.get(
        id=requisition_timeline_id
    )
    note = form.note.data
    if not note:
        return redirect(
            url_for(
                "procurement.requisition_timeline.index",
                organization_id=organization.id,
            )
        )
    # บันทึกเหตุผลการยกเลิกs
    requisition_timeline.note = note
    requisition_timeline.status = "cancelled"
    requisition_timeline.save()

    requisition = models.Requisition.objects(
        id=requisition_timeline.requisition.id
    ).first()

    if requisition:
        requisition.status = "cancelled"
        requisition.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.send_cancellation_email_to_relevant.send_cancellation_email_to_relevant,
        args=(
            requisition,
            requisition_timeline,
            current_user._get_current_object(),
            current_app.config,
        ),
        timeout=600,
        job_timeout=600,
    )
    if job:
        print("=====> Cancellation email job submitted", job.get_id())

    return redirect(
        url_for(
            "procurement.requisition_timeline.index",
            organization_id=organization.id,
        )
    )


@module.route("/<requisition_timeline_id>/billing_modal", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def billing_modal(requisition_timeline_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    requisition_timeline = models.RequisitionTimeline.objects.get(
        id=requisition_timeline_id
    )
    reservations = list(
        models.Reservation.objects(requisition=requisition_timeline.requisition)
    )
    reservation_map = {str(reservation.id): reservation for reservation in reservations}
    reservation_payloads = []
    for reservation in reservations:
        reservation_payloads.append(
            {
                "id": str(reservation.id),
                "mas_code": reservation.mas.mas_code if reservation.mas else "-",
                "mas_name": reservation.mas.description if reservation.mas else "-",
                "reserved_amount": float(reservation.amount or 0),
                "used_amount": float(
                    (requisition_timeline.fund_usage_amounts or {}).get(
                        str(reservation.id), 0
                    )
                    or 0
                ),
            }
        )

    form = forms.requisition_timeline.BillingForm()

    is_readonly = request.args.get("readonly") == "1"

    def _render_page(errors=None):
        item_source_map = {}
        if requisition_timeline.fund_allocations:
            for item in requisition_timeline.requisition.items:
                item_source_map[str(item._id)] = (
                    requisition_timeline.fund_allocations.get(str(item._id), {}).get(
                        "allocations", []
                    )
                )

        # Generate JSON payloads for JavaScript to avoid Jinja/formatter issues
        reservation_limits_dict = {}
        for reservation in reservations:
            reservation_limits_dict[str(reservation.id)] = float(
                reservation.amount or 0
            )
        reservation_limits_json = json.dumps(reservation_limits_dict)

        item_quantity_limits_dict = {}
        for item in requisition_timeline.requisition.items:
            item_quantity_limits_dict[str(item._id)] = int(item.quantity or 0)
        item_quantity_limits_json = json.dumps(item_quantity_limits_dict)

        return render_template(
            "procurement/requisitions/billing.html",
            item=requisition_timeline,
            organization=organization,
            form=form,
            reservations=reservation_payloads,
            reservation_limits_json=reservation_limits_json,
            item_quantity_limits_json=item_quantity_limits_json,
            total_reserved=sum(
                float(reservation.amount or 0) for reservation in reservations
            ),
            total_used=sum(
                float(
                    (requisition_timeline.fund_usage_amounts or {}).get(
                        str(reservation.id), 0
                    )
                    or 0
                )
                for reservation in reservations
            ),
            item_source_map=item_source_map,
            errors=errors or [],
            selected_purchase_method=requisition_timeline.purchase_method or "",
            readonly=is_readonly,
        )

    if request.method == "GET":
        form.purchase_method.data = requisition_timeline.purchase_method or ""
        form.quotation_winner.data = requisition_timeline.quotation_winner or ""
        return _render_page()

    if is_readonly:
        return _render_page()

    errors = []
    purchase_method = form.purchase_method.data
    quotation_winner = (form.quotation_winner.data or "").strip()
    usage_amounts = {}
    item_allocations = {}
    total_amount = 0.0

    if not purchase_method:
        errors.append("กรุณาเลือกวิธีการจัดซื้อ")

    for item in requisition_timeline.requisition.items:
        item_id = str(item._id)
        item_reserved_qty = int(item.quantity or 0)
        is_multi_source = request.form.get(f"item-{item_id}-multi_source") == "on"
        allocations = []
        item_total = 0.0
        item_qty_total = 0

        if is_multi_source:
            selected_source_ids = request.form.getlist(f"item-{item_id}-multi_sources")
            if not selected_source_ids:
                errors.append(
                    f"กรุณาเลือกแหล่งเงินอย่างน้อย 1 รายการสำหรับ {item.product_name}"
                )
            for source_id in selected_source_ids:
                amount_raw = request.form.get(
                    f"item-{item_id}-multi_amount_{source_id}", ""
                )
                qty_raw = request.form.get(f"item-{item_id}-multi_qty_{source_id}", "")
                reservation = reservation_map.get(source_id)
                try:
                    amount = float(amount_raw or 0)
                except Exception:
                    amount = -1
                try:
                    item_amount = int(qty_raw or 0)
                except Exception:
                    item_amount = -1
                if amount <= 0:
                    errors.append(
                        f"กรุณากรอกจำนวนเงินของแหล่งเงินที่เลือกสำหรับ {item.product_name}"
                    )
                    continue
                if not reservation:
                    errors.append(f"ไม่พบข้อมูลแหล่งเงินที่เลือกสำหรับ {item.product_name}")
                    continue
                reserved_money = float(reservation.amount or 0)
                if amount > reserved_money:
                    errors.append(
                        f"จำนวนเงินของ {item.product_name} ต้องไม่เกินยอดจองของแหล่งเงิน ({reservation.mas.mas_code if reservation.mas else source_id})"
                    )
                    continue
                if item_amount < 0:
                    errors.append(
                        f"กรุณากรอกจำนวนสิ่งของของแหล่งเงินที่เลือกสำหรับ {item.product_name}"
                    )
                    continue
                if item_amount > item_reserved_qty:
                    errors.append(
                        f"จำนวนสิ่งของของ {item.product_name} ต้องไม่เกินจำนวนที่จองไว้ ({item_reserved_qty})"
                    )
                    continue
                allocations.append(
                    {
                        "reservation_id": source_id,
                        "amount": round(amount, 2),
                        "item_amount": item_amount,
                    }
                )
                usage_amounts[source_id] = round(
                    float(usage_amounts.get(source_id, 0)) + amount, 2
                )
                item_total += amount
                item_qty_total += item_amount
        else:
            source_id = request.form.get(f"item-{item_id}-source", "")
            amount_raw = request.form.get(f"item-{item_id}-single_amount", "")
            qty_raw = request.form.get(f"item-{item_id}-single_qty", "")
            reservation = reservation_map.get(source_id) if source_id else None
            if not source_id:
                errors.append(f"กรุณาเลือกแหล่งเงินสำหรับ {item.product_name}")
            else:
                try:
                    amount = float(amount_raw or 0)
                except Exception:
                    amount = -1
                try:
                    item_amount = int(qty_raw or 0)
                except Exception:
                    item_amount = -1
                if amount <= 0:
                    errors.append(f"กรุณากรอกจำนวนเงินที่ใช้จริงของ {item.product_name}")
                else:
                    if not reservation:
                        errors.append(f"ไม่พบข้อมูลแหล่งเงินที่เลือกสำหรับ {item.product_name}")
                        continue
                    reserved_money = float(reservation.amount or 0)
                    if amount > reserved_money:
                        errors.append(
                            f"จำนวนเงินของ {item.product_name} ต้องไม่เกินยอดจองของแหล่งเงิน ({reservation.mas.mas_code if reservation.mas else source_id})"
                        )
                        continue
                    if item_amount < 0:
                        errors.append(f"กรุณากรอกจำนวนสิ่งของสำหรับ {item.product_name}")
                    if item_amount > item_reserved_qty:
                        errors.append(
                            f"จำนวนสิ่งของของ {item.product_name} ต้องไม่เกินจำนวนที่จองไว้ ({item_reserved_qty})"
                        )
                    allocations.append(
                        {
                            "reservation_id": source_id,
                            "amount": round(amount, 2),
                            "item_amount": item_amount if item_amount >= 0 else 0,
                        }
                    )
                    usage_amounts[source_id] = round(
                        float(usage_amounts.get(source_id, 0)) + amount, 2
                    )
                    item_total += amount
                    item_qty_total += item_amount if item_amount >= 0 else 0

        if item_qty_total > item_reserved_qty:
            errors.append(
                f"ผลรวมจำนวนสิ่งของของ {item.product_name} ต้องไม่เกินจำนวนที่จองไว้ ({item_reserved_qty})"
            )

        item_allocations[item_id] = {
            "multi_source": is_multi_source,
            "allocations": allocations,
            "account_code": request.form.get(
                f"item-{item_id}-account_code", ""
            ).strip(),
            "item_total": round(item_total, 2),
        }
        total_amount += item_total

    if errors:
        form.purchase_method.data = purchase_method
        form.quotation_winner.data = quotation_winner
        return _render_page(errors=errors)

    for reservation_id, used_amount in usage_amounts.items():
        reservation = reservation_map.get(reservation_id)
        if not reservation:
            continue
        reserved_money = float(reservation.amount or 0)
        if float(used_amount) > reserved_money:
            errors.append(
                f"ยอดใช้จริงรวมของแหล่งเงิน ({reservation.mas.mas_code if reservation.mas else reservation_id}) ต้องไม่เกินยอดจอง"
            )

    if errors:
        form.purchase_method.data = purchase_method
        form.quotation_winner.data = quotation_winner
        return _render_page(errors=errors)

    for reservation_id, actual in usage_amounts.items():
        res = reservation_map.get(reservation_id)
        if not res:
            continue
        unused = float(res.amount or 0) - float(actual)
        res.actual_amount = float(actual)
        res.reservation_status = "finished"
        res.save()
        if res.mas:
            new_remaining = float(res.mas.remaining_amount or 0) - float(actual)
            models.MAS.objects(id=res.mas.id).update_one(
                set__remaining_amount=max(0, new_remaining),
                set__reservable_amount=float(res.mas.reservable_amount or 0) + unused,
            )

            for fund_item in requisition_timeline.requisition.fund:
                if fund_item.mas and str(fund_item.mas.id) == str(res.mas.id):
                    fund_item.reservation = res
                    fund_item.amount = float(actual)

    requisition_timeline.requisition.save()
    requisition_timeline.purchase_method = purchase_method
    requisition_timeline.quotation_winner = (
        quotation_winner or requisition_timeline.quotation_winner
    )
    requisition_timeline.fund_usage_amounts = usage_amounts
    requisition_timeline.fund_allocations = item_allocations
    requisition_timeline.payment_amount = round(total_amount, 2)
    add_progress_in_order(
        requisition_timeline, "awaiting_delivery", current_user, request
    )
    requisition_timeline.save()

    return redirect(
        url_for(
            "procurement.requisition_timeline.index", organization_id=organization.id
        )
    )


@module.route("/<requisition_timeline_id>/completed_submit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def completed_submit(requisition_timeline_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    requisition_timeline = models.RequisitionTimeline.objects.get(
        id=requisition_timeline_id
    )

    responder_user_choices = []
    seen_user_ids = set()
    for member in organization.get_organization_users():
        user = getattr(member, "user", None)
        if not user:
            continue
        user_id = str(user.id)
        if user_id in seen_user_ids:
            continue
        seen_user_ids.add(user_id)
        responder_user_choices.append((user_id, member.display_user_fullname()))

    form = forms.requisition_timeline.CompletedForm()
    is_view_only = requisition_timeline.status == "completed"
    items_by_type = generate_requisition_items(requisition_timeline)

    def _parse_date(value):
        if not value:
            return None
        if isinstance(value, datetime.date):
            return value
        try:
            return datetime.datetime.strptime(str(value), "%Y-%m-%d").date()
        except Exception:
            return None

    def _format_insurance_duration(start_date, end_date):
        if not start_date or not end_date:
            return "-"
        if end_date < start_date:
            return "-"

        years = end_date.year - start_date.year
        months = end_date.month - start_date.month
        days = end_date.day - start_date.day

        if days < 0:
            months -= 1
            previous_month_last_day = (
                end_date.replace(day=1) - datetime.timedelta(days=1)
            ).day
            days += previous_month_last_day

        if months < 0:
            years -= 1
            months += 12

        parts = []
        if years > 0:
            parts.append(f"{years} ปี")
        if months > 0:
            parts.append(f"{months} เดือน")
        if days > 0:
            parts.append(f"{days} วัน")

        return " ".join(parts) if parts else "0 วัน"

    shared_forms_by_type = {}
    row_forms_by_type = {}
    for item_id, timeline_items in items_by_type.items():
        shared_form = forms.requisition_timeline.RequisitionTimelineItemSharedForm(
            prefix=f"shared_{item_id}"
        )
        if timeline_items:
            shared_form.seller.data = timeline_items[0].seller
            start_date = _parse_date(timeline_items[0].insurance_start_date)
            end_date = _parse_date(timeline_items[0].insurance_end_date)
            shared_form.insurance_start_date.data = start_date
            shared_form.insurance_end_date.data = end_date
            shared_form.insurance_duration.data = _format_insurance_duration(
                start_date, end_date
            )
        else:
            shared_form.insurance_duration.data = "-"
        shared_forms_by_type[item_id] = shared_form

        row_forms = []
        for idx, ti in enumerate(timeline_items):
            row_form = forms.requisition_timeline.RequisitionTimelineItemForm(
                prefix=f"row_{item_id}_{idx}"
            )
            row_form.responder_user.choices = responder_user_choices
            row_form.responder_user.data = (
                str(ti.responder_user.id) if ti.responder_user else ""
            )
            row_form.serial_number.data = ti.serial_number
            row_form.requisition_item_code.data = ti.requisition_item_code
            row_form.location.data = ti.location
            row_forms.append(row_form)
        row_forms_by_type[item_id] = row_forms

    if request.method == "GET":
        form.requisition_code.data = requisition_timeline.requisition.requisition_code
        form.product_name.data = (
            requisition_timeline.requisition.items[0].product_name
            if requisition_timeline.requisition.items
            else "-"
        )
        form.total_amount.data = sum(
            item.amount for item in requisition_timeline.requisition.fund
        )

        def _find_progress(status):
            for p in requisition_timeline.progress:
                if p.progress_status == status:
                    return p
            return None

        inspection_p = _find_progress("inspection")
        order_confirmed_p = _find_progress("order_confirmed")
        form.delivered_date.data = inspection_p.created_date if inspection_p else None
        form.inspection_date.data = requisition_timeline.inspection_date
        form.paid_date.data = (
            order_confirmed_p.created_date if order_confirmed_p else None
        )
        form.requisition_creator.data = (
            requisition_timeline.requisition.created_by.get_resources_fullname_th()
            if requisition_timeline.requisition.created_by
            else "-"
        )

        if is_view_only and requisition_timeline.completed_progress_detail:
            cpd = requisition_timeline.completed_progress_detail
            form.seller_name.data = cpd.seller_name
            form.contract_number.data = cpd.contract_number
            form.purchase_method.data = cpd.purchase_method
            form.usage_location.data = cpd.usage_location
            form.warranty_period.data = cpd.warranty_period
            form.start_warranty_date.data = cpd.start_warranty_date
            form.end_warranty_date.data = cpd.end_warranty_date
            form.money_type.data = cpd.money_type
            form.account_code.data = cpd.account_code
            form.asset_code.data = cpd.asset_code

        return render_template(
            "/procurement/requisitions/completed_submit.html",
            item=requisition_timeline,
            organization=organization,
            form=form,
            readonly=is_view_only,
            items_by_type=items_by_type,
            responder_user_choices=responder_user_choices,
            shared_forms_by_type=shared_forms_by_type,
            row_forms_by_type=row_forms_by_type,
        )

    if request.method == "POST":
        for item_id, timeline_items in items_by_type.items():
            shared_form = shared_forms_by_type[item_id]
            insurance_start = request.form.get(
                shared_form.insurance_start_date.name, ""
            )
            seller = request.form.get(shared_form.seller.name, "")
            insurance_end = request.form.get(shared_form.insurance_end_date.name, "")

            for idx, ti in enumerate(timeline_items):
                row_form = row_forms_by_type[item_id][idx]
                ti.insurance_start_date = insurance_start
                ti.seller = seller
                ti.insurance_end_date = insurance_end
                responder_user_id = request.form.get(row_form.responder_user.name, "")
                ti.responder_user = (
                    models.User.objects(id=responder_user_id).first()
                    if responder_user_id
                    else None
                )
                ti.serial_number = request.form.get(row_form.serial_number.name, "")
                ti.requisition_item_code = request.form.get(
                    row_form.requisition_item_code.name, ""
                )
                ti.location = request.form.get(row_form.location.name, "")
                ti.save()

        requisition_timeline.status = "completed"
        requisition_timeline.save()

        add_progress_in_order(
            requisition_timeline, "payment_processed", current_user, request
        )
        add_progress_in_order(requisition_timeline, "completed", current_user, request)

        requisition = models.Requisition.objects(
            id=requisition_timeline.requisition.id
        ).first()
        if requisition:
            requisition.status = "completed"
            requisition.save()

        return redirect(
            url_for(
                "procurement.requisition_timeline.index",
                organization_id=organization.id,
            )
        )

    return render_template(
        "/procurement/requisitions/completed_submit.html",
        item=requisition_timeline,
        organization=organization,
        form=form,
        items_by_type=items_by_type,
        responder_user_choices=responder_user_choices,
        shared_forms_by_type=shared_forms_by_type,
        row_forms_by_type=row_forms_by_type,
    )


@module.route("/<requisition_timeline_id>/details_specified", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def details_specified(requisition_timeline_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    requisition_timeline = models.RequisitionTimeline.objects.get(
        id=requisition_timeline_id
    )
    requisition = requisition_timeline.requisition

    form = forms.requisition_timeline.DetailsSpecifiedForm()
    is_readonly = request.args.get("readonly") == "1"

    if request.method == "GET":
        form.project_name.data = requisition.project_name or ""

        # Populate items from requisition
        for item in requisition.items:
            form.items.append_entry(
                {
                    "item_id": str(item._id),
                    "product_name": item.product_name,
                    "brand": item.brand or "",
                    "model_name": item.model_name or "",
                    "quantity": item.quantity,
                    "amount": item.amount,
                    "winner": item.winner or "",
                    "account_code": item.account_code or "",
                    "note": item.note or "",
                }
            )

    if request.method == "POST" and not is_readonly:
        requisition.project_name = form.project_name.data

        # Update existing items and add new ones
        updated_items = []
        for entry in form.items.entries:
            item_id = entry.item_id.data

            # Find existing item
            existing_item = next(
                (i for i in requisition.items if str(i._id) == item_id), None
            )

            if existing_item:
                existing_item.product_name = entry.product_name.data
                existing_item.brand = entry.brand.data
                existing_item.model_name = entry.model_name.data
                existing_item.quantity = entry.quantity.data
                existing_item.amount = entry.amount.data
                existing_item.winner = entry.winner.data
                existing_item.account_code = entry.account_code.data
                existing_item.note = entry.note.data
                updated_items.append(existing_item)
            else:
                # If they duplicated/added manually with JS and we want to spawn a new item
                new_item = models.RequisitionItem(
                    product_name=entry.product_name.data,
                    company=(requisition.items[0].company if requisition.items else ""),
                    quantity=entry.quantity.data,
                    category=(
                        requisition.items[0].category if requisition.items else "-"
                    ),
                    amount=entry.amount.data,
                    currency=requisition.items[0].currency if requisition.items else "",
                    brand=entry.brand.data,
                    model_name=entry.model_name.data,
                    winner=entry.winner.data,
                    account_code=entry.account_code.data,
                    note=entry.note.data,
                )
                updated_items.append(new_item)

        requisition.items = updated_items
        requisition.save()
        add_progress_in_order(
            requisition_timeline, "order_confirmed", current_user, request
        )

        return redirect(
            url_for(
                "procurement.requisition_timeline.index",
                organization_id=organization.id,
            )
        )

    return render_template(
        "/procurement/requisitions/details_specified.html",
        item=requisition_timeline,
        organization=organization,
        form=form,
        readonly=is_readonly,
    )
