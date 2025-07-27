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
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("products", __name__, url_prefix="/products")


def calculate_months_days(start_date, end_date):
    if not start_date or not end_date:
        return None, None
    # Ensure both are datetime
    if hasattr(start_date, "date"):
        start_date = start_date.date()
    if hasattr(end_date, "date"):
        end_date = end_date.date()
    # Calculate months and days
    months = (end_date.year - start_date.year) * 12 + (
        end_date.month - start_date.month
    )
    if end_date.day >= start_date.day:
        days = end_date.day - start_date.day
    else:
        months -= 1
        # Find last day of previous month
        from calendar import monthrange

        prev_month = end_date.month - 1 or 12
        prev_year = end_date.year if end_date.month != 1 else end_date.year - 1
        last_day_prev_month = monthrange(prev_year, prev_month)[1]
        days = last_day_prev_month - start_date.day + end_date.day
    return months, days


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    # --- Filter only ---
    category = request.args.get("category", "")
    payment_status = request.args.get("payment_status", "")

    query = {}
    if category:
        query["category"] = category
    if payment_status:
        query["payment_status"] = payment_status

    procurements = (
        models.Procurement.objects(__raw__=query)
        if query
        else models.Procurement.objects()
    )

    # Add duration_months and duration_days to each procurement for display
    procurement_list = []
    for p in procurements:
        months, days = calculate_months_days(p.start_date, p.end_date)
        p.duration_months = months
        p.duration_days = days
        procurement_list.append(p)

    # For filter dropdowns
    category_choices = models.procurement.CATEGORY_CHOICES
    payment_status_choices = models.procurement.PAYEMENT_STATUS_CHOICES

    return render_template(
        "/procurement/products/index.html",
        organization=organization,
        procurements=procurement_list,
        selected_category=category,
        selected_payment_status=payment_status,
        category_choices=category_choices,
        payment_status_choices=payment_status_choices,
    )


@module.route("/create", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def create():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.procurement.ProcurementForm()

    if not form.validate_on_submit():
        print("Form validation failed:", form.errors)
        return render_template(
            "/procurement/products/create.html",
            form=form,
            organization=organization,
        )

    procurement = models.Procurement()
    form.populate_obj(procurement)

    procurement.created_by = current_user._get_current_object()
    procurement.last_updated_by = current_user._get_current_object()
    procurement.save()
    return redirect(
        url_for("procurement.products.index", organization_id=organization.id)
    )
