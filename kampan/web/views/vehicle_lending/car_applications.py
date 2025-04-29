from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
    jsonify,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("car_applications", __name__, url_prefix="/car_applications")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization
    )
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)
    return render_template(
        "/vehicle_lending/car_applications/index.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/calendar", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def calendar():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization
    )
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)
    return render_template(
        "/vehicle_lending/car_applications/calendar.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"car_application_id": None})
@module.route("/<car_application_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def create_or_edit(car_application_id):
    car_application = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicle_applications.CarApplicationForm()

    form.car.choices = [
        (str(car.id), car.license_plate)
        for car in models.vehicles.Car.objects(organization=organization)
    ]
    if not form.validate_on_submit():
        if car_application_id:
            car_application = models.vehicle_applications.CarApplication.objects(
                id=car_application_id
            ).first()
            form = forms.vehicle_applications.CarApplicationForm(obj=car_application)

        else:
            date = request.args.get("date", type=str, default=None)
            if date:
                date = datetime.datetime.strptime(date, "%Y-%m-%d")
                form.departure_date.data = date.date()
                form.departure_time.data = date.time()
        if car_application:
            form.departure_date.data = car_application.departure_datetime.date()
            form.departure_time.data = car_application.departure_datetime.time()

            form.return_date.data = car_application.return_datetime.date()
            form.return_time.data = car_application.return_datetime.time()

            form.flight_date.data = car_application.flight_datetime.date()
            form.flight_time.data = car_application.flight_datetime.time()
        form.car.choices = [
            (str(car.id), car.license_plate)
            for car in models.vehicles.Car.objects(organization=organization)
        ]
        return render_template(
            "/vehicle_lending/car_applications/create_or_edit.html",
            organization=organization,
            form=form,
        )

    car_application = models.vehicle_applications.CarApplication()
    if car_application_id:
        car_application = models.vehicle_applications.CarApplication.objects(
            id=car_application_id
        ).first()

    form.populate_obj(car_application)
    car_application.car = models.vehicles.Car.objects(id=form.car.data).first()
    if not car_application.car:
        return render_template(
            "/vehicle_lending/car_applications/create_or_edit.html",
            organization=organization,
            form=form,
        )
    car_application.departure_datetime = datetime.datetime.combine(
        form.departure_date.data, form.departure_time.data
    )
    if form.travel_type.data != "one way":
        car_application.return_datetime = datetime.datetime.combine(
            form.return_date.data, form.return_time.data
        )
    car_application.status = "pending on header"

    if form.using_type.data == "out of town":
        car_application.status = "pending on director"
    if form.using_type.data == "airport transfer":
        car_application.flight_datetime = datetime.datetime.combine(
            form.flight_date.data, form.flight_time.data
        )

    car_application.organization = current_user.get_current_organization()
    car_application.division = current_user.get_current_division()
    if not car_application_id:
        car_application.creator = current_user
    car_application.updater = current_user
    car_application.updated_date = datetime.datetime.now()
    car_application.save()
    return redirect(
        url_for(
            "vehicle_lending.car_applications.index", organization_id=organization_id
        )
    )


@module.route("/<car_application_id>/delete")
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier", "supervisor supplier"
)
def delete(car_application_id):
    organization_id = request.args.get("organization_id")

    car_application = models.vehicle_applications.CarApplication.objects().get(
        id=car_application_id
    )
    car_application.status = "disactive"
    car_application.save()

    return redirect(url_for("vehicle_lending.car_applications.index", **request.args))


@module.route("/get_car_applications")
@login_required
def get_car_applications():
    organization_id = request.args.get("organization_id")

    car_applications = models.vehicle_applications.CarApplication.objects(
        status__in=[
            "pending on header",
            "pending on director",
            "pending on admin",
            "active",
        ]
    )

    color_of_event = {
        "active": "green",
        "pending on header": "orange",
        "pending on director": "orange",
        "pending on admin": "orange",
    }
    datas = []
    for car_application in car_applications:
        start = car_application.departure_datetime.strftime("%Y-%m-%d")
        end = (
            car_application.departure_datetime + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        if car_application.travel_type == "round trip":
            end = (
                car_application.return_datetime + datetime.timedelta(days=1)
            ).strftime("%Y-%m-%d")

        data = {
            "id": str(car_application.id),
            "title": car_application.request_reason,
            "start": start,
            "end": end,
            "color": color_of_event[car_application.status],
        }
        datas.append(data)

    return jsonify({"car_applications": datas})
