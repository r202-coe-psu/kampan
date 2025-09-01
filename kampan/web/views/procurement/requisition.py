from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from io import BytesIO
from kampan.web import forms, acl
from kampan import models

import datetime

module = Blueprint("requisitions", __name__, url_prefix="/requisitions")


@module.route("", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    tor_year = getattr(current_user.user_setting, "tor_year", None)

    category = request.args.get("category", "")

    query = {}
    if tor_year:
        query["tor_year"] = tor_year
    if category:
        query["category"] = category

    # Filter only items expiring within 7 days and status pending
    procurements = models.Procurement.objects(**query, status="pending").order_by(
        "end_date"
    )

    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=8, type=int)
    paginated_procurements = Pagination(procurements, page=page, per_page=per_page)

    category_choices = models.procurement.CATEGORY_CHOICES
    return render_template(
        "procurement/requisitions/index.html",
        procurements=paginated_procurements.items,
        paginated_procurements=paginated_procurements,
        organization=organization,
        category_choices=category_choices,
        selected_category=category,
    )


@module.route("/<requisition_procurement_id>/delete")
@acl.organization_roles_required("admin")
def delete(requisition_procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=requisition_procurement_id).first()

    if not procurement:
        return redirect(
            url_for("procurement.requisitions.index", organization_id=organization.id)
        )

    procurement.status = "disactive"
    procurement.last_updated_by = current_user._get_current_object()
    procurement.save()
    return redirect(
        url_for("procurement.requisitions.index", organization_id=organization.id)
    )


@module.route("/non-renewal")
@login_required
@acl.organization_roles_required("admin")
def non_renewal():
    organization = current_user.user_setting.current_organization
    category = request.args.get("category", "")
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=10, type=int)

    query = {"status": "disactive"}
    tor_year = getattr(current_user.user_setting, "tor_year", None)
    if tor_year:
        query["tor_year"] = tor_year
    if category:
        query["category"] = category

    procurements = models.Procurement.objects(**query).order_by("-end_date")
    paginated_procurements = Pagination(procurements, page=page, per_page=per_page)
    category_choices = models.procurement.CATEGORY_CHOICES

    params = dict(request.args)
    if "page" in params:
        params.pop("page")
    if "organization_id" not in params:
        params["organization_id"] = organization.id

    return render_template(
        "procurement/requisitions/non_renewal.html",
        disactive_items=paginated_procurements.items,
        paginated_procurements=paginated_procurements,
        organization=organization,
        category_choices=category_choices,
        selected_category=category,
        params=params,
    )
