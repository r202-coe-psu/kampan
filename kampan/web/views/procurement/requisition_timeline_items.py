from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
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


module = Blueprint(
    "requisition_timeline_items", __name__, url_prefix="/requisition_timeline_items"
)


@module.route("/", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.requisition_timeline_items.RequisitionTimelineItemFilterForm(
        request.args
    )
    query = {}
    if form.start_date.data and form.end_date.data:
        query["created_date__gte"] = form.start_date.data
        query["created_date__lte"] = form.end_date.data
    requisition_timeline_items = models.RequisitionTimelineItem.objects(**query)
    return render_template(
        "procurement/requisitions/requisition_timeline_items.html",
        organization=organization,
        form=form,
        requisition_timeline_items=requisition_timeline_items,
    )


@module.route("/export_excel_modal", methods=["GET"])
@acl.organization_roles_required("admin")
def export_excel_modal():
    organization_id = request.args.get("organization_id")
    form = forms.requisition_timeline_items.ExportExcelForm(request.args)
    modal_id = f"export_excel_modal_{hashlib.sha256(json.dumps(request.args, sort_keys=True).encode()).hexdigest()[:8]}"
    return render_template(
        "procurement/components/export_excel_modal.html",
        organization_id=organization_id,
        form=form,
        modal_id=modal_id,
        modal_title="ส่งออกข้อมูลสินค้า",
        url_for_export="admin.mas.export_excel",
    )


@module.route("/export_excel", methods=["POST"])
@acl.organization_roles_required("admin")
def export_excel():
    organization_id = request.args.get("organization_id")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    job_id = redis_rq.redis_queue.queue.enqueue(
        utils.export_file.process_requisition_timeline_items_export,
        args=(current_user._get_current_object(), start_date, end_date),
        timeout=3600,
        job_timeout=1200,
    )
    flash("ระบบกำลังสร้างไฟล์ส่งออกข้อมูลสินค้า กรุณารอสักครู่", "pending")
    return redirect(
        url_for(
            "admin.requisition_timeline_items.index", organization_id=organization_id
        )
    )
