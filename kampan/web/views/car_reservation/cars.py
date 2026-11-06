import datetime

from flask import Blueprint, abort, flash, g, redirect, render_template, url_for
from flask_login import current_user

from kampan import models
from kampan.web import acl, forms

module = Blueprint("cars", __name__, url_prefix="/cars")


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
    form.populate_obj(car)
    car.updater = current_user._get_current_object()
    car.updated_date = datetime.datetime.now()
    car.save()
    flash(f"บันทึกรถ {car.license_plate} แล้ว", "success")
    return redirect(
        url_for("car_reservation.cars.index", organization_id=g.organization.id)
    )
