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


module = Blueprint("requisition_progress", __name__, url_prefix="/requisition_progress")

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
        requisition_progress = models.RequisitionProgress.objects().order_by(
            "-updated_date"
        )
    if not is_admin:
        requisition_progress = models.RequisitionProgress.objects(
            purchaser=org_user_role
        ).order_by("-updated_date")

    return render_template(
        "procurement/requisition_progress/index.html",
        requisition_progress_list=requisition_progress,
        organization=organization,
    )


@module.route("/<requisition_progress_id>")
@login_required
def view(requisition_progress_id):
    organization = current_user.user_setting.current_organization
    is_admin = current_user.has_organization_roles("admin")

    requisition_progress = models.RequisitionProgress.objects(
        id=requisition_progress_id
    ).first()

    current_status = None
    if requisition_progress.progress != []:
        current_status = requisition_progress.progress[-1].progress_status
    next_status = get_next_status(requisition_progress.progress)

    return render_template(
        "procurement/requisition_progress/view.html",
        requisition_progress=requisition_progress,
        is_admin=is_admin,
        current_status=current_status,
        next_status=next_status if next_status else None,
        progress_status_order=PROGRESS_STATUS_ORDER,
        organization=organization,
    )


@module.route("/<requisition_progress_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def add_progress(requisition_progress_id):
    organization = current_user.user_setting.current_organization
    requisition_progress = models.RequisitionProgress.objects(
        id=requisition_progress_id
    ).first()
    if not requisition_progress:
        abort(404)

    next_status = get_next_status(requisition_progress.progress)
    if next_status is None:
        return redirect(
            url_for(
                "requisition_progress.view",
                requisition_progress_id=requisition_progress.id,
                organization=organization,
                error="ความคืบหน้าเสร็จสิ้นแล้ว ไม่สามารถเพิ่มขั้นตอนได้",
            )
        )
    if request.method == "POST":
        new_progress = models.Progress(
            progress_status=next_status,
            issued_by=current_user._get_current_object(),
            issued_date=datetime.datetime.now(),
            timestamp=datetime.datetime.now(),
            last_ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
            user_agent=request.headers.get("User-Agent"),
        )
        requisition_progress.progress.append(new_progress)
        requisition_progress.updated_by = current_user._get_current_object()
        requisition_progress.updated_date = datetime.datetime.now()
        requisition_progress.save()

        return redirect(
            url_for(
                "requisition_progress.view",
                requisition_progress_id=requisition_progress.id,
                organization=organization,
            )
        )
