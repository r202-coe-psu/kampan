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


@module.route("", methods=["GET", "POST"])
@login_required
def index():
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=8, type=int)
    progress = request.args.get("progress", default=None, type=str)
    if progress:
        # query progress ล่าสุด
        pipeline = [
            {
                "$addFields": {
                    "last_progress_status": {
                        "$arrayElemAt": ["$progress.progress_status", -1]
                    }
                }
            },
            {"$match": {"last_progress_status": progress}},
        ]
        query = models.RequisitionTimeLine.objects.aggregate(*pipeline)
    else:
        query = models.RequisitionTimeLine.objects
    organization = current_user.user_setting.current_organization
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object()
    ).first()
    is_admin = current_user.has_organization_roles("admin")
    if is_admin:
        requisition_timeline = query.order_by("-updated_date")
    if not is_admin:
        requisition_timeline = query.filter(purchaser=org_user_role).order_by(
            "-updated_date"
        )

    paginated_requisition_timeline = Pagination(
        requisition_timeline, page=page, per_page=per_page
    )
    progress_choices = models.requisition_timeline.PROGRESS_STATUS_CHOICES
    print(progress_choices)
    return render_template(
        "/procurement/requisitions/requisition_timeline.html",
        requisition_timeline_list=requisition_timeline,
        organization=organization,
        paginated_requisition_timeline=paginated_requisition_timeline,
        progress_choices=progress_choices,
        is_admin=is_admin,
    )


@module.route("/<requisition_timeline_id>/add_progress", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_progress(requisition_timeline_id):
    organization = current_user.user_setting.current_organization
    requisition_timeline = models.RequisitionTimeLine.objects(
        id=requisition_timeline_id
    ).first()
    if not requisition_timeline:
        abort(404)

    next_status = get_next_status(requisition_timeline.progress)
    if next_status is None:
        return redirect(
            url_for(
                "requisition_timeline.view",
                requisition_timeline_id=requisition_timeline.id,
                organization=organization,
                error="ความคืบหน้าเสร็จสิ้นแล้ว ไม่สามารถเพิ่มขั้นตอนได้",
            )
        )
    if request.method == "POST":
        new_progress = models.Progress(
            progress_status=next_status,
            created_by=current_user._get_current_object(),
            created_date=datetime.datetime.now(),
            last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent"),
            timestamp=datetime.datetime.now(),
        )
        requisition_timeline.progress.append(new_progress)
        requisition_timeline.last_updated_by = current_user._get_current_object()
        requisition_timeline.updated_date = datetime.datetime.now()
        requisition_timeline.save()

        return redirect(
            url_for(
                "requisition_timeline.view",
                requisition_timeline_id=requisition_timeline.id,
                organization=organization,
            )
        )
