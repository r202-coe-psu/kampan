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
from kampan import models, utils
from ... import redis_rq

import datetime
import pandas as pd

module = Blueprint("products", __name__, url_prefix="/products")


def calculate_months_days(start_date, end_date):
    """Calculate the number of months and days between two dates."""
    if not start_date or not end_date:
        return None, None
    start = start_date.date() if hasattr(start_date, "date") else start_date
    end = end_date.date() if hasattr(end_date, "date") else end_date

    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day >= start.day:
        days = end.day - start.day
    else:
        months -= 1
        from calendar import monthrange

        prev_month = end.month - 1 or 12
        prev_year = end.year if end.month != 1 else end.year - 1
        last_day_prev_month = monthrange(prev_year, prev_month)[1]
        days = last_day_prev_month - start.day + end.day
    return months, days


@module.route("", methods=["GET", "POST"])
def index():
    organization = current_user.user_setting.current_organization
    today = datetime.date.today()

    # Collect filters from request
    category = request.args.get("category", "")
    payment_status = request.args.get("payment_status", "")
    upload_success = request.args.get("upload_success", "")
    year = request.args.get("year", "")

    # Build query dict
    query = {}
    if category:
        query["category"] = category
    if payment_status:
        query["payment_status"] = payment_status
    if year:
        try:
            year_int = int(year)
            start_of_year = datetime.datetime(year_int, 1, 1)
            end_of_year = datetime.datetime(year_int, 12, 31, 23, 59, 59)
            query["created_date__gte"] = start_of_year
            query["created_date__lte"] = end_of_year
        except (ValueError, TypeError):
            pass

    procurement_qs = models.Procurement.objects(**query).order_by("-created_date")

    # Filter for staff role (not admin)
    org_user_role = models.OrganizationUserRole.objects(
        user=current_user._get_current_object()
    ).first()
    if (
        org_user_role
        and "staff" in current_user.roles
        and "admin" not in current_user.roles
    ):
        procurement_qs = procurement_qs.filter(responsible_by=org_user_role)

    # --- Status count section ---
    # Count all procurements for this organization/user role (not paginated, not filtered by category/payment_status)
    base_qs = models.Procurement.objects()

    if (
        org_user_role
        and "staff" in current_user.roles
        and "admin" not in current_user.roles
    ):
        base_qs = base_qs.filter(responsible_by=org_user_role)
    status_count = {}
    for status, _ in models.procurement.PAYEMENT_STATUS_CHOICES:
        status_count[status] = base_qs.filter(payment_status=status).count()
    # --- End status count section ---

    # Pagination
    page = request.args.get("page", default=1, type=int)
    per_page = request.args.get("per_page", default=30, type=int)
    paginated_procurements = Pagination(procurement_qs, page=page, per_page=per_page)

    # Calculate durations
    for p in paginated_procurements.items:
        months, days = calculate_months_days(p.start_date, p.end_date)
        p.duration_months = months
        p.duration_days = days

    # Choices for filters
    all_procurements = models.Procurement.objects()

    # Years for filtering
    available_years = set()
    for p in all_procurements:
        available_years.add(p.created_date.year)
    available_years = sorted(list(available_years), reverse=True)

    category_choices = models.procurement.CATEGORY_CHOICES
    payment_status_choices = models.procurement.PAYEMENT_STATUS_CHOICES

    return render_template(
        "/procurement/products/index.html",
        organization=organization,
        procurements=paginated_procurements.items,
        paginated_procurements=paginated_procurements,
        today=today,
        selected_category=category,
        selected_payment_status=payment_status,
        selected_year=year,
        category_choices=category_choices,
        available_years=available_years,
        payment_status_choices=payment_status_choices,
        upload_success=upload_success,
        all_procurements=all_procurements,
        status_count=status_count,
    )


def validate_upload_file(form, errors, template_columns):
    """Validate uploaded Excel file columns."""
    if not form.document_upload.data:
        errors.append("ไม่พบไฟล์ กรุณาเลือกไฟล์ก่อนอัปโหลด")
        return None, errors
    file_storage = form.document_upload.data
    if isinstance(file_storage, list):
        file_storage = file_storage[0]
    file_storage.seek(0)
    file_bytes = file_storage.read()
    try:
        df = pd.read_excel(BytesIO(file_bytes))
        file_columns = list(df.columns)
        missing_cols = [col for col in template_columns if col not in file_columns]
        if missing_cols:
            errors.append(f"ไฟล์ที่อัปโหลดไม่มี column เหล่านี้: {', '.join(missing_cols)}")
            return None, errors
        return file_bytes, errors
    except Exception as e:
        errors.append(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
        return None, errors


@module.route("/create", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def create():
    form = forms.procurement.ProcurementForm()
    organization = current_user.user_setting.current_organization
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
    procurement.created_by = procurement.last_updated_by = (
        current_user._get_current_object()
    )

    # Save image if uploaded
    if form.image.data:
        if procurement.image:
            procurement.image.replace(
                form.image.data,
                filename=form.image.data.filename,
                content_type=form.image.data.content_type,
            )
        else:
            procurement.image.put(
                form.image.data,
                filename=form.image.data.filename,
                content_type=form.image.data.content_type,
            )

    procurement.save()
    return redirect(url_for("procurement.products.index", organization=organization))


@module.route("/<organization_id>/upload", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def upload(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.procurement.FileForm()
    errors = request.args.getlist("errors")
    template_columns = [
        "product_number",
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
        file_bytes, errors = validate_upload_file(form, errors, template_columns)
        if errors:
            return render_template(
                "/procurement/products/upload_procurement.html",
                form=form,
                organization=organization,
                errors=errors,
            )
        job = redis_rq.redis_queue.queue.enqueue(
            utils.procurements.upload_procurement_excel,
            args=[file_bytes, current_user.id],
            timeout=600,
            job_timeout=600,
        )
        print("=====> submit", job.get_id())
        return redirect(
            url_for(
                "procurement.products.index",
                organization_id=organization_id,
                upload_success=1,
            )
        )

    return render_template(
        "/procurement/products/upload_procurement.html",
        form=form,
        organization=organization,
        errors=errors,
    )


@module.route("/<organization_id>/download_template")
@login_required
@acl.roles_required("admin")
def download_template(organization_id):
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    template_data = {
        "product_number": ["มอ. 011/2567-0001"],
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
    df = pd.DataFrame(template_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="แม่แบบข้อมูล", index=False)
        worksheet = writer.sheets["แม่แบบข้อมูล"]
        for column in worksheet.columns:
            max_length = max((len(str(cell.value)) for cell in column), default=0)
            column_letter = column[0].column_letter
            worksheet.column_dimensions[column_letter].width = min(max_length + 2, 50)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"Template_{organization.name}.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@module.route("/<procurement_id>/picture/<filename>")
def image(procurement_id, filename):
    procurement = models.Procurement.objects.get(id=procurement_id)
    if (
        not procurement
        or not procurement.image
        or procurement.image.filename != filename
    ):
        return abort(403)
    return send_file(
        procurement.image,
        download_name=procurement.image.filename,
        mimetype=procurement.image.content_type,
    )


@module.route("/<procurement_id>/edit_image", methods=["GET", "POST"])
@login_required
def edit_image(procurement_id):
    procurement = models.Procurement.objects(id=procurement_id).first()
    if not procurement:
        abort(404)
    organization = current_user.user_setting.current_organization

    form = forms.procurement.EditImageForm(obj=procurement)
    if not form.validate_on_submit():
        return render_template(
            "/procurement/products/edit_image.html",
            form=form,
            procurement=procurement,
            organization=organization,
        )

    # Save new image if uploaded
    if form.image.data:
        if procurement.image:
            procurement.image.replace(
                form.image.data,
                filename=form.image.data.filename,
                content_type=form.image.data.content_type,
            )
        else:
            procurement.image.put(
                form.image.data,
                filename=form.image.data.filename,
                content_type=form.image.data.content_type,
            )
        procurement.last_updated_by = current_user._get_current_object()
        procurement.save()
    return redirect(url_for("procurement.products.index", organization=organization))
