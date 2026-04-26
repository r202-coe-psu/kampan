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
import io
import qrcode

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


@module.route("/<car_id>/qrcode")
@acl.organization_roles_required("admin", "supervisor supplier")
def qr_code(car_id):
    organization_id = request.args.get("organization_id")
    car = models.vehicles.Car.objects(id=car_id).first()
    if not car:
        return abort(404)

    feedback_url = url_for(
        "vehicle_lending.cars.feedback",
        car_id=car_id,
        _external=True,
    )

    img = qrcode.make(feedback_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf, mimetype="image/png", download_name=f"qrcode_{car.license_plate}.png"
    )


@module.route("/<car_id>/feedback", methods=["GET", "POST"])
def feedback(car_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    car = models.vehicles.Car.objects(id=car_id).first()
    if not car:
        return abort(404)

    template_id = request.args.get("template_id")
    if template_id:
        template = models.car_feedback.CarFeedbackTemplate.objects(
            id=template_id, car=car
        ).first()
    else:
        template = models.car_feedback.CarFeedbackTemplate.objects(car=car).first()

    if not template:
        return render_template("ไม่พบแบบประเมินสำหรับรถคันนี้"), 404

    form = forms.car_feedback.get_dynamic_feedback_form(template)

    if form.validate_on_submit():
        response = models.car_feedback.CarFeedbackResponse(
            feedback_template=template, car=car
        )
        answers = []
        for q in template.questions:
            ans = models.car_feedback.Answer(question_id=q.question_id)
            field_name = f"answer_{q.question_id}"
            field = getattr(form, field_name)

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
            "/vehicle_lending/car_feedback/feedback_thanks.html",
            car=car,
            organization=organization,
        )

    return render_template(
        "/vehicle_lending/car_feedback/feedback.html",
        car=car,
        organization=organization,
        template=template,
        form=form,
    )
