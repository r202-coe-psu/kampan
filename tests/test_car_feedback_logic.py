"""Unit tests ของ helper functions ในโมดูล view kampan.web.views.vehicle_lending.car_feedback"""

import datetime
import json

import pytest
from bson import DBRef, ObjectId

from kampan import models
from kampan.web.views.vehicle_lending import car_feedback as car_feedback_view


def build_payload(**overrides):
    question = {
        "question_text": "คนขับสุภาพหรือไม่",
        "question_type": "score",
        "choice_list": [],
        "is_required": True,
    }
    question.update(overrides)
    return json.dumps([question])


# --------------------------------------------------------------------------
# parse_questions_payload
# --------------------------------------------------------------------------


def test_parse_questions_payload_builds_question_templates(app):
    with app.app_context():
        questions = car_feedback_view.parse_questions_payload(build_payload())

        assert len(questions) == 1
        assert isinstance(questions[0], models.QuestionTemplate)
        assert questions[0].question_text == "คนขับสุภาพหรือไม่"
        assert questions[0].question_type == "score"
        assert questions[0].is_required is True
        assert questions[0].question_id is not None


def test_parse_questions_payload_keeps_existing_question_id(app):
    """question_id เดิมต้องคงไว้ ไม่งั้นคำตอบที่บันทึกไว้แล้วจะจับคู่กับคำถามไม่ได้"""
    with app.app_context():
        existing_id = ObjectId()
        questions = car_feedback_view.parse_questions_payload(build_payload(question_id=str(existing_id)))

        assert questions[0].question_id == existing_id


def test_parse_questions_payload_strips_blank_choices(app):
    with app.app_context():
        questions = car_feedback_view.parse_questions_payload(
            build_payload(question_type="single_choice", choice_list=["ดี", "  ", "", "แย่"])
        )

        assert questions[0].choice_list == ["ดี", "แย่"]


@pytest.mark.parametrize(
    "raw_questions",
    [
        None,
        "",
        "{not json at all",
        '{"question_text": "x"}',
        "[]",
        '["a string, not an object"]',
    ],
)
def test_parse_questions_payload_rejects_broken_json(app, raw_questions):
    """JSON ผิดรูปแบบต้องกลายเป็น QuestionPayloadError ไม่ใช่ JSONDecodeError ดิบ ๆ"""
    with app.app_context():
        with pytest.raises(car_feedback_view.QuestionPayloadError):
            car_feedback_view.parse_questions_payload(raw_questions)


@pytest.mark.parametrize(
    "overrides",
    [
        {"question_text": ""},
        {"question_text": "   "},
        {"question_text": None},
    ],
)
def test_parse_questions_payload_rejects_blank_question_text(app, overrides):
    """คำถามว่างต้องถูกปฏิเสธก่อนถึง save() ซึ่งจะพังเป็น mongoengine ValidationError"""
    with app.app_context():
        with pytest.raises(car_feedback_view.QuestionPayloadError):
            car_feedback_view.parse_questions_payload(build_payload(**overrides))


def test_parse_questions_payload_rejects_unknown_question_type(app):
    with app.app_context():
        with pytest.raises(car_feedback_view.QuestionPayloadError):
            car_feedback_view.parse_questions_payload(build_payload(question_type="sql_injection"))


@pytest.mark.parametrize("question_type", ["single_choice", "multiple_choice"])
def test_parse_questions_payload_requires_choices_for_choice_questions(app, question_type):
    with app.app_context():
        with pytest.raises(car_feedback_view.QuestionPayloadError):
            car_feedback_view.parse_questions_payload(build_payload(question_type=question_type, choice_list=[]))


def test_parse_questions_payload_rejects_invalid_question_id(app):
    with app.app_context():
        with pytest.raises(car_feedback_view.QuestionPayloadError):
            car_feedback_view.parse_questions_payload(build_payload(question_id="ไม่ใช่ objectid"))


def test_parse_questions_payload_saved_questions_pass_model_validation(app, create_org, create_car):
    """ผลลัพธ์ของ parser ต้อง save ผ่าน ไม่เหลือช่องให้ 500 ตอน template.save()"""
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        questions = car_feedback_view.parse_questions_payload(build_payload())

        template = car_feedback_view.save_template(None, org, "แบบประเมิน", "", [car], questions)

        assert models.CarFeedbackTemplate.objects(id=template.id).count() == 1


# --------------------------------------------------------------------------
# reference_id / reference_key — ปลอดภัยกับ queryset ที่ใช้ .no_dereference()
# --------------------------------------------------------------------------


def test_reference_id_handles_document_dbref_objectid_and_none(app, create_org, create_car):
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        object_id = ObjectId()

        assert car_feedback_view.reference_id(car) == car.id
        assert car_feedback_view.reference_id(DBRef("cars", object_id)) == object_id
        assert car_feedback_view.reference_id(object_id) == object_id
        assert car_feedback_view.reference_id(None) is None

        assert car_feedback_view.reference_key(DBRef("cars", object_id)) == str(object_id)
        assert car_feedback_view.reference_key(object_id) == str(object_id)
        assert car_feedback_view.reference_key(None) is None


# --------------------------------------------------------------------------
# การ query แบบผูก organization
# --------------------------------------------------------------------------


def test_get_template_is_scoped_to_organization(app, create_org, create_car, create_feedback_template):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_b = create_car(org_b, "ขข 2222")
        template_b = create_feedback_template(org_b, [car_b])

        assert car_feedback_view.get_template(template_b.id, org_b) == template_b
        assert car_feedback_view.get_template(template_b.id, org_a) is None


def test_get_template_returns_none_for_malformed_id(app, create_org):
    """id ที่ไม่ใช่ ObjectId ต้องคืน None ให้ view ตอบ 404 ไม่ใช่ระเบิดเป็น 500"""
    with app.app_context():
        org = create_org("Org A")

        assert car_feedback_view.get_template("ไม่ใช่ objectid", org) is None
        assert car_feedback_view.get_template(None, org) is None


def test_get_organization_templates_excludes_other_organizations(
    app, create_org, create_car, create_feedback_template
):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")
        template_a = create_feedback_template(org_a, [car_a], name="ของ A")
        create_feedback_template(org_b, [car_b], name="ของ B")

        templates = list(car_feedback_view.get_organization_templates(org_a))

        assert templates == [template_a]


def test_get_template_cars_drops_cars_from_other_organizations(
    app, create_org, create_car, create_feedback_template
):
    """เอกสารเก่าอาจผูกรถข้ามหน่วยงานไว้ ต้องไม่หลุดออกมาในหน้าสถิติ"""
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")
        template = create_feedback_template(org_a, [car_a, car_b])

        cars = car_feedback_view.get_template_cars(template, org_a)

        assert [car.id for car in cars] == [car_a.id]


def test_get_cars_in_organization_ignores_foreign_cars(app, create_org, create_car):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")

        cars = car_feedback_view.get_cars_in_organization([str(car_a.id), str(car_b.id)], org_a)

        assert [car.id for car in cars] == [car_a.id]


def test_get_feedback_template_for_car_is_scoped_by_car_organization(
    app, create_org, create_car, create_feedback_template
):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")
        template_a = create_feedback_template(org_a, [car_a])
        template_b = create_feedback_template(org_b, [car_b])

        assert car_feedback_view.get_feedback_template_for_car(car_a) == template_a
        # ยัด template ของหน่วยงานอื่นเข้ามาทาง query string ต้องไม่ติด
        assert car_feedback_view.get_feedback_template_for_car(car_a, template_id=template_b.id) is None


def test_get_car_trips_only_returns_used_trips(app, create_org, create_car, create_car_application):
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        active = create_car_application(org, car, status="active")
        completed = create_car_application(org, car, status="completed")
        create_car_application(org, car, status="disactive")
        create_car_application(org, car, status="pending on header")

        trips = car_feedback_view.get_car_trips(car, org)

        assert {trip.id for trip in trips} == {active.id, completed.id}


def test_delete_template_also_removes_its_responses(
    app, create_org, create_car, create_feedback_template, create_feedback_response, make_question
):
    """ไม่ให้เหลือผลตอบรับที่ชี้ไปยังแบบประเมินที่ถูกลบไปแล้ว"""
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        question = make_question("score")
        template = create_feedback_template(org, [car], questions=[question])
        other_template = create_feedback_template(org, [car], name="อีกอัน", questions=[question])
        create_feedback_response(template, car)
        create_feedback_response(template, car)
        kept = create_feedback_response(other_template, car)

        car_feedback_view.delete_template(template)

        assert models.CarFeedbackTemplate.objects(id=template.id).first() is None
        assert models.CarFeedbackResponse.objects(feedback_template=template).count() == 0
        assert models.CarFeedbackResponse.objects(id=kept.id).count() == 1


# --------------------------------------------------------------------------
# สถิติ / aggregation
# --------------------------------------------------------------------------


@pytest.fixture
def stats_fixture(
    app,
    create_org,
    create_car,
    create_car_application,
    create_feedback_template,
    create_feedback_response,
    make_question,
    make_answer,
):
    """แบบประเมินที่มีคำถามครบทุกชนิด พร้อมผลตอบรับ 3 ชุดสำหรับตรวจสถิติ"""

    def _build():
        org = create_org("Org A")
        car_one = create_car(org, "กก 1111")
        car_two = create_car(org, "ขข 2222")
        trip = create_car_application(org, car_one, location="สนามบิน")

        score = make_question("score", "ให้คะแนนคนขับ")
        boolean = make_question("boolean", "รถสะอาดไหม")
        single = make_question("single_choice", "ตรงเวลาไหม", choice_list=["ตรงเวลา", "สาย"])
        multi = make_question("multiple_choice", "ชอบอะไร", choice_list=["สุภาพ", "ขับนุ่ม", "สะอาด"])
        text = make_question("text", "ข้อเสนอแนะ")
        template = create_feedback_template(
            org, [car_one, car_two], questions=[score, boolean, single, multi, text]
        )

        create_feedback_response(
            template,
            car_one,
            car_application=trip,
            created_date=datetime.datetime(2026, 2, 1, 9, 0),
            answers=[
                make_answer(score, score=5),
                make_answer(boolean, boolean=True),
                make_answer(single, text="ตรงเวลา"),
                make_answer(multi, choices=["สุภาพ", "สะอาด"]),
                make_answer(text, text="ดีมาก"),
            ],
        )
        create_feedback_response(
            template,
            car_one,
            created_date=datetime.datetime(2026, 2, 2, 9, 0),
            answers=[
                make_answer(score, score=3),
                make_answer(boolean, boolean=False),
                make_answer(single, text="สาย"),
                make_answer(multi, choices=["ขับนุ่ม"]),
                make_answer(text, text="รอนาน"),
            ],
        )
        # ผลตอบรับที่เว้นข้อว่างไว้ ไม่ควรถูกนับเข้าค่าเฉลี่ย
        create_feedback_response(
            template,
            car_two,
            created_date=datetime.datetime(2026, 2, 3, 9, 0),
            answers=[
                make_answer(score),
                make_answer(boolean),
                make_answer(single, text=""),
                make_answer(multi, choices=[]),
                make_answer(text, text=""),
            ],
        )

        return {
            "organization": org,
            "template": template,
            "cars": [car_one, car_two],
            "trip": trip,
            "questions": {
                "score": score,
                "boolean": boolean,
                "single": single,
                "multi": multi,
                "text": text,
            },
        }

    return _build


def aggregate_stats(template):
    responses = models.CarFeedbackResponse.objects(feedback_template=template)
    aggregated = next(iter(responses.aggregate(car_feedback_view.build_stats_pipeline(template.questions))), {})
    return aggregated, car_feedback_view.collect_question_stats(template.questions, aggregated)


def test_collect_question_stats_counts_every_question_type(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        questions = data["questions"]

        _aggregated, stats = aggregate_stats(data["template"])

        score_stat = stats[str(questions["score"].question_id)]
        assert score_stat["responses"] == 2
        assert score_stat["data"] == {1: 0, 2: 0, 3: 1, 4: 0, 5: 1}
        assert score_stat["sum"] == 8
        assert score_stat["average"] == 4

        boolean_stat = stats[str(questions["boolean"].question_id)]
        assert boolean_stat["responses"] == 2
        assert boolean_stat["data"] == {"true": 1, "false": 1}

        single_stat = stats[str(questions["single"].question_id)]
        assert single_stat["responses"] == 2
        assert single_stat["data"] == {"ตรงเวลา": 1, "สาย": 1}

        # multiple_choice: responses = จำนวนคนที่ตอบ, data = จำนวนครั้งของแต่ละตัวเลือก
        multi_stat = stats[str(questions["multi"].question_id)]
        assert multi_stat["responses"] == 2
        assert multi_stat["data"] == {"สุภาพ": 1, "ขับนุ่ม": 1, "สะอาด": 1}

        text_stat = stats[str(questions["text"].question_id)]
        assert text_stat["responses"] == 0  # ข้อความถูกผนวกทีหลังใน build_response_report


def test_collect_question_stats_average_is_zero_without_answers(
    app, create_org, create_car, create_feedback_template, make_question
):
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        score = make_question("score")
        template = create_feedback_template(org, [car], questions=[score])

        _aggregated, stats = aggregate_stats(template)

        assert stats[str(score.question_id)]["responses"] == 0
        assert stats[str(score.question_id)]["average"] == 0


def test_build_response_report_summarises_all_cars(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        template = data["template"]
        cars = car_feedback_view.get_template_cars(template, data["organization"])
        trips = car_feedback_view.get_filter_trips(cars, data["organization"])

        report = car_feedback_view.build_response_report(template, data["organization"], cars, trips)

        assert report["summary"]["total_responses"] == 3
        assert report["summary"]["cars_covered"] == 2
        assert report["summary"]["trips_covered"] == 1
        assert report["summary"]["has_score"] is True
        assert report["summary"]["overall_average"] == 4
        assert report["summary"]["latest_response_date"] == datetime.datetime(2026, 2, 3, 9, 0)
        # log เรียงจากใหม่ไปเก่า
        assert [row["license_plate"] for row in report["response_log"]] == ["ขข 2222", "กก 1111", "กก 1111"]


def test_build_response_report_attaches_text_answers_with_car_and_trip(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        template = data["template"]
        cars = car_feedback_view.get_template_cars(template, data["organization"])
        trips = car_feedback_view.get_filter_trips(cars, data["organization"])

        report = car_feedback_view.build_response_report(template, data["organization"], cars, trips)
        text_stat = report["stats"][str(data["questions"]["text"].question_id)]

        assert text_stat["responses"] == 2
        assert text_stat["texts_truncated"] == 0
        assert [item["text"] for item in text_stat["texts"]] == ["รอนาน", "ดีมาก"]
        assert text_stat["texts"][1]["license_plate"] == "กก 1111"
        assert text_stat["texts"][1]["departure"] == data["trip"].get_departure_datetime()


def test_build_response_report_truncates_text_answers_at_limit(app, stats_fixture, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(car_feedback_view, "TEXT_ANSWER_LIMIT", 1)
        data = stats_fixture()
        template = data["template"]
        cars = car_feedback_view.get_template_cars(template, data["organization"])

        report = car_feedback_view.build_response_report(template, data["organization"], cars, [])
        text_stat = report["stats"][str(data["questions"]["text"].question_id)]

        assert text_stat["responses"] == 2
        assert len(text_stat["texts"]) == 1
        assert text_stat["texts_truncated"] == 1


def test_build_response_report_filters_by_selected_car(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        template = data["template"]
        organization = data["organization"]
        cars = car_feedback_view.get_template_cars(template, organization)
        selected_car = next(car for car in cars if car.license_plate == "ขข 2222")

        report = car_feedback_view.build_response_report(
            template, organization, cars, [], selected_car=selected_car
        )

        assert report["summary"]["total_responses"] == 1
        assert report["summary"]["cars_covered"] == 1
        assert [row["license_plate"] for row in report["response_log"]] == ["ขข 2222"]


def test_build_response_report_filters_by_selected_trip(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        template = data["template"]
        organization = data["organization"]
        cars = car_feedback_view.get_template_cars(template, organization)
        trips = car_feedback_view.get_filter_trips(cars, organization)

        report = car_feedback_view.build_response_report(
            template, organization, cars, trips, selected_trip=trips[0]
        )

        assert report["summary"]["total_responses"] == 1
        assert report["summary"]["trips_covered"] == 1
        assert report["stats"][str(data["questions"]["score"].question_id)]["average"] == 5


def test_build_response_report_ignores_responses_of_foreign_cars(
    app,
    create_org,
    create_car,
    create_feedback_template,
    create_feedback_response,
    make_question,
    make_answer,
):
    """ไม่มีตัวกรองรถ = จำกัดไว้แค่รถของหน่วยงานนี้ ไม่ใช่ทุกผลตอบรับของแบบประเมิน"""
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")
        score = make_question("score")
        template = create_feedback_template(org_a, [car_a, car_b], questions=[score])
        create_feedback_response(template, car_a, answers=[make_answer(score, score=4)])
        create_feedback_response(template, car_b, answers=[make_answer(score, score=1)])

        cars = car_feedback_view.get_template_cars(template, org_a)
        report = car_feedback_view.build_response_report(template, org_a, cars, [])

        assert report["summary"]["total_responses"] == 1
        assert report["stats"][str(score.question_id)]["average"] == 4


def test_build_response_report_resolves_trips_outside_the_filter(
    app,
    create_org,
    create_car,
    create_car_application,
    create_feedback_template,
    create_feedback_response,
    make_question,
    make_answer,
):
    """เที่ยวที่ถูกยกเลิกหลังผู้โดยสารประเมินแล้ว ยังต้องแสดงวันเดินทางได้"""
    with app.app_context():
        org = create_org("Org A")
        car = create_car(org, "กก 1111")
        cancelled_trip = create_car_application(org, car, status="disactive", location="ยกเลิกแล้ว")
        text = make_question("text")
        template = create_feedback_template(org, [car], questions=[text])
        create_feedback_response(
            template,
            car,
            car_application=cancelled_trip,
            answers=[make_answer(text, text="ประทับใจ")],
        )

        cars = car_feedback_view.get_template_cars(template, org)
        trips = car_feedback_view.get_filter_trips(cars, org)
        report = car_feedback_view.build_response_report(template, org, cars, trips)

        assert trips == []
        assert report["response_log"][0]["location"] == "ยกเลิกแล้ว"
        text_stat = report["stats"][str(text.question_id)]
        assert text_stat["texts"][0]["departure"] == cancelled_trip.get_departure_datetime()


def test_get_response_choice_counts_groups_by_car_and_trip(app, stats_fixture):
    with app.app_context():
        data = stats_fixture()
        car_one, car_two = data["cars"]

        car_counts, trip_counts = car_feedback_view.get_response_choice_counts(data["template"])

        assert car_counts == {str(car_one.id): 2, str(car_two.id): 1}
        assert trip_counts == {str(data["trip"].id): 1}


def test_get_filter_trips_returns_empty_without_cars(app, create_org):
    with app.app_context():
        org = create_org("Org A")

        assert car_feedback_view.get_filter_trips([], org) == []
