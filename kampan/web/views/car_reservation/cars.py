import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    send_file,
    url_for,
)
from flask_login import current_user

from kampan import models
from kampan.web import acl, forms

module = Blueprint("cars", __name__, url_prefix="/cars")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]


def get_car_or_404(car_id):
    try:
        car = models.vehicles.Car.objects(
            id=car_id, organization=g.organization
        ).first()
    except Exception:
        car = None
    if car is None:
        abort(404)
    return car


@module.route("/")
@acl.organization_roles_required("admin")
def index():
    cars = models.vehicles.Car.objects(organization=g.organization).order_by(
        "license_plate"
    )
    return render_template(
        "/car_reservation/cars/index.html", organization=g.organization, cars=cars
    )


@module.route("/<car_id>/image")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def image(car_id):
    car = get_car_or_404(car_id)
    if not car.image:
        abort(404)
    return send_file(
        car.image,
        download_name=car.image.filename,
        mimetype=car.image.content_type,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"car_id": None})
@module.route("/<car_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(car_id):
    car = get_car_or_404(car_id) if car_id else None
    form = forms.car_reservation.CarForm(obj=car)

    if not form.validate_on_submit():
        return render_template(
            "/car_reservation/cars/create_or_edit.html",
            organization=g.organization,
            form=form,
            car=car,
        )

    if car is None:
        car = models.vehicles.Car(
            organization=g.organization, creator=current_user._get_current_object()
        )
    car.license_plate = form.license_plate.data
    car.vehicle_type = form.vehicle_type.data
    car.seat_count = form.seat_count.data
    car.description = form.description.data or ""
    upload = form.upload_image.data
    if upload:
        store = car.image.replace if car.image else car.image.put
        store(upload, filename=upload.filename, content_type=upload.content_type)
    car.updater = current_user._get_current_object()
    car.updated_date = datetime.datetime.now()
    car.save()
    flash(f"บันทึกรถ {car.license_plate} แล้ว", "success")
    return redirect(
        url_for("car_reservation.cars.index", organization_id=g.organization.id)
    )
