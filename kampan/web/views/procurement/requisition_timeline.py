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
from ... import redis_rq
import datetime


module = Blueprint("requisition_timeline", __name__, url_prefix="/requisition_timeline")

PROGRESS_STATUS_ORDER = [
    "request_created",
    "vendor_contacted",
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


@module.route("", methods=["GET", "POST"])
@login_required
def index():
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)
    progress = request.args.get("progress", default=None, type=str)
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

    # เช็คสิทธิ์ถ้าไม่ใช่ admin ให้กรองเฉพาะรายการของผู้ใช้คนนั้น
    if not is_admin:
        requisition_timeline = requisition_timeline.filter(purchaser=org_user_role)

    paginated_requisition_timeline = Pagination(
        requisition_timeline,
        page=page,
        per_page=per_page,
    )
    return render_template(
        "/procurement/requisitions/requisition_timeline.html",
        paginated_requisition_timeline=paginated_requisition_timeline,
        requisition_timeline_list=requisition_timeline,
        organization=organization,
        progress_choices=progress_choices,
        is_admin=is_admin,
        PROGRESS_STATUS_ORDER=PROGRESS_STATUS_ORDER,  # Add this line
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

    # Get progress value from form
    new_progress_status = request.form.get("progress")

    if new_progress_status:
        # Create a new Progress embedded document
        progress_entry = models.Progress(
            progress_status=new_progress_status,
            created_by=current_user._get_current_object(),
            last_ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
            timestamp=datetime.datetime.now(),
        )
        # Append to the progress list
        requisition_timeline.progress.append(progress_entry)
        requisition_timeline.last_updated_by = current_user._get_current_object()
        requisition_timeline.updated_date = datetime.datetime.now()
        requisition_timeline.save()

    return redirect(
        url_for(
            "procurement.requisition_timeline.index",
            organization_id=organization.id,
        )
    )
