import datetime

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from kampan import models
from kampan.web import acl, forms

module = Blueprint("cars", __name__, url_prefix="/cars")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(id=organization_id, status="active").first()
    cars = models.vehicles.Car.objects(organization=organization)
    return render_template("/vehicle_lending/cars/index.html", organization=organization, cars=cars)


@module.route("/create", methods=["GET", "POST"], defaults={"car_id": None})
@module.route("/<car_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(car_id):
    car = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(id=organization_id, status="active").first()
    form = forms.vehicles.CarForm()
    if car_id:
        car = models.vehicles.Car.objects(id=car_id, organization=organization).first()
        if not car:
            return abort(404)

        form = forms.vehicles.CarForm(obj=car)

    if not form.validate_on_submit():
        return render_template(
            "/vehicle_lending/cars/create_or_edit.html",
            organization=organization,
            form=form,
        )

    car = models.vehicles.Car()
    if car_id:
        car = models.vehicles.Car.objects(id=car_id, organization=organization).first()
        if not car:
            return abort(404)
    if form.upload_image.data:
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
    car.organization = current_user.get_viewing_organization()
    if not car_id:
        car.creator = current_user._get_current_object()
    car.updater = current_user._get_current_object()
    car.updated_date = datetime.datetime.now()

    car.save()
    flash(f"{'บันทึก' if car_id else 'เพิ่ม'}รถ {car.license_plate} แล้ว", "success")
    return redirect(url_for("vehicle_lending.cars.index", organization_id=organization_id))


@module.route("/<car_id>/picture/<filename>")
@acl.organization_roles_required("admin", "supervisor supplier", "head", "supervisor supplier")
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
    flash(f"ลบรถ {car.license_plate} แล้ว", "success")

    return redirect(url_for("vehicle_lending.cars.index", **request.args))
