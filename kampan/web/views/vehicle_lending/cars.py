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

module = Blueprint("cars", __name__, url_prefix="/cars")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    cars = models.vehicles.Car.objects(organization=organization)
    return render_template(
        "/vehicle_lending/cars/index.html", organization=organization, cars=cars
    )


@module.route("/create", methods=["GET", "POST"], defaults={"car_id": None})
@module.route("/<car_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(car_id):
    car = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicles.CarForm()
    if car_id:
        car = models.vehicles.Car.objects(id=car_id).first()
        form = forms.vehicles.CarForm(obj=car)

    if not form.validate_on_submit():
        print(form.errors)

        return render_template(
            "/vehicle_lending/cars/create_or_edit.html",
            organization=organization,
            form=form,
        )

    car = models.vehicles.Car()
    if car_id:
        car = models.vehicles.Car.objects(id=car_id).first()
    if form.upload_image.data:
        print(form.upload_image.data)
        if car.image:
            car.image.replace(
                form.upload_image.data,
                filename=form.upload_image.data.filename,
                content_type=form.upload_image.data.content_type,
            )
        else:
            car.image.put(
                form.upload_image.data,
                filename=form.upload_image.data.filename,
                content_type=form.upload_image.data.content_type,
            )
    form.populate_obj(car)
    car.organization = current_user.get_current_organization()
    if not car_id:
        car.creator = current_user
    car.updater = current_user
    car.updated_date = datetime.datetime.now()

    car.save()
    return redirect(
        url_for("vehicle_lending.cars.index", organization_id=organization_id)
    )


@module.route("/<car_id>/picture/<filename>")
@acl.organization_roles_required(
    "admin", "supervisor supplier", "head", "supervisor supplier"
)
def image(car_id, filename):
    organization_id = request.args.get("organization_id")

    car = models.vehicles.Car.objects.get(id=car_id)

    if not car or not car.image or car.image.filename != filename:
        return abort(403)

    response = send_file(
        car.image,
        download_name=car.image.filename,
        mimetype=car.image.content_type,
    )
    return response


@module.route("/<car_id>/delete")
@acl.organization_roles_required("admin", "supervisor supplier")
def delete(car_id):
    organization_id = request.args.get("organization_id")

    car = models.vehicles.Car.objects().get(id=car_id)
    car.status = "disactive"
    car.save()

    return redirect(url_for("vehicle_lending.cars.index", **request.args))
