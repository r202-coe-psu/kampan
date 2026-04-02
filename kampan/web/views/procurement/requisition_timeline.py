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
    filter_form = forms.requisition_timeline.RequisitionTimelineFilterForm()

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
        filter_form=filter_form,
        progress_choices=progress_choices,
        is_admin=is_admin,
        PROGRESS_STATUS_ORDER=PROGRESS_STATUS_ORDER,
        reservations_map=reservations_map,
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


@module.route("/<requisition_timeline_id>/billing_modal", methods=["POST"])
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
    form = forms.requisition_timeline.BillingForm()
    res_map = {str(r.id): r for r in reservations}
    usage_amounts = {}
    total_amount = 0.0
    for entry in form.reservations.entries:
        res_id = entry.reservation_id.data
        actual = float(entry.amount.data or 0)
        usage_amounts[res_id] = round(actual, 2)
        total_amount += actual

    for res_id, actual in usage_amounts.items():
        res = res_map.get(res_id)
        if not res:
            continue
        unused = float(res.amount or 0) - actual
        res.actual_amount = actual
        res.reservation_status = "finished"
        res.save()
        if res.mas:
            new_remaining = float(res.mas.remaining_amount or 0) - actual
            res.mas.remaining_amount = max(0, new_remaining)
            res.mas.reservable_amount = float(res.mas.reservable_amount or 0) + unused
            res.mas.save()

            # Update the Requisition's fund amount for this MAS
            for fund_item in requisition_timeline.requisition.fund:
                for r in reservations:
                    if str(r.mas.id) == str(fund_item.mas.id):
                        fund_item.reservation = r
                        break

                if str(fund_item.mas.id) == str(res.mas.id):
                    fund_item.amount = actual

    # Save the updated requisition
    requisition_timeline.requisition.save()

    requisition_timeline.fund_usage_amounts = usage_amounts
    requisition_timeline.payment_amount = round(total_amount, 2)
    add_progress_in_order(
        requisition_timeline, "awaiting_delivery", current_user, request
    )
    if form.quotation_winner.data:
        requisition_timeline.quotation_winner = form.quotation_winner.data
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
        form.inspection_date.data = inspection_p.created_date if inspection_p else None
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

    if request.method == "POST":
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
                    company=(
                        requisition.items[0].company if requisition.items else ""
                    ),  # Inherit some properties
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
    )
