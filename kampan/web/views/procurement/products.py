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
from kampan import models, utils

import pandas as pd
from io import BytesIO

from ... import redis_rq

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
    unpaid_payments_count = 0
    today = datetime.date.today()

    for p in procurements:
        months, days = calculate_months_days(p.start_date, p.end_date)
        p.duration_months = months
        p.duration_days = days

        # Check if payment is due within a week for urgent payments count
        status = p.get_current_payment_status(today)
        if status == "upcoming":
            due_dates = p.get_payment_due_dates()
            next_idx = p.get_next_payment_index()
            if next_idx < len(due_dates):
                next_due_date = due_dates[next_idx]
                if hasattr(next_due_date, "date"):
                    next_due_date = next_due_date.date()
                days_until_due = (next_due_date - today).days
                if 0 <= days_until_due <= 7:  # Due within a week
                    unpaid_payments_count += 1

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
        today=today,
        unpaid_payments_count=unpaid_payments_count,
    )


@module.route("/create", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def create():
    form = forms.procurement.ProcurementForm()
    organization = current_user.user_setting.current_organization
    tor_year_id = request.args.get("tor_year_id")
    members = organization.get_organization_users()
    form.responsible_by.queryset = members

    if not form.validate_on_submit():
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
        tor_year = models.ToRYear.objects(id=tor_year_id, status="active").first()
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


@module.route("/<organization_id>/upload", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def upload(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.procurement.FileForm()
    errors = request.args.getlist("errors")

    template_columns = [
        "ปังบประมาณ",
        "ชื่อรายการ",
        "รหัสครุภัณฑ์",
        "วันที่เริ่มต้น",
        "วันที่สิ้นสุด",
        "ระยะเวลา (เดือน)",
        "จำนวน (งวด)",
        "ประเภท",
        "ชื่อผู้รับผิดชอบ",
        "จำนวนเงิน",
        "ชื่อบริษัท/ร้านค้า ผู้จำหน่ายผลิตภัณฑ์",
        "หมายเหตุ",
    ]

    if request.method == "POST" and form.validate_on_submit():
        if form.document_upload.data:
            if not errors:
                file_storage = form.document_upload.data
                if isinstance(file_storage, list):
                    file_storage = file_storage[0]
                file_storage.seek(0)
                file_bytes = file_storage.read()
                try:
                    df = pd.read_excel(BytesIO(file_bytes))
                    file_columns = list(df.columns)
                    missing_cols = [
                        col for col in template_columns if col not in file_columns
                    ]
                    if missing_cols:
                        errors.append(
                            f"ไฟล์ที่อัปโหลดไม่มี column เหล่านี้: {', '.join(missing_cols)}"
                        )
                        return render_template(
                            "/procurement/products/upload_procurement.html",
                            form=form,
                            organization=organization,
                            errors=errors,
                        )
                    job = redis_rq.redis_queue.queue.enqueue(
                        utils.procurements.upload_procurement_excel,
                        args=[
                            file_bytes,
                            current_user.id,
                        ],
                        timeout=600,
                        job_timeout=600,
                    )
                    print("=====> submit", job.get_id())
                    return redirect(
                        url_for(
                            "procurement.products.index",
                            organization_id=organization_id,
                        )
                    )
                except Exception as e:
                    errors.append(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
                    return render_template(
                        "/procurement/products/upload_procurement.html",
                        form=form,
                        organization=organization,
                        errors=errors,
                    )
        else:
            errors.append("ไม่พบไฟล์ กรุณาเลือกไฟล์ก่อนอัปโหลด")
    return render_template(
        "/procurement/products/upload_procurement.html",
        form=form,
        organization=organization,
        errors=errors,
    )


@module.route("/<organization_id>/download_template")
@login_required
@acl.organization_roles_required("admin")
def download_template(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    # สร้างข้อมูลตัวอย่างสำหรับแม่แบบ
    template_data = {
        "ปังบประมาณ": ["25xx"],
        "ชื่อรายการ": ["เครื่องคอมพิวเตอร์"],
        "รหัสครุภัณฑ์": ["CC/www-x-yy/zz"],
        "วันที่เริ่มต้น": ["14 พฤศจิกายน 2567"],
        "วันที่สิ้นสุด": ["14 พฤศจิกายน 2568"],
        "ระยะเวลา (เดือน)": [12],
        "จำนวน (งวด)": [1],
        "ประเภท": ["จ้างเหมาบริการ"],
        "ชื่อผู้รับผิดชอบ": ["นายสมชาย ใจดี"],
        "จำนวนเงิน": [50000],
        "ชื่อบริษัท/ร้านค้า ผู้จำหน่ายผลิตภัณฑ์": ["บริษัท เทคโนโลยี จำกัด"],
        "หมายเหตุ": ["สำหรับใช้ในสำนักงาน"],
    }

    # สร้าง DataFrame และ Excel file (Excel 2007 format)
    df = pd.DataFrame(template_data)
    output = BytesIO()

    # ใช้ openpyxl engine สำหรับ Excel 2007+ format
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="แม่แบบข้อมูล", index=False)

        # ปรับขนาดคอลัมน์
        worksheet = writer.sheets["แม่แบบข้อมูล"]
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f"Template_{organization.name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
