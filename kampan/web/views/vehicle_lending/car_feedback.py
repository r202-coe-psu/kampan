import io
import json

import qrcode
from bson import ObjectId
from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from kampan import models
from kampan.web import acl, forms

module = Blueprint("car_feedback", __name__, url_prefix="/car_feedback")

# สถานะเที่ยวรถที่ถือว่าเกิดการใช้งานจริงและมีสิทธิ์มีแบบประเมิน
FEEDBACK_TRIP_STATUS = ["active", "completed"]

# เพดานข้อมูลที่ดึงมาแสดงในหน้าสถิติ กันไม่ให้ payload บวมตามจำนวนผลตอบรับ
TEXT_ANSWER_LIMIT = 200
RESPONSE_LOG_LIMIT = 50


def build_stats_pipeline(questions):

    qids_by_type = {}
    for question in questions:
        qids_by_type.setdefault(question.question_type, []).append(question.question_id)

    def answer_stage(question_type, answer_match):
        return [
            {"$unwind": "$answers"},
            {
                "$match": {
                    "answers.question_id": {"$in": qids_by_type.get(question_type, [])},
                    **answer_match,
                }
            },
        ]

    def group_by_value(value_field):
        return {
            "$group": {
                "_id": {"q": "$answers.question_id", "value": value_field},
                "count": {"$sum": 1},
            }
        }

    # แต่ละ $match นับเฉพาะข้อที่มีคำตอบจริง ข้อที่เว้นว่างไม่ควรถ่วงค่าเฉลี่ย
    return [
        {
            "$facet": {
                "summary": [
                    {
                        "$group": {
                            "_id": None,
                            "total": {"$sum": 1},
                            "cars": {"$addToSet": "$car"},
                            "trips": {"$addToSet": "$car_application"},
                            "latest": {"$max": "$created_date"},
                        }
                    }
                ],
                "score": answer_stage("score", {"answers.answer_score": {"$ne": None}}) + [group_by_value("$answers.answer_score")],
                "boolean": answer_stage("boolean", {"answers.answer_boolean": {"$ne": None}})
                + [group_by_value("$answers.answer_boolean")],
                "single_choice": answer_stage("single_choice", {"answers.answer_text": {"$nin": [None, ""]}})
                + [group_by_value("$answers.answer_text")],
                # multiple_choice ต้องนับ 2 อย่าง: จำนวนคนที่ตอบ และจำนวนครั้งของแต่ละตัวเลือก
                "multi_respondents": answer_stage("multiple_choice", {"answers.answer_choices.0": {"$exists": True}})
                + [{"$group": {"_id": "$answers.question_id", "count": {"$sum": 1}}}],
                "multi_choices": answer_stage("multiple_choice", {"answers.answer_choices.0": {"$exists": True}})
                + [
                    {"$unwind": "$answers.answer_choices"},
                    group_by_value("$answers.answer_choices"),
                ],
                # $sort ก่อน $push เพื่อให้ได้ข้อความล่าสุดขึ้นก่อน แล้ว $slice ตัดเพดาน
                "texts": [{"$sort": {"created_date": -1}}]
                + answer_stage("text", {"answers.answer_text": {"$nin": [None, ""]}})
                + [
                    {
                        "$group": {
                            "_id": "$answers.question_id",
                            "total": {"$sum": 1},
                            "items": {
                                "$push": {
                                    "text": "$answers.answer_text",
                                    "car": "$car",
                                    "car_application": "$car_application",
                                    "created_date": "$created_date",
                                }
                            },
                        }
                    },
                    {
                        "$project": {
                            "total": 1,
                            "items": {"$slice": ["$items", TEXT_ANSWER_LIMIT]},
                        }
                    },
                ],
            }
        }
    ]


def collect_question_stats(questions, aggregated):
    """แปลงผลลัพธ์ของ build_stats_pipeline เป็นสถิติต่อคำถามสำหรับ template

    ยังไม่รวมเนื้อหาข้อความ เพราะต้อง resolve ทะเบียนรถกับเที่ยวรถเพิ่มก่อน
    """
    stats = {}
    for question in questions:
        stat = {
            "type": question.question_type,
            "text": question.question_text,
            "is_required": question.is_required,
            "responses": 0,
            "data": {},
        }
        if question.question_type == "score":
            stat["data"] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            stat["average"] = 0
            stat["sum"] = 0
        elif question.question_type == "boolean":
            stat["data"] = {"true": 0, "false": 0}
        elif question.question_type in ["single_choice", "multiple_choice"]:
            stat["data"] = {choice: 0 for choice in question.choice_list}
        elif question.question_type == "text":
            stat["texts"] = []
            stat["texts_truncated"] = 0
        stats[str(question.question_id)] = stat

    for row in aggregated.get("score", []):
        stat = stats.get(str(row["_id"]["q"]))
        if not stat:
            continue
        score = row["_id"]["value"]
        stat["data"][score] = stat["data"].get(score, 0) + row["count"]
        stat["responses"] += row["count"]
        stat["sum"] += score * row["count"]

    for row in aggregated.get("boolean", []):
        stat = stats.get(str(row["_id"]["q"]))
        if not stat:
            continue
        stat["data"]["true" if row["_id"]["value"] else "false"] += row["count"]
        stat["responses"] += row["count"]

    for row in aggregated.get("single_choice", []):
        stat = stats.get(str(row["_id"]["q"]))
        if not stat:
            continue
        choice = row["_id"]["value"]
        stat["data"][choice] = stat["data"].get(choice, 0) + row["count"]
        stat["responses"] += row["count"]

    for row in aggregated.get("multi_respondents", []):
        stat = stats.get(str(row["_id"]))
        if stat:
            stat["responses"] += row["count"]

    for row in aggregated.get("multi_choices", []):
        stat = stats.get(str(row["_id"]["q"]))
        if not stat:
            continue
        choice = row["_id"]["value"]
        stat["data"][choice] = stat["data"].get(choice, 0) + row["count"]

    for stat in stats.values():
        if stat["type"] == "score" and stat["responses"] > 0:
            stat["average"] = stat["sum"] / stat["responses"]

    return stats


@module.route("", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(id=organization_id, status="active").first()
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
    organization = models.Organization.objects(id=organization_id, status="active").first()
    if not organization:
        return abort(404)

    organization_cars = models.vehicles.Car.objects(organization=organization)

    template = None
    if template_id:
        template = models.CarFeedbackTemplate.objects(id=template_id, cars__in=organization_cars).first()
        if not template:
            return abort(404)

    form = forms.car_feedback.CarFeedbackTemplateForm(obj=template)

    cars = models.vehicles.Car.objects(organization=organization, status="active").order_by("license_plate")
    choice_cars = list(cars)
    if template:
        # คงรถที่เคยเลือกไว้ในตัวเลือกด้วย แม้จะถูกปิดใช้งานไปแล้ว ไม่ให้หลุดหายตอนบันทึกซ้ำ
        active_car_ids = {car.id for car in choice_cars}
        choice_cars.extend(car for car in template.cars if car.id not in active_car_ids)
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
            if q.get("question_id"):
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

        return redirect(url_for("vehicle_lending.car_feedback.index", organization_id=organization_id))

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
    organization = models.Organization.objects(id=organization_id, status="active").first()
    if not organization:
        return abort(404)

    organization_cars = models.vehicles.Car.objects(organization=organization)
    template = models.CarFeedbackTemplate.objects(id=template_id, cars__in=organization_cars).first()
    if not template:
        return abort(404)

    # เฉพาะรถของ organization นี้ที่ถูกผูกไว้กับแบบประเมิน
    cars = list(
        models.vehicles.Car.objects(id__in=[car.id for car in template.cars], organization=organization).order_by("license_plate")
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

    # ยอดผลตอบรับสำหรับ label ใน dropdown นับทั้งแบบประเมิน ไม่ผูกกับตัวกรองปัจจุบัน
    choice_counts = next(
        iter(
            models.car_feedback.CarFeedbackResponse.objects(feedback_template=template).aggregate(
                [
                    {
                        "$facet": {
                            "by_car": [{"$group": {"_id": "$car", "count": {"$sum": 1}}}],
                            "by_trip": [
                                {"$match": {"car_application": {"$ne": None}}},
                                {
                                    "$group": {
                                        "_id": "$car_application",
                                        "count": {"$sum": 1},
                                    }
                                },
                            ],
                        }
                    }
                ]
            )
        ),
        {},
    )
    car_response_counts = {str(row["_id"]): row["count"] for row in choice_counts.get("by_car", [])}
    trip_response_counts = {str(row["_id"]): row["count"] for row in choice_counts.get("by_trip", [])}

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
    selected_trip = next((trip for trip in trip_choices if trip["id"] == car_application_id), None)

    form = forms.car_feedback.CarFeedbackResponseFilterForm()
    form.car_id.choices = [("", f"รถทุกคัน ({len(cars)} คัน)")] + [
        (str(car.id), f"{car.license_plate} · {car_response_counts.get(str(car.id), 0)} ผลตอบรับ") for car in cars
    ]
    form.car_id.data = car_id or ""

    if trip_choices:
        trip_placeholder = f"ทุกเที่ยว ({len(trip_choices)} เที่ยว)"
    else:
        trip_placeholder = "ยังไม่มีเที่ยวรถที่ assign ไว้"
    trip_option_choices = [("", trip_placeholder)]
    for trip in trip_choices:
        label = trip["departure"]
        if not car_id and trip["license_plate"]:
            label += f" · {trip['license_plate']}"
        label += f" · {trip['location']} ({trip['response_count']})"
        trip_option_choices.append((trip["id"], label))
    form.car_application_id.choices = trip_option_choices
    form.car_application_id.data = car_application_id or ""
    if selected_car:
        form.car_application_id.label.text = f"เที่ยวรถ — เฉพาะเที่ยวของ {selected_car.license_plate}"

    filter_kwargs = {"feedback_template": template}
    if selected_car:
        filter_kwargs["car"] = selected_car
    else:
        filter_kwargs["car__in"] = cars
    if car_application_id:
        filter_kwargs["car_application"] = trip_by_id[car_application_id]

    aggregated = next(
        iter(models.car_feedback.CarFeedbackResponse.objects(**filter_kwargs).aggregate(build_stats_pipeline(template.questions))),
        {},
    )
    stats = collect_question_stats(template.questions, aggregated)

    # ตารางรายการตอบกลับดึงเท่าที่แสดงจริง ไม่ต้องโหลดทั้ง collection
    log_entries = list(
        models.car_feedback.CarFeedbackResponse.objects(**filter_kwargs)
        .only("created_date", "car", "car_application")
        .no_dereference()
        .order_by("-created_date")
        .limit(RESPONSE_LOG_LIMIT)
    )

    # เที่ยวที่ผลตอบรับอ้างถึงแต่ไม่อยู่ในรายการตัวกรอง (เช่น เที่ยวที่ถูกยกเลิกไปแล้ว)
    text_rows = aggregated.get("texts", [])
    trip_lookup = dict(trip_by_id)
    missing_trip_ids = {
        item["car_application"]
        for row in text_rows
        for item in row["items"]
        if item.get("car_application") and str(item["car_application"]) not in trip_lookup
    }
    missing_trip_ids.update(
        entry.car_application.id
        for entry in log_entries
        if entry.car_application and str(entry.car_application.id) not in trip_lookup
    )
    if missing_trip_ids:
        for trip in (
            models.vehicle_applications.CarApplication.objects(id__in=list(missing_trip_ids), organization=organization)
            .only("travel_type", "departure_datetime", "return_datetime", "location")
            .no_dereference()
        ):
            trip_lookup[str(trip.id)] = trip

    for row in text_rows:
        stat = stats.get(str(row["_id"]))
        if not stat:
            continue
        stat["responses"] += row["total"]
        stat["texts_truncated"] = row["total"] - len(row["items"])
        for item in row["items"]:
            car = car_by_id.get(str(item["car"])) if item.get("car") else None
            trip = trip_lookup.get(str(item["car_application"])) if item.get("car_application") else None
            stat["texts"].append(
                {
                    "text": item["text"],
                    "license_plate": car.license_plate if car else "",
                    "departure": trip.get_departure_datetime() if trip else "",
                    "created_date": item["created_date"],
                }
            )

    response_log = []
    for entry in log_entries:
        car = car_by_id.get(str(entry.car.id)) if entry.car else None
        trip = trip_lookup.get(str(entry.car_application.id)) if entry.car_application else None
        response_log.append(
            {
                "created_date": entry.created_date,
                "license_plate": car.license_plate if car else "",
                "trip_id": str(entry.car_application.id) if entry.car_application else "",
                "departure": trip.get_departure_datetime() if trip else "",
                "location": trip.location if trip else "",
            }
        )

    score_sum = 0
    score_count = 0
    for stat in stats.values():
        if stat["type"] == "score":
            score_sum += stat["sum"]
            score_count += stat["responses"]

    summary_row = next(iter(aggregated.get("summary", [])), {})
    summary = {
        "total_responses": summary_row.get("total", 0),
        "overall_average": (score_sum / score_count) if score_count else 0,
        "has_score": score_count > 0,
        "trips_covered": len([t for t in summary_row.get("trips", []) if t]),
        "cars_covered": len([c for c in summary_row.get("cars", []) if c]),
        "latest_response_date": summary_row.get("latest"),
    }

    return render_template(
        "/vehicle_lending/car_feedback/view.html",
        organization=organization,
        template=template,
        response_log=response_log,
        response_log_limit=RESPONSE_LOG_LIMIT,
        stats=stats,
        summary=summary,
        cars=cars,
        car_id=car_id,
        selected_car=selected_car,
        car_response_counts=car_response_counts,
        trip_choices=trip_choices,
        car_application_id=car_application_id,
        selected_trip=selected_trip,
        form=form,
    )


@module.route("/<template_id>/delete")
@acl.organization_roles_required("admin")
def delete(template_id):
    organization_id = request.args.get("organization_id")
    template = models.CarFeedbackTemplate.objects(id=template_id).first()
    if template:
        template.delete()
    return redirect(url_for("vehicle_lending.car_feedback.index", organization_id=organization_id))
