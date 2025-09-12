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
from uuid import uuid4
import pandas as pd
from io import BytesIO
from mongoengine.queryset.visitor import Q

from kampan.web import forms, acl
from kampan import models

module = Blueprint("history_car_lending", __name__, url_prefix="/history_car_lending")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_lendings = models.vehicle_applications.CarApplication.objects(
        organization=organization, status="active"
    ).order_by("-departure_datetime")
    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_lendings, page=page, per_page=30)
    return render_template(
        "/vehicle_lending/history_car_lending/index.html",
        organization=organization,
        car_lendings=car_lendings,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/detail/<car_application_id>", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def detail(car_application_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization
    ).first()
    if not car_application:
        abort(404)
    return render_template(
        "/vehicle_lending/history_car_lending/detail.html",
        organization=organization,
        car_application=car_application,
        modal_id=uuid4(),
    )


@module.route("/edit/<car_application_id>", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def edit(car_application_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application: models.vehicle_applications.CarApplication = (
        models.vehicle_applications.CarApplication.objects(
            id=car_application_id, organization=organization
        ).first()
    )
    if not car_application:
        abort(404)
    form = forms.vehicle_applications.ReturnCarApplicationForm(obj=car_application)

    if request.method == "POST" and form.validate_on_submit():
        car_application.last_mileage = form.last_mileage.data
        car_application.return_datetime = datetime.datetime.combine(
            form.return_date.data, form.return_time.data
        )
        car_application.updater = current_user._get_current_object()
        car_application.updated_date = datetime.datetime.now()
        car_application.save()
        return redirect(
            url_for(
                "vehicle_lending.history_car_lending.index",
                organization_id=organization.id,
            )
        )
    form.return_date.data = (
        car_application.return_datetime.date()
        if car_application.return_datetime
        else datetime.datetime.now().date()
    )
    form.return_time.data = (
        car_application.return_datetime.time()
        if car_application.return_datetime
        else datetime.datetime.now().time()
    )
    return render_template(
        "/vehicle_lending/history_car_lending/edit.html",
        organization=organization,
        car_application=car_application,
        form=form,
        modal_id=uuid4(),
    )


@module.route("/export_car_applications", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def export_car_applications():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicle_applications.DateRangeForm()
    if request.method == "GET":
        return render_template(
            "/vehicle_lending/history_car_lending/export_car_applications.html",
            form=form,
            modal_id=uuid4(),
            organization=organization,
        )
    if request.method == "POST":
        start_date = form.start_date.data
        end_date = (
            (form.end_date.data + datetime.timedelta(days=1))
            if form.end_date.data
            else None
        )
        query = Q()
        query &= Q(organization=organization) & Q(status="active")
        if start_date:
            query &= Q(departure_datetime__gte=start_date)
        if end_date:
            query &= Q(departure_datetime__lt=end_date)

        car_applications = models.vehicle_applications.CarApplication.objects(
            query
        ).order_by("departure_datetime")

    # แปลงเป็น list ของ dict
    data = []
    for idx, car_application in enumerate(car_applications, start=1):
        data.append(
            {
                "ลำดับ": idx,
                "วันที่ออกเดินทาง": car_application.departure_datetime.strftime(
                    "%d-%m-%Y %H:%M"
                ),
                "ผู้ขอใช้": car_application.creator.get_name(),
                "ลักษณะงาน": car_application.request_reason,
                "สถานที่ไป": car_application.location,
                "กลับถึงเวลา": (
                    car_application.return_datetime.strftime("%d-%m-%Y %H:%M")
                    if car_application.return_datetime
                    else ""
                ),
                "เลขไมล์ก่อนเดินทาง": car_application.get_mile_before(),
                "เลขไมล์หลังเดินทาง": car_application.last_mileage,
            }
        )

    # สร้าง DataFrame
    df = pd.DataFrame(data)

    # เขียนไฟล์ excel ลง memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="CarApplications")

    output.seek(0)

    # ส่งไฟล์ออก
    return send_file(
        output,
        as_attachment=True,
        download_name="บันทึกการใช้รถยนต์.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
