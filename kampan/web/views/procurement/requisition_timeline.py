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
    organization = current_user.user_setting.current_organization

    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object()
    ).first()
    is_admin = current_user.has_organization_roles("admin")
    if is_admin:
        requisition_timeline = models.RequisitionTimeLine.objects().order_by(
            "-updated_date"
        )
    if not is_admin:
        requisition_timeline = models.RequisitionTimeLine.objects(
            purchaser=org_user_role
        ).order_by("-updated_date")

    return render_template(
        "procurement/requisition_timeline/index.html",
        requisition_timeline_list=requisition_timeline,
        organization=organization,
    )


@module.route("/<requisition_timeline_id>")
@login_required
def view(requisition_timeline_id):
    organization = current_user.user_setting.current_organization
    is_admin = current_user.has_organization_roles("admin")

    requisition_timeline = models.RequisitionTimeLine.objects(
        id=requisition_timeline_id
    ).first()

    current_status = None
    if requisition_timeline.progress != []:
        current_status = requisition_timeline.progress[-1].progress_status
    next_status = get_next_status(requisition_timeline.progress)

    return render_template(
        "procurement/requisition_timeline/view.html",
        requisition_timeline=requisition_timeline,
        is_admin=is_admin,
        current_status=current_status,
        next_status=next_status if next_status else None,
        progress_status_order=PROGRESS_STATUS_ORDER,
        organization=organization,
    )


@module.route("/<requisition_timeline_id>/edit", methods=["GET", "POST"])
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
