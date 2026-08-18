from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    abort,
    send_file,
)
from flask_login import login_required, current_user
import mongoengine as me
from bson import ObjectId
import datetime
import io
import qrcode
import json

from kampan.web import forms, acl
from kampan import models

module = Blueprint("car_feedback", __name__, url_prefix="/car_feedback")

# สถานะเที่ยวรถที่ถือว่าเกิดการใช้งานจริงและมีสิทธิ์มีแบบประเมิน
FEEDBACK_TRIP_STATUS = ["active", "completed"]


@module.route("", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    cars = models.vehicles.Car.objects(organization=organization)

    templates = models.CarFeedbackTemplate.objects(cars__in=cars)

    return render_template(
        "/vehicle_lending/car_feedback/index.html",
        organization=organization,
        templates=templates,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"template_id": None})
@module.route("/<template_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(template_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    organization_cars = models.vehicles.Car.objects(organization=organization)

    template = None
    if template_id:
        template = models.CarFeedbackTemplate.objects(
            id=template_id, cars__in=organization_cars
        ).first()
        if not template:
            return abort(404)

    form = forms.car_feedback.CarFeedbackTemplateForm(obj=template)

    cars = models.vehicles.Car.objects(
        organization=organization, status="active"
    ).order_by("license_plate")
    choice_cars = list(cars)
    if template:
        # คงรถที่เคยเลือกไว้ในตัวเลือกด้วย แม้จะถูกปิดใช้งานไปแล้ว ไม่ให้หลุดหายตอนบันทึกซ้ำ
        active_car_ids = {car.id for car in choice_cars}
        choice_cars.extend(
            car for car in template.cars if car.id not in active_car_ids
        )
    car_choices = [(str(car.id), car.license_plate) for car in choice_cars]
    form.cars.choices = car_choices

    if template and request.method == "GET":
        # SelectMultipleField coerce ด้วย str ทำให้ obj=template ได้ค่าเป็น "Car object"
        # ต้องกำหนดเป็น id ของรถเองเพื่อให้ตรงกับ value ของ choices
        form.cars.data = [str(car.id) for car in template.cars]

    if request.method == "POST":
        name = form.name.data
        car_ids = form.cars.data
        description = form.description.data

        selected_cars = models.vehicles.Car.objects(id__in=car_ids, organization=organization)
        if len(selected_cars) != len(car_ids):
            return abort(400, "Invalid car selection")

        questions_json = request.form.get("questions_data")
        if not questions_json:
            return abort(400, "Missed questions data")

        questions = json.loads(questions_json)

        question_templates = []
        for q in questions:
            qt = models.QuestionTemplate()
            if "question_id" in q and q["question_id"]:
                try:
                    qt.question_id = ObjectId(q["question_id"])
                except Exception:
                    pass
            qt.question_text = q.get("question_text")
            qt.question_type = q.get("question_type")
            qt.choice_list = q.get("choice_list", [])
            qt.is_required = q.get("is_required", False)
            question_templates.append(qt)

        if not template:
            template = models.CarFeedbackTemplate()

        template.name = name
        template.cars = selected_cars
        template.description = description
        template.questions = question_templates
        template.save()

        return redirect(
            url_for(
                "vehicle_lending.car_feedback.index", organization_id=organization_id
            )
        )

    return render_template(
        "/vehicle_lending/car_feedback/create_or_edit.html",
        organization=organization,
        template=template,
        template_id=template_id,
        cars=cars,
        car_choices=car_choices,
        form=form,
    )


@module.route("/<template_id>/qrcode")
@acl.organization_roles_required("admin")
def qr_code(template_id):
    car_id = request.args.get("car_id")
    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if not template or not template.cars:
        return abort(404)

    car = None
    if car_id:
        car = models.vehicles.Car.objects(id=car_id).first()
    else:
        car = template.cars[0]

    if not car:
        return abort(404)

    feedback_url = url_for(
        "vehicle_lending.cars.feedback",
        car_id=car.id,
        template_id=template.id,
        _external=True,
    )

    img = qrcode.make(feedback_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return send_file(
        buf,
        mimetype="image/png",
        download_name=f"qrcode_form_{car.license_plate}.png",
    )


@module.route("/<template_id>/view", methods=["GET"])
@acl.organization_roles_required("admin")
def view_responses(template_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    organization_cars = models.vehicles.Car.objects(organization=organization)
    template = models.CarFeedbackTemplate.objects(
        id=template_id, cars__in=organization_cars
    ).first()
    if not template:
        return abort(404)

    # เฉพาะรถของ organization นี้ที่ถูกผูกไว้กับแบบประเมิน
    cars = list(
        models.vehicles.Car.objects(
            id__in=[car.id for car in template.cars], organization=organization
        ).order_by("license_plate")
    )
    car_by_id = {str(car.id): car for car in cars}

    car_id = request.args.get("car_id")
    selected_car = car_by_id.get(car_id)
    if not selected_car:
        car_id = None

    # เที่ยวรถที่ใช้เป็นตัวกรอง = เฉพาะเที่ยวที่รถคันนั้นถูก assign ไว้
    trip_cars = [selected_car] if selected_car else cars
    trips = list(
        models.vehicle_applications.CarApplication.objects(
            car__in=trip_cars,
            organization=organization,
            status__in=FEEDBACK_TRIP_STATUS,
        )
        .no_dereference()
        .order_by("-departure_datetime")
    )

    trip_response_counts = {
        str(row["_id"]): row["count"]
        for row in models.car_feedback.CarFeedbackResponse.objects(
            feedback_template=template
        ).aggregate(
            [
                {"$match": {"car_application": {"$ne": None}}},
                {"$group": {"_id": "$car_application", "count": {"$sum": 1}}},
            ]
        )
    }
    car_response_counts = {
        str(row["_id"]): row["count"]
        for row in models.car_feedback.CarFeedbackResponse.objects(
            feedback_template=template
        ).aggregate([{"$group": {"_id": "$car", "count": {"$sum": 1}}}])
    }

    trip_by_id = {str(trip.id): trip for trip in trips}
    trip_choices = []
    for trip in trips:
        trip_car = car_by_id.get(str(trip.car.id)) if trip.car else None
        trip_choices.append(
            {
                "id": str(trip.id),
                "departure": trip.get_departure_datetime(),
                "location": trip.location,
                "license_plate": trip_car.license_plate if trip_car else "",
                "status": trip.status,
                "status_display": trip.get_status_display(),
                "response_count": trip_response_counts.get(str(trip.id), 0),
            }
        )

    car_application_id = request.args.get("car_application_id")
    if car_application_id not in trip_by_id:
        car_application_id = None
    selected_trip = next(
        (trip for trip in trip_choices if trip["id"] == car_application_id), None
    )

    filter_kwargs = {"feedback_template": template}
    if selected_car:
        filter_kwargs["car"] = selected_car
    else:
        filter_kwargs["car__in"] = cars
    if car_application_id:
        filter_kwargs["car_application"] = trip_by_id[car_application_id]

    responses = list(
        models.car_feedback.CarFeedbackResponse.objects(**filter_kwargs)
        .order_by("-created_date")
        .select_related(max_depth=1)
    )

    stats = {}
    for q in template.questions:
        stat = {
            "type": q.question_type,
            "text": q.question_text,
            "is_required": q.is_required,
            "responses": 0,
            "data": {},
        }
        if q.question_type == "score":
            stat["data"] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            stat["average"] = 0
            stat["sum"] = 0
        elif q.question_type == "boolean":
            stat["data"] = {"true": 0, "false": 0}
        elif q.question_type in ["single_choice", "multiple_choice"]:
            stat["data"] = {choice: 0 for choice in q.choice_list}
        elif q.question_type == "text":
            stat["texts"] = []
        stats[str(q.question_id)] = stat

    for response in responses:
        for answer in response.answers:
            stat = stats.get(str(answer.question_id))
            if not stat:
                continue

            # นับเฉพาะข้อที่มีคำตอบจริง ข้อที่เว้นว่างไม่ควรถ่วงค่าเฉลี่ย
            if stat["type"] == "score":
                if answer.answer_score:
                    stat["responses"] += 1
                    stat["data"][answer.answer_score] += 1
                    stat["sum"] += answer.answer_score
            elif stat["type"] == "boolean":
                if answer.answer_boolean is not None:
                    stat["responses"] += 1
                    key = "true" if answer.answer_boolean else "false"
                    stat["data"][key] += 1
            elif stat["type"] == "single_choice":
                if answer.answer_text:
                    stat["responses"] += 1
                    stat["data"][answer.answer_text] = (
                        stat["data"].get(answer.answer_text, 0) + 1
                    )
            elif stat["type"] == "multiple_choice":
                if answer.answer_choices:
                    stat["responses"] += 1
                    for choice in answer.answer_choices:
                        stat["data"][choice] = stat["data"].get(choice, 0) + 1
            elif stat["type"] == "text":
                if answer.answer_text:
                    stat["responses"] += 1
                    stat["texts"].append(
                        {
                            "text": answer.answer_text,
                            "license_plate": (
                                response.car.license_plate if response.car else ""
                            ),
                            "departure": (
                                response.car_application.get_departure_datetime()
                                if response.car_application
                                else ""
                            ),
                            "created_date": response.created_date,
                        }
                    )

    score_sum = 0
    score_count = 0
    for stat in stats.values():
        if stat["type"] == "score" and stat["responses"] > 0:
            stat["average"] = stat["sum"] / stat["responses"]
            score_sum += stat["sum"]
            score_count += stat["responses"]

    summary = {
        "total_responses": len(responses),
        "overall_average": (score_sum / score_count) if score_count else 0,
        "has_score": score_count > 0,
        "trips_covered": len(
            {
                str(response.car_application.id)
                for response in responses
                if response.car_application
            }
        ),
        "cars_covered": len(
            {str(response.car.id) for response in responses if response.car}
        ),
        "latest_response_date": responses[0].created_date if responses else None,
    }

    return render_template(
        "/vehicle_lending/car_feedback/view.html",
        organization=organization,
        template=template,
        responses=responses,
        stats=stats,
        summary=summary,
        cars=cars,
        car_id=car_id,
        selected_car=selected_car,
        car_response_counts=car_response_counts,
        trip_choices=trip_choices,
        car_application_id=car_application_id,
        selected_trip=selected_trip,
    )


@module.route("/<template_id>/delete")
@acl.organization_roles_required("admin")
def delete(template_id):
    organization_id = request.args.get("organization_id")
    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if template:
        template.delete()
    return redirect(
        url_for("vehicle_lending.car_feedback.index", organization_id=organization_id)
    )
