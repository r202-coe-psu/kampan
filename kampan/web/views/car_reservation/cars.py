import datetime

import mongoengine as me
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl, forms

from . import feedback as feedback_view

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


@module.route("/directory")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def directory():
    """ข้อมูลรถและพนักงานขับรถ (อ่านอย่างเดียว) สำหรับสมาชิกทุกคนขององค์กร"""
    return render_template(
        "/car_reservation/cars/directory.html",
        organization=g.organization,
        cars=utils.car_reservation_flow.assignable_cars(g.organization),
        drivers=utils.car_reservation_flow.assignable_drivers(g.organization),
    )


@module.route("/<car_id>/deactivate", methods=["POST"])
@acl.organization_roles_required("admin")
def deactivate(car_id):
    car = get_car_or_404(car_id)
    car.status = "disactive"
    car.updater = current_user._get_current_object()
    car.updated_date = datetime.datetime.now()
    car.save()
    flash(f"ปิดใช้งานรถ {car.license_plate} แล้ว", "success")
    return redirect(
        url_for("car_reservation.cars.index", organization_id=g.organization.id)
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
    car.brand = (form.brand.data or "").strip()
    car.car_model = (form.car_model.data or "").strip()
    car.seat_count = form.seat_count.data
    car.description = form.description.data or ""
    car.status = form.status.data
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


@module.route("/<car_id>/feedback", methods=["GET", "POST"])
def feedback(car_id):
    """หน้าให้ผู้โดยสารประเมินรถคันนี้ (public ไม่ต้อง login เพราะเข้าจาก QR Code หรือลิงก์ในอีเมล)

    หน่วยงานมาจากตัวรถ ไม่ใช่จากผู้ใช้ จึงตรวจเองว่าหน่วยงานของรถเปิดระบบจองรถอยู่ (ACL ตรวจให้
    เฉพาะผู้ที่ login) ``?reservation_id=`` เลือกเที่ยวรถตั้งต้นได้เมื่อเป็นเที่ยวของรถคันนี้
    """
    try:
        car = models.vehicles.Car.objects(id=car_id).first()
    except (me.errors.ValidationError, me.errors.InvalidQueryError):
        car = None
    if not car:
        return abort(404)

    organization = car.organization
    if not organization.has_module("car_reservation"):
        return abort(404)

    template = feedback_view.get_feedback_template_for_car(
        car, template_id=request.args.get("template_id")
    )
    if not template:
        return (
            render_template(
                "/car_reservation/feedback/feedback_unavailable.html",
                car=car,
                organization=organization,
            ),
            404,
        )

    now = datetime.datetime.now()
    car_reservations = feedback_view.get_car_trips(car, organization)
    trip_choices = [
        (
            str(reservation.id),
            f"{feedback_view.get_trip_departure_text(reservation)} · {reservation.location}",
        )
        for reservation in car_reservations
    ]
    default_trip_id = None
    if car_reservations:
        closest_reservation = min(
            car_reservations,
            key=lambda reservation: abs(reservation.departure_datetime - now),
        )
        default_trip_id = str(closest_reservation.id)

    requested_trip_id = request.args.get("reservation_id")
    if requested_trip_id in [trip_id for trip_id, _label in trip_choices]:
        default_trip_id = requested_trip_id

    form = forms.car_reservation_feedback.get_dynamic_feedback_form(
        template, trip_choices=trip_choices, default_trip_id=default_trip_id
    )

    if not form.validate_on_submit():
        return render_template(
            "/car_reservation/feedback/feedback.html",
            car=car,
            organization=organization,
            template=template,
            form=form,
        )

    car_reservation = None
    if trip_choices:
        car_reservation = models.CarReservation.objects(
            id=form.car_reservation.data, car=car, organization=organization
        ).first()

    response = models.CarFeedbackResponse(
        feedback_template=template,
        organization=organization,
        car=car,
        car_reservation=car_reservation,
    )
    answers = []
    for q in template.questions:
        ans = models.Answer(question_id=q.question_id)
        field = getattr(form, f"answer_{q.question_id}")

        if q.question_type == "score" and field.data:
            ans.answer_score = int(field.data)
        elif q.question_type == "text" and field.data:
            ans.answer_text = field.data
        elif q.question_type == "boolean" and field.data:
            ans.answer_boolean = field.data == "True"
        elif q.question_type == "single_choice" and field.data:
            ans.answer_text = field.data
        elif q.question_type == "multiple_choice" and field.data:
            ans.answer_choices = field.data
        answers.append(ans)

    response.answers = answers
    response.save()

    return render_template(
        "/car_reservation/feedback/feedback_thanks.html",
        car=car,
        organization=organization,
    )
