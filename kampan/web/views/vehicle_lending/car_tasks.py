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

module = Blueprint("car_tasks", __name__, url_prefix="/car_tasks")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
@login_required
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    date_str = request.args.get("date")
    target_date = None
    sort_by = request.args.get("sort_by", "departure_datetime")
    order_dir = request.args.get("order", "asc")

    query = Q(organization=organization, status="active")

    if date_str:
        target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        start_of_day = datetime.datetime.combine(target_date, datetime.time.min)
        end_of_day = datetime.datetime.combine(target_date, datetime.time.max)
        query &= Q(
            departure_datetime__gte=start_of_day, departure_datetime__lte=end_of_day
        )

    # Apply sorting
    sort_field = sort_by if order_dir == "asc" else f"-{sort_by}"
    car_lendings = models.vehicle_applications.CarApplication.objects(query).order_by(
        sort_field
    )

    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_lendings, page=page, per_page=30)
    today_date = datetime.date.today()

    return render_template(
        "/vehicle_lending/car_tasks/index.html",
        organization=organization,
        car_lendings=car_lendings,
        target_date=target_date,
        today_date=today_date,
        sort_by=sort_by,
        order_dir=order_dir,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/submit_tasks/<car_application_id>", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "driver")
def submit_task_modal(car_application_id):
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

    form = forms.vehicle_applications.ReturnCarApplicationMileageOnlyForm(
        obj=car_application
    )

    if request.method == "POST" and form.validate_on_submit():
        car = models.vehicles.Car.objects(id=car_application.car.id).first()
        # บันทึกเลขไมล์ก่อนออกเดินทาง
        car_application.last_mileage_before = car.last_mileage
        #  บันทึกเลขไมล์หลังเดินทางกลับในรถ
        car.last_mileage = form.last_mileage.data
        car.save()
        car_application.last_mileage = form.last_mileage.data
        car_application.status = "completed"
        car_application.return_datetime = datetime.datetime.now()
        car_application.updater = current_user._get_current_object()
        car_application.updated_date = datetime.datetime.now()
        car_application.save()

        return redirect(
            url_for(
                "vehicle_lending.car_tasks.index",
                organization_id=organization.id,
            )
        )

    return render_template(
        "/vehicle_lending/car_tasks/submit_task_modal.html",
        organization=organization,
        car_application=car_application,
        form=form,
        modal_id=uuid4(),
    )
