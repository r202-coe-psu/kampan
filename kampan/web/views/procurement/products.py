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
    organization = current_user.user_setting.current_organization

    # --- Filter only ---
    category = request.args.get("category", "")
    payment_status = request.args.get("payment_status", "")

    query = {}
    if category:
        query["category"] = category
    if payment_status:
        query["payment_status"] = payment_status

    procurements = (
        models.Procurement.objects(
            __raw__=query, tor_year=current_user.user_setting.tor_year
        )
        if query
        else models.Procurement.objects(tor_year=current_user.user_setting.tor_year)
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
        today=datetime.date.today(),
    )


@module.route("/create", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def create():
    form = forms.procurement.ProcurementForm()
    organization = current_user.user_setting.current_organization
    tor_year_id = request.args.get("tor_year_id")
    members = models.User.objects()
    form.responsible_by.queryset = members

    if not form.validate_on_submit():
        form.responsible_by.label_modifier = lambda u: f"{u.first_name} {u.last_name}"
        return render_template(
            "/procurement/products/create.html",
            form=form,
            organization=organization,
        )

    procurement = models.Procurement()
    form.populate_obj(procurement)

    procurement.created_by = current_user._get_current_object()
    procurement.last_updated_by = current_user._get_current_object()

    # เก็บ ToRYear
    tor_year = None
    if tor_year_id:
        tor_year = models.ToRYear.objects(id=tor_year_id).first()
    elif current_user.user_setting and current_user.user_setting.tor_year:
        tor_year = current_user.user_setting.tor_year
    if tor_year:
        procurement.tor_year = tor_year

    procurement.save()
    return redirect(url_for("procurement.products.index", organization=organization))


@module.route("/<procurement_id>/set_paid", methods=["POST"])
@login_required
@acl.organization_roles_required("admin")
def set_paid(procurement_id):
    organization = current_user.user_setting.current_organization
    procurement = models.Procurement.objects(id=procurement_id).first()

    # หา index ของงวดถัดไปที่ต้องจ่าย
    next_period_index = len(procurement.payment_records)

    # บันทึกประวัติการจ่ายเงิน
    procurement.add_payment_record(
        period_index=next_period_index,
        paid_by=current_user._get_current_object(),
    )

    # อัปเดต paid_period_index ให้เป็นงวดที่เพิ่งจ่าย
    procurement.paid_period_index = next_period_index

    # ถ้าจ่ายครบทุกงวดแล้ว ให้เปลี่ยน status เป็น paid
    if len(procurement.payment_records) >= procurement.period:
        procurement.payment_status = "paid"

    procurement.last_updated_by = current_user._get_current_object()
    procurement.save()

    return redirect(
        url_for(
            "procurement.products.index",
            organization=organization,
        )
    )
