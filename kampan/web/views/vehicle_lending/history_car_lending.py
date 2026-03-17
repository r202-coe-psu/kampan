from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
import calendar
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime
from uuid import uuid4
import pandas as pd
from mongoengine.queryset.visitor import Q

from kampan.web import forms, acl
from kampan import models
from kampan.repositories.history_car_lending import HistoryCarLendingRepository

module = Blueprint("history_car_lending", __name__, url_prefix="/history_car_lending")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    date_str = request.args.get("date")
    target_date = None
    sort_by = request.args.get("sort_by", "departure_datetime")
    order_dir = request.args.get("order", "asc")

    query = Q(organization=organization, status="completed")

    if date_str:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_of_day = datetime.datetime.combine(target_date, datetime.time.min)
        end_of_day = datetime.datetime.combine(target_date, datetime.time.max)
        query &= Q(
            departure_datetime__gte=start_of_day, departure_datetime__lte=end_of_day
        )

    sort_field = sort_by if order_dir == "asc" else f"-{sort_by}"
    car_lendings = models.vehicle_applications.CarApplication.objects(query).order_by(
        sort_field
    )

    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_lendings, page=page, per_page=30)
    today_date = datetime.date.today()

    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_lendings, page=page, per_page=30)
    return render_template(
        "/vehicle_lending/history_car_lending/index.html",
        organization=organization,
        car_lendings=car_lendings,
        target_date=target_date,
        today_date=today_date,
        sort_by=sort_by,
        order_dir=order_dir,
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
        car = models.vehicles.Car.objects(id=car_application.car.id).first()
        car.last_mileage = form.last_mileage.data
        car.save()
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
    car_applications = []
    if request.method == "GET":
        today = datetime.date.today()

        # วันแรกของเดือน
        first_day = today.replace(day=1)

        # วันสุดท้ายของเดือน
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        # กำหนดค่าให้ form
        form.start_date.data = first_day
        form.end_date.data = last_day

        form.car.choices = [
            (str(car.id), car.license_plate)
            for car in models.vehicles.Car.objects(
                organization=organization, status="active"
            ).order_by("license_plate")
        ]
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
        if form.car.data:
            query &= Q(car=form.car.data)
        car_applications = models.vehicle_applications.CarApplication.objects(
            query
        ).order_by("departure_datetime")
    car_ = models.vehicles.Car.objects(id=form.car.data).first()
    output = HistoryCarLendingRepository.get_export_car_applications_pdf(
        car_applications=car_applications,
        current_user=current_user,
        car=car_,
        start_date=form.start_date.data,
        end_date=form.end_date.data,
    )
    # ส่งไฟล์ออก
    return output
