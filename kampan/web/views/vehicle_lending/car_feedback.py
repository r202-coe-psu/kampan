import io
import json

import mongoengine as me
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

CHOICE_QUESTION_TYPES = ["single_choice", "multiple_choice"]

TRIP_LOOKUP_FIELDS = ["travel_type", "departure_datetime", "return_datetime", "location"]


class QuestionPayloadError(ValueError):
    """คำถามที่ client ส่งมาไม่ถูกรูปแบบ route จะแปลงเป็น HTTP 400 พร้อมข้อความนี้"""


# --------------------------------------------------------------------------
# Helpers: ตัว query / business logic ของฟีเจอร์นี้
#
# ตามหลักแล้วควรอยู่ชั้น repository แต่โปรเจกต์ยังไม่มีชั้นนั้น จึงพักไว้ในโมดูล
# ของ route นี้ก่อน ไม่ปนกับ kampan/controllers/ ที่เป็นงาน background/service
# --------------------------------------------------------------------------


def get_active_organization():
    """หน่วยงานที่กำลังเปิดดูอยู่ จาก query string หรือ form ของ request ปัจจุบัน

    ACL ตรวจสมาชิกภาพให้แล้ว ที่นี่แค่ยืนยันว่าหน่วยงานยังใช้งานอยู่จริง
    และคืน ``None`` เมื่อ id ไม่ใช่ ObjectId ที่ใช้ได้ เพื่อไม่ให้กลายเป็น 500
    """
    organization_id = request.args.get("organization_id") or request.form.get("organization_id")
    if not organization_id:
        return None

    try:
        return models.Organization.objects(id=organization_id, status="active").first()
    except (me.errors.ValidationError, me.errors.InvalidQueryError):
        return None


def reference_id(value):
    """คืน id ของ reference field ที่อาจเป็น Document, DBRef หรือ ObjectId

    queryset ที่ใช้ ``.no_dereference()`` จะคืนค่า reference เป็น DBRef/ObjectId
    แทน Document การเรียก ``.id`` ตรง ๆ จึงพัง AttributeError ในบางกรณี
    """
    if value is None:
        return None

    return getattr(value, "id", value)


def reference_key(value):
    """แปลง reference เป็น str ของ id เพื่อใช้เป็น key ของ dict lookup"""
    resolved = reference_id(value)
    return str(resolved) if resolved is not None else None


def parse_questions_payload(raw_questions):
    """แปลง JSON คำถามจากฟอร์มเป็น QuestionTemplate พร้อมตรวจความถูกต้อง

    ตรวจที่นี่เพื่อให้ client ที่ส่งข้อมูลผิดรูปแบบได้ HTTP 400 แทนที่จะไป
    ระเบิดเป็น 500 ตอน ``json.loads`` หรือตอน ``save()`` ของ mongoengine
    """
    if not raw_questions:
        raise QuestionPayloadError("กรุณาเพิ่มคำถามในแบบประเมินอย่างน้อย 1 ข้อ")

    try:
        payload = json.loads(raw_questions)
    except (TypeError, ValueError):
        raise QuestionPayloadError("รูปแบบข้อมูลคำถามไม่ถูกต้อง")

    if not isinstance(payload, list) or not payload:
        raise QuestionPayloadError("กรุณาเพิ่มคำถามในแบบประเมินอย่างน้อย 1 ข้อ")

    valid_types = [value for value, _label in models.QUESTION_TYPE]

    questions = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise QuestionPayloadError(f"ข้อมูลคำถามข้อที่ {index} ไม่ถูกรูปแบบ")

        question_text = (item.get("question_text") or "").strip()
        if not question_text:
            raise QuestionPayloadError(f"กรุณาระบุคำถามข้อที่ {index}")

        question_type = item.get("question_type")
        if question_type not in valid_types:
            raise QuestionPayloadError(f"ชนิดของคำถามข้อที่ {index} ไม่ถูกต้อง")

        raw_choices = item.get("choice_list") or []
        if not isinstance(raw_choices, list):
            raise QuestionPayloadError(f"ตัวเลือกของคำถามข้อที่ {index} ไม่ถูกรูปแบบ")

        choice_list = [str(choice).strip() for choice in raw_choices if str(choice).strip()]
        if question_type in CHOICE_QUESTION_TYPES and not choice_list:
            raise QuestionPayloadError(f"กรุณาระบุตัวเลือกของคำถามข้อที่ {index}")

        question = models.QuestionTemplate(
            question_text=question_text,
            question_type=question_type,
            choice_list=choice_list,
            is_required=bool(item.get("is_required", False)),
        )

        # question_id เดิมต้องคงไว้ ไม่งั้นคำตอบที่บันทึกไว้แล้วจะจับคู่กับคำถามไม่ได้
        raw_question_id = item.get("question_id")
        if raw_question_id:
            try:
                question.question_id = ObjectId(raw_question_id)
            except Exception:
                raise QuestionPayloadError(f"รหัสของคำถามข้อที่ {index} ไม่ถูกต้อง")

        questions.append(question)

    return questions


def get_organization_templates(organization):
    """แบบประเมินทั้งหมดของหน่วยงาน"""
    return models.CarFeedbackTemplate.objects(organization=organization).order_by("name")


def get_template(template_id, organization):
    """ดึงแบบประเมินที่ผูกกับหน่วยงานนี้เท่านั้น กัน IDOR ข้ามหน่วยงาน

    คืน ``None`` เมื่อ id ไม่ใช่ ObjectId ที่ใช้ได้ เพื่อให้ route ตอบ 404 ไม่ใช่ 500
    """
    if not template_id:
        return None

    try:
        return models.CarFeedbackTemplate.objects(id=template_id, organization=organization).first()
    except (me.errors.ValidationError, me.errors.InvalidQueryError):
        return None


def get_selectable_cars(organization):
    """รถที่ใช้งานได้ของหน่วยงาน สำหรับเป็นตัวเลือกในฟอร์มแบบประเมิน"""
    return models.vehicles.Car.objects(organization=organization, status="active").order_by("license_plate")


def get_cars_in_organization(car_ids, organization):
    """ดึงรถตาม id ที่เลือก โดยบังคับว่าต้องเป็นรถของหน่วยงานนี้"""
    if not car_ids:
        return []

    try:
        return list(models.vehicles.Car.objects(id__in=list(car_ids), organization=organization))
    except (me.errors.ValidationError, me.errors.InvalidQueryError):
        return []


def get_template_cars(template, organization):
    """รถของหน่วยงานนี้ที่ผูกไว้กับแบบประเมิน เรียงตามทะเบียน"""
    car_ids = [reference_id(car) for car in template.cars if car]
    if not car_ids:
        return []

    return list(models.vehicles.Car.objects(id__in=car_ids, organization=organization).order_by("license_plate"))


def save_template(template, organization, name, description, cars, questions):
    """บันทึกแบบประเมิน โดยตรึง organization ไว้กับเอกสารเสมอ"""
    if template is None:
        template = models.CarFeedbackTemplate()

    template.organization = organization
    template.name = name
    template.description = description or ""
    template.cars = list(cars)
    template.questions = list(questions)
    template.save()

    return template


def delete_template(template):
    """ลบแบบประเมินพร้อมผลตอบรับ ไม่ให้เหลือ response ที่ชี้ไปยัง template ที่หายไป"""
    models.CarFeedbackResponse.objects(feedback_template=template).delete()
    template.delete()


def get_feedback_template_for_car(car, template_id=None):
    """หาแบบประเมินของรถคันนี้ สำหรับหน้าให้ผู้โดยสารกรอก (public route)

    scope ด้วย organization ของรถ ไม่ใช่ค่าจาก query string ที่ผู้ใช้ส่งมาได้
    """
    query = {"cars": car, "organization": car.organization}
    if template_id:
        query["id"] = template_id

    try:
        return models.CarFeedbackTemplate.objects(**query).first()
    except (me.errors.ValidationError, me.errors.InvalidQueryError):
        return None


def get_car_trips(car, organization):
    """เที่ยวรถของรถคันนี้ที่เกิดการใช้งานจริง เรียงจากเที่ยวล่าสุด"""
    return list(
        models.vehicle_applications.CarApplication.objects(
            car=car,
            organization=organization,
            status__in=FEEDBACK_TRIP_STATUS,
        ).order_by("-departure_datetime")
    )


def get_filter_trips(cars, organization):
    """เที่ยวรถที่ใช้เป็นตัวกรองในหน้าสถิติ = เฉพาะเที่ยวที่รถเหล่านี้ถูก assign ไว้"""
    if not cars:
        return []

    return list(
        models.vehicle_applications.CarApplication.objects(
            car__in=list(cars),
            organization=organization,
            status__in=FEEDBACK_TRIP_STATUS,
        )
        .no_dereference()
        .order_by("-departure_datetime")
    )


def get_response_choice_counts(template):
    """นับผลตอบรับต่อคันและต่อเที่ยว สำหรับ label ใน dropdown ตัวกรอง

    ตัวเลขนี้นับทั้งแบบประเมิน ไม่ผูกกับตัวกรองปัจจุบัน ผู้ใช้จึงเห็นได้ว่า
    ตัวเลือกไหนมีข้อมูลให้ดูก่อนจะกดกรอง
    """
    facets = next(
        iter(
            models.CarFeedbackResponse.objects(feedback_template=template).aggregate(
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

    car_counts = {reference_key(row["_id"]): row["count"] for row in facets.get("by_car", []) if row["_id"]}
    trip_counts = {reference_key(row["_id"]): row["count"] for row in facets.get("by_trip", []) if row["_id"]}

    return car_counts, trip_counts


def build_stats_pipeline(questions):
    """สร้าง aggregation pipeline เดียวที่สรุปสถิติของทุกชนิดคำถามพร้อมกัน"""
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
                            # $ifNull ทำให้ key ยังอยู่ครบแม้ผลตอบรับนั้นไม่ได้ผูกเที่ยวรถ
                            # โครงสร้างของ item จึงคงที่ไม่ว่าข้อมูลจะครบหรือไม่
                            "items": {
                                "$push": {
                                    "text": "$answers.answer_text",
                                    "car": "$car",
                                    "car_application": {"$ifNull": ["$car_application", None]},
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
        elif question.question_type in CHOICE_QUESTION_TYPES:
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


def build_response_filter(template, cars, selected_car=None, selected_trip=None):
    """เงื่อนไข query ของผลตอบรับตามตัวกรองที่ผู้ใช้เลือก

    ไม่มีตัวกรองรถ = จำกัดไว้แค่รถของหน่วยงานนี้ ไม่ใช่ทุกผลตอบรับของแบบประเมิน
    """
    filter_kwargs = {"feedback_template": template}
    if selected_car:
        filter_kwargs["car"] = selected_car
    else:
        filter_kwargs["car__in"] = list(cars)
    if selected_trip:
        filter_kwargs["car_application"] = selected_trip

    return filter_kwargs


def resolve_trip_lookup(organization, trips, text_rows, log_entries):
    """เติมเที่ยวรถที่ผลตอบรับอ้างถึงแต่ไม่อยู่ในตัวกรอง (เช่น เที่ยวที่ถูกยกเลิกแล้ว)"""
    trip_lookup = {reference_key(trip.id): trip for trip in trips}

    missing_trip_ids = {
        reference_id(item["car_application"])
        for row in text_rows
        for item in row["items"]
        if item.get("car_application") and reference_key(item["car_application"]) not in trip_lookup
    }
    missing_trip_ids.update(
        reference_id(entry.car_application)
        for entry in log_entries
        if entry.car_application and reference_key(entry.car_application) not in trip_lookup
    )

    if not missing_trip_ids:
        return trip_lookup

    for trip in (
        models.vehicle_applications.CarApplication.objects(id__in=list(missing_trip_ids), organization=organization)
        .only(*TRIP_LOOKUP_FIELDS)
        .no_dereference()
    ):
        trip_lookup[reference_key(trip.id)] = trip

    return trip_lookup


def attach_text_answers(stats, text_rows, car_by_id, trip_lookup):
    """ผนวกคำตอบแบบข้อความเข้ากับสถิติ พร้อม resolve ทะเบียนรถและเที่ยวรถ"""
    for row in text_rows:
        stat = stats.get(str(row["_id"]))
        if not stat:
            continue

        stat["responses"] += row["total"]
        stat["texts_truncated"] = row["total"] - len(row["items"])
        for item in row["items"]:
            car = car_by_id.get(reference_key(item["car"])) if item.get("car") else None
            trip = trip_lookup.get(reference_key(item["car_application"])) if item.get("car_application") else None
            stat["texts"].append(
                {
                    "text": item["text"],
                    "license_plate": car.license_plate if car else "",
                    "departure": trip.get_departure_datetime() if trip else "",
                    "created_date": item["created_date"],
                }
            )


def build_response_log(log_entries, car_by_id, trip_lookup):
    """แถวของตารางรายการตอบกลับล่าสุด"""
    response_log = []
    for entry in log_entries:
        car = car_by_id.get(reference_key(entry.car)) if entry.car else None
        trip = trip_lookup.get(reference_key(entry.car_application)) if entry.car_application else None
        response_log.append(
            {
                "created_date": entry.created_date,
                "license_plate": car.license_plate if car else "",
                "trip_id": reference_key(entry.car_application) or "",
                "departure": trip.get_departure_datetime() if trip else "",
                "location": trip.location if trip else "",
            }
        )

    return response_log


def build_summary(stats, aggregated):
    """การ์ดสรุปด้านบนของหน้าสถิติ"""
    score_sum = 0
    score_count = 0
    for stat in stats.values():
        if stat["type"] == "score":
            score_sum += stat["sum"]
            score_count += stat["responses"]

    summary_row = next(iter(aggregated.get("summary", [])), {})

    return {
        "total_responses": summary_row.get("total", 0),
        "overall_average": (score_sum / score_count) if score_count else 0,
        "has_score": score_count > 0,
        "trips_covered": len([trip for trip in summary_row.get("trips", []) if trip]),
        "cars_covered": len([car for car in summary_row.get("cars", []) if car]),
        "latest_response_date": summary_row.get("latest"),
    }


def build_response_report(template, organization, cars, trips, selected_car=None, selected_trip=None):
    """สถิติ ข้อความ log และการ์ดสรุปของหน้าดูผลตอบรับ

    ทุกอย่างมาจาก aggregation ครั้งเดียวบวก query log ที่จำกัดจำนวนแถวไว้แล้ว
    """
    filter_kwargs = build_response_filter(template, cars, selected_car=selected_car, selected_trip=selected_trip)
    car_by_id = {str(car.id): car for car in cars}

    aggregated = next(
        iter(models.CarFeedbackResponse.objects(**filter_kwargs).aggregate(build_stats_pipeline(template.questions))),
        {},
    )
    stats = collect_question_stats(template.questions, aggregated)

    # ตารางรายการตอบกลับดึงเท่าที่แสดงจริง ไม่ต้องโหลดทั้ง collection
    log_entries = list(
        models.CarFeedbackResponse.objects(**filter_kwargs)
        .only("created_date", "car", "car_application")
        .no_dereference()
        .order_by("-created_date")
        .limit(RESPONSE_LOG_LIMIT)
    )

    text_rows = aggregated.get("texts", [])
    trip_lookup = resolve_trip_lookup(organization, trips, text_rows, log_entries)

    attach_text_answers(stats, text_rows, car_by_id, trip_lookup)

    return {
        "stats": stats,
        "response_log": build_response_log(log_entries, car_by_id, trip_lookup),
        "summary": build_summary(stats, aggregated),
    }


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@module.route("", methods=["GET"])
@acl.organization_roles_required("admin")
def index():
    organization = get_active_organization()
    if not organization:
        return abort(404)

    templates = get_organization_templates(organization)

    return render_template(
        "/vehicle_lending/car_feedback/index.html",
        organization=organization,
        templates=templates,
        delete_form=forms.car_feedback.CarFeedbackTemplateDeleteForm(),
    )


@module.route("/create", methods=["GET", "POST"], defaults={"template_id": None})
@module.route("/<template_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(template_id):
    organization = get_active_organization()
    if not organization:
        return abort(404)

    template = None
    if template_id:
        template = get_template(template_id, organization)
        if not template:
            return abort(404)

    form = forms.car_feedback.CarFeedbackTemplateForm(obj=template)

    cars = get_selectable_cars(organization)
    choice_cars = list(cars)
    if template:
        active_car_ids = {car.id for car in choice_cars}
        choice_cars.extend(car for car in template.cars if car.id not in active_car_ids)
    car_choices = [(str(car.id), car.license_plate) for car in choice_cars]
    form.cars.choices = car_choices

    if template and request.method == "GET":
        form.cars.data = [str(car.id) for car in template.cars]

    def render_form(questions_error=None, status_code=200):
        return (
            render_template(
                "/vehicle_lending/car_feedback/create_or_edit.html",
                organization=organization,
                template=template,
                template_id=template_id,
                cars=cars,
                car_choices=car_choices,
                form=form,
                questions_data=request.form.get("questions_data", ""),
                questions_error=questions_error,
            ),
            status_code,
        )

    # validate_on_submit ครอบทั้ง CSRF token และ field validators ของ WTForms
    if not form.validate_on_submit():
        return render_form()

    car_ids = list(dict.fromkeys(form.cars.data or []))
    selected_cars = get_cars_in_organization(car_ids, organization)
    if len(selected_cars) != len(car_ids):
        return abort(400, "Invalid car selection")

    try:
        questions = parse_questions_payload(request.form.get("questions_data"))
    except QuestionPayloadError as error:
        return render_form(questions_error=str(error), status_code=400)

    save_template(
        template,
        organization,
        name=form.name.data,
        description=form.description.data,
        cars=selected_cars,
        questions=questions,
    )

    return redirect(url_for("vehicle_lending.car_feedback.index", organization_id=organization.id))


@module.route("/<template_id>/qrcode")
@acl.organization_roles_required("admin")
def qr_code(template_id):
    organization = get_active_organization()
    if not organization:
        return abort(404)

    template = get_template(template_id, organization)
    if not template:
        return abort(404)

    # จำกัดไว้แค่รถของหน่วยงานนี้ที่ผูกกับแบบประเมิน กันการสร้าง QR ของรถหน่วยงานอื่น
    template_cars = get_template_cars(template, organization)
    if not template_cars:
        return abort(404)

    car_id = request.args.get("car_id")
    if car_id:
        car = next((item for item in template_cars if str(item.id) == car_id), None)
    else:
        car = template_cars[0]

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
    organization = get_active_organization()
    if not organization:
        return abort(404)

    template = get_template(template_id, organization)
    if not template:
        return abort(404)

    cars = get_template_cars(template, organization)
    car_by_id = {str(car.id): car for car in cars}

    selected_car = car_by_id.get(request.args.get("car_id"))
    car_id = str(selected_car.id) if selected_car else None

    trips = get_filter_trips([selected_car] if selected_car else cars, organization)
    trip_by_id = {str(trip.id): trip for trip in trips}

    car_response_counts, trip_response_counts = get_response_choice_counts(template)

    trip_choices = []
    for trip in trips:
        trip_car = car_by_id.get(reference_key(trip.car)) if trip.car else None
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

    report = build_response_report(
        template,
        organization,
        cars,
        trips,
        selected_car=selected_car,
        selected_trip=trip_by_id.get(car_application_id),
    )

    return render_template(
        "/vehicle_lending/car_feedback/view.html",
        organization=organization,
        template=template,
        response_log=report["response_log"],
        response_log_limit=RESPONSE_LOG_LIMIT,
        stats=report["stats"],
        summary=report["summary"],
        cars=cars,
        car_id=car_id,
        selected_car=selected_car,
        car_response_counts=car_response_counts,
        trip_choices=trip_choices,
        car_application_id=car_application_id,
        selected_trip=selected_trip,
        form=form,
    )


@module.route("/<template_id>/delete", methods=["POST"])
@acl.organization_roles_required("admin")
def delete(template_id):
    organization = get_active_organization()
    if not organization:
        return abort(404)

    form = forms.car_feedback.CarFeedbackTemplateDeleteForm()
    if not form.validate_on_submit():
        return abort(400, "Invalid CSRF token")

    template = get_template(template_id, organization)
    if not template:
        return abort(404)

    delete_template(template)

    return redirect(url_for("vehicle_lending.car_feedback.index", organization_id=organization.id))
