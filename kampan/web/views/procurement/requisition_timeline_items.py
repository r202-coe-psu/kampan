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
    if form.start_date.data and form.end_date.data:
        requisition_timeline_items = models.RequisitionTimelineItem.objects(
            created_date__gte=form.start_date.data,
            created_date__lte=form.end_date.data,
        )
    else:
        requisition_timeline_items = models.RequisitionTimelineItem.objects()
    return render_template(
        "procurement/requisitions/requisition_timeline_items.html",
        organization=organization,
        form=form,
        requisition_timeline_items=requisition_timeline_items,
    )
