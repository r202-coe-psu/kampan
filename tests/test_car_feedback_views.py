"""Integration & security tests ของ route แบบประเมินความพึงพอใจการใช้รถยนต์"""

import json
import re

import pytest

from kampan import models


FEEDBACK_BASE = "/vehicle_lending/car_feedback"
CARS_BASE = "/vehicle_lending/cars"


@pytest.fixture
def csrf_enabled(app):
    """เปิด CSRF ชั่วคราวเพื่อยืนยันว่า route ปฏิเสธ request ที่ไม่มี token"""
    app.config["WTF_CSRF_ENABLED"] = True
    yield app
    app.config["WTF_CSRF_ENABLED"] = False


def extract_csrf_token(html):
    """ดึง CSRF token ที่หน้าเว็บ render ออกมาจริง เพื่อทดสอบ flow แบบ end-to-end"""
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "หน้าเว็บไม่ได้ render csrf_token"
    return match.group(1)


def questions_payload(*questions):
    return json.dumps(list(questions), ensure_ascii=False)


def score_question(question_text="ให้คะแนนคนขับ", **overrides):
    question = {
        "question_text": question_text,
        "question_type": "score",
        "choice_list": [],
        "is_required": False,
    }
    question.update(overrides)
    return question


@pytest.fixture
def two_orgs(create_org, create_user, assign_user_to_org, create_car, create_feedback_template, make_question):
    """หน่วยงาน A/B ที่ต่างมีแอดมิน รถ และแบบประเมินของตัวเอง"""

    def _build():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        admin_a = create_user("AdminA", "OrgA")
        admin_b = create_user("AdminB", "OrgB")
        staff_a = create_user("StaffA", "OrgA")
        assign_user_to_org(admin_a, org_a, roles=["admin"])
        assign_user_to_org(admin_b, org_b, roles=["admin"])
        assign_user_to_org(staff_a, org_a, roles=["staff"])

        car_a = create_car(org_a, "กก 1111")
        car_b = create_car(org_b, "ขข 2222")
        question_a = make_question("score", "ให้คะแนน A")
        question_b = make_question("score", "ให้คะแนน B")
        template_a = create_feedback_template(org_a, [car_a], name="ของ A", questions=[question_a])
        template_b = create_feedback_template(org_b, [car_b], name="ของ B", questions=[question_b])

        return {
            "org_a": org_a,
            "org_b": org_b,
            "admin_a": admin_a,
            "admin_b": admin_b,
            "staff_a": staff_a,
            "car_a": car_a,
            "car_b": car_b,
            "question_a": question_a,
            "question_b": question_b,
            "template_a": template_a,
            "template_b": template_b,
        }

    return _build


# --------------------------------------------------------------------------
# index
# --------------------------------------------------------------------------


def test_index_lists_only_templates_of_the_viewing_organization(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(f"{FEEDBACK_BASE}?organization_id={data['org_a'].id}")
            body = response.data.decode()

            assert response.status_code == 200
            assert "ของ A" in body
            assert "ของ B" not in body


def test_index_requires_admin_role(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["staff_a"])

            response = client.get(f"{FEEDBACK_BASE}?organization_id={data['org_a'].id}")

            assert response.status_code == 302
            assert "/login" in response.location


# --------------------------------------------------------------------------
# delete — IDOR, HTTP method และ CSRF
# --------------------------------------------------------------------------


def test_delete_is_not_reachable_by_get(app, two_orgs, login_as):
    """GET ลบข้อมูลได้จะโดน crawler/prefetch/CSRF ยิงโดยไม่ตั้งใจ"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/delete?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 405
            assert models.CarFeedbackTemplate.objects(id=data["template_a"].id).count() == 1


def test_delete_cross_tenant_is_denied(app, two_orgs, login_as):
    """แอดมินของ Org A ต้องลบแบบประเมินของ Org B ไม่ได้ (IDOR)"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/delete?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 404
            assert models.CarFeedbackTemplate.objects(id=data["template_b"].id).count() == 1


def test_delete_cross_tenant_with_foreign_organization_id_is_denied(app, two_orgs, login_as):
    """สลับ organization_id ไปเป็นของ Org B ก็ต้องไม่ผ่าน เพราะ ACL ตรวจสมาชิกภาพ"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/delete?organization_id={data['org_b'].id}"
            )

            assert response.status_code == 302
            assert "/login" in response.location
            assert models.CarFeedbackTemplate.objects(id=data["template_b"].id).count() == 1


def test_delete_removes_template_and_its_responses(app, two_orgs, login_as, create_feedback_response):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            create_feedback_response(data["template_a"], data["car_a"])
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/delete?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 302
            assert models.CarFeedbackTemplate.objects(id=data["template_a"].id).count() == 0
            assert models.CarFeedbackResponse.objects(feedback_template=data["template_a"]).count() == 0


def test_delete_without_csrf_token_is_rejected(app, csrf_enabled, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/delete?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 400
            assert models.CarFeedbackTemplate.objects(id=data["template_a"].id).count() == 1


def test_delete_succeeds_with_the_csrf_token_rendered_on_the_page(app, csrf_enabled, two_orgs, login_as):
    """ปุ่มลบต้องใช้งานได้จริงตอน CSRF เปิด ไม่ใช่แค่ปฏิเสธทุก request"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            page = client.get(f"{FEEDBACK_BASE}?organization_id={data['org_a'].id}")
            token = extract_csrf_token(page.data.decode())

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/delete?organization_id={data['org_a'].id}",
                data={"csrf_token": token},
            )

            assert response.status_code == 302
            assert models.CarFeedbackTemplate.objects(id=data["template_a"].id).count() == 0


def test_delete_requires_admin_role(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["staff_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/delete?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 302
            assert models.CarFeedbackTemplate.objects(id=data["template_a"].id).count() == 1


def test_delete_with_malformed_template_id_returns_404(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(f"{FEEDBACK_BASE}/not-an-objectid/delete?organization_id={data['org_a'].id}")

            assert response.status_code == 404


# --------------------------------------------------------------------------
# create_or_edit — WTForms validation, CSRF และการตรวจ payload คำถาม
# --------------------------------------------------------------------------


def test_create_form_renders(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}")

            assert response.status_code == 200
            assert "กก 1111" in response.data.decode()


def test_create_without_name_shows_validation_error(app, two_orgs, login_as):
    """ไม่เรียก validate จะข้าม InputRequired ของชื่อแบบประเมินไปเลย"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 200
            assert "กรุณาระบุชื่อแบบประเมิน" in response.data.decode()
            assert models.CarFeedbackTemplate.objects(organization=data["org_a"]).count() == 1


def test_create_without_cars_shows_validation_error(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 200
            assert "กรุณาเลือกรถยนต์" in response.data.decode()
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_create_without_csrf_token_is_rejected(app, csrf_enabled, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 200
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_create_succeeds_with_the_csrf_token_rendered_on_the_page(app, csrf_enabled, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            page = client.get(f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}")
            token = extract_csrf_token(page.data.decode())

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "csrf_token": token,
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 302
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 1


def test_create_rejects_car_from_another_organization(app, two_orgs, login_as):
    """รถของ Org B ไม่อยู่ใน choices ของฟอร์ม WTForms จึงตีกลับก่อนถึงชั้นบันทึก"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_b"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 200
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_edit_rejects_legacy_car_from_another_organization(app, two_orgs, login_as, create_car):
    """แบบประเมินเก่าอาจผูกรถข้ามหน่วยงานไว้ ทำให้รถนั้นอยู่ใน choices ด้วย

    ชั้นบันทึกต้องยังกันไว้อีกชั้น ไม่ให้บันทึกรถของหน่วยงานอื่นกลับลงไป
    """
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            template = data["template_a"]
            template.cars = [data["car_a"], data["car_b"]]
            template.save()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{template.id}/edit?organization_id={data['org_a'].id}",
                data={
                    "name": "ของ A",
                    "cars": [str(data["car_b"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 400


def test_create_rejects_malformed_questions_json(app, two_orgs, login_as):
    """JSON เสียต้องได้ 400 พร้อมข้อความ ไม่ใช่ 500 จาก json.loads"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": "[{broken json",
                },
            )

            assert response.status_code == 400
            assert "รูปแบบข้อมูลคำถามไม่ถูกต้อง" in response.data.decode()
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_create_rejects_blank_question_text(app, two_orgs, login_as):
    """question_text ว่างเคยหลุดไปพังเป็น mongoengine ValidationError ตอน save()"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question(question_text="")),
                },
            )

            assert response.status_code == 400
            assert "กรุณาระบุคำถามข้อที่ 1" in response.data.decode()
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_create_rejects_missing_questions_data(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={"name": "แบบประเมินใหม่", "cars": [str(data["car_a"].id)]},
            )

            assert response.status_code == 400
            assert models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").count() == 0


def test_create_keeps_submitted_questions_on_validation_error(app, two_orgs, login_as):
    """ผู้ใช้ไม่ควรเสียคำถามที่กรอกไว้เมื่อฟอร์มตีกลับ"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])
            payload = questions_payload(score_question("อยากได้คำถามนี้กลับมา"))

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={"name": "", "cars": [str(data["car_a"].id)], "questions_data": payload},
            )

            assert response.status_code == 200
            assert "อยากได้คำถามนี้กลับมา" in response.data.decode()


def test_create_saves_template_bound_to_the_organization(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "description": "รอบเดือนสิงหาคม",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(
                        score_question("ให้คะแนนคนขับ", is_required=True),
                        {
                            "question_text": "ตรงเวลาไหม",
                            "question_type": "single_choice",
                            "choice_list": ["ตรงเวลา", "สาย"],
                            "is_required": False,
                        },
                    ),
                },
            )

            assert response.status_code == 302
            template = models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").first()
            assert template is not None
            assert template.organization == data["org_a"]
            assert [car.id for car in template.cars] == [data["car_a"].id]
            assert [question.question_type for question in template.questions] == ["score", "single_choice"]
            assert template.questions[1].choice_list == ["ตรงเวลา", "สาย"]


def test_create_deduplicates_repeated_car_selection(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/create?organization_id={data['org_a'].id}",
                data={
                    "name": "แบบประเมินใหม่",
                    "cars": [str(data["car_a"].id), str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert response.status_code == 302
            template = models.CarFeedbackTemplate.objects(name="แบบประเมินใหม่").first()
            assert [car.id for car in template.cars] == [data["car_a"].id]


def test_edit_cross_tenant_is_denied(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            get_response = client.get(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/edit?organization_id={data['org_a'].id}"
            )
            post_response = client.post(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/edit?organization_id={data['org_a'].id}",
                data={
                    "name": "ยึดของ B",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(score_question()),
                },
            )

            assert get_response.status_code == 404
            assert post_response.status_code == 404
            assert models.CarFeedbackTemplate.objects(id=data["template_b"].id).first().name == "ของ B"


def test_edit_keeps_existing_question_ids(app, two_orgs, login_as, create_feedback_response, make_answer):
    """question_id ต้องไม่เปลี่ยน ไม่งั้นคำตอบเดิมจะจับคู่กับคำถามไม่ได้"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            question = data["question_a"]
            create_feedback_response(
                data["template_a"], data["car_a"], answers=[make_answer(question, score=4)]
            )
            login_as(client, data["admin_a"])

            response = client.post(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/edit?organization_id={data['org_a'].id}",
                data={
                    "name": "ของ A แก้แล้ว",
                    "cars": [str(data["car_a"].id)],
                    "questions_data": questions_payload(
                        score_question("ให้คะแนน A", question_id=str(question.question_id))
                    ),
                },
            )

            assert response.status_code == 302
            template = models.CarFeedbackTemplate.objects(id=data["template_a"].id).first()
            assert template.name == "ของ A แก้แล้ว"
            assert template.questions[0].question_id == question.question_id


# --------------------------------------------------------------------------
# qr_code
# --------------------------------------------------------------------------


def test_qr_code_cross_tenant_is_denied(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/qrcode?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 404


def test_qr_code_rejects_car_outside_the_template(app, two_orgs, login_as, create_car):
    """car_id ที่ไม่ได้ผูกกับแบบประเมินต้องไม่ถูกนำมาสร้าง QR"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            unrelated_car = create_car(data["org_a"], "คค 3333")
            login_as(client, data["admin_a"])

            unrelated_response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/qrcode"
                f"?organization_id={data['org_a'].id}&car_id={unrelated_car.id}"
            )
            foreign_response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/qrcode"
                f"?organization_id={data['org_a'].id}&car_id={data['car_b'].id}"
            )

            assert unrelated_response.status_code == 404
            assert foreign_response.status_code == 404


def test_qr_code_returns_png_for_a_car_of_the_template(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/qrcode"
                f"?organization_id={data['org_a'].id}&car_id={data['car_a'].id}"
            )

            assert response.status_code == 200
            assert response.mimetype == "image/png"
            assert response.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_qr_code_without_car_id_uses_the_first_template_car(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/qrcode?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 200
            assert response.mimetype == "image/png"


# --------------------------------------------------------------------------
# view_responses
# --------------------------------------------------------------------------


def test_view_responses_cross_tenant_is_denied(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_b'].id}/view?organization_id={data['org_a'].id}"
            )

            assert response.status_code == 404


def test_view_responses_renders_statistics(
    app, two_orgs, login_as, create_car_application, create_feedback_response, make_answer
):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            trip = create_car_application(data["org_a"], data["car_a"], location="สนามบินหาดใหญ่")
            create_feedback_response(
                data["template_a"],
                data["car_a"],
                car_application=trip,
                answers=[make_answer(data["question_a"], score=5)],
            )
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/view?organization_id={data['org_a'].id}"
            )
            body = response.data.decode()

            assert response.status_code == 200
            assert "ให้คะแนน A" in body
            assert "สนามบินหาดใหญ่" in body


def test_view_responses_ignores_unknown_filter_values(
    app, two_orgs, login_as, create_car_application, create_feedback_response, make_answer
):
    """car_id/car_application_id ที่ไม่อยู่ในตัวเลือกต้องถูกมองข้าม ไม่ใช่พังหรือรั่วข้อมูล"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            foreign_trip = create_car_application(data["org_b"], data["car_b"])
            create_feedback_response(
                data["template_a"], data["car_a"], answers=[make_answer(data["question_a"], score=2)]
            )
            login_as(client, data["admin_a"])

            response = client.get(
                f"{FEEDBACK_BASE}/{data['template_a'].id}/view"
                f"?organization_id={data['org_a'].id}"
                f"&car_id={data['car_b'].id}&car_application_id={foreign_trip.id}"
            )

            assert response.status_code == 200
            assert "ขข 2222" not in response.data.decode()


def test_view_responses_with_malformed_template_id_returns_404(app, two_orgs, login_as):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])

            response = client.get(f"{FEEDBACK_BASE}/not-an-objectid/view?organization_id={data['org_a'].id}")

            assert response.status_code == 404


def test_malformed_organization_id_is_blocked_by_acl(app, two_orgs, login_as):
    """organization_id ที่ไม่ใช่ ObjectId ต้องถูก ACL ปฏิเสธ ไม่ใช่กลายเป็น 500"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            login_as(client, data["admin_a"])
            template_id = data["template_a"].id

            for path in (
                f"{FEEDBACK_BASE}/{template_id}/view?organization_id=not-an-objectid",
                f"{FEEDBACK_BASE}/{template_id}/qrcode?organization_id=not-an-objectid",
                f"{FEEDBACK_BASE}/create?organization_id=not-an-objectid",
            ):
                response = client.get(path)
                assert response.status_code == 302, path
                assert "/login" in response.location, path


def test_global_admin_with_malformed_organization_id_gets_404(app, two_orgs, create_user, login_as):
    """global admin ข้าม ACL ได้ ชั้น view จึงต้องกัน organization_id เสียเองด้วย"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            global_admin = create_user("Super", "Admin", roles=["admin"])
            login_as(client, global_admin)
            template_id = data["template_a"].id

            for path in (
                f"{FEEDBACK_BASE}/{template_id}/view?organization_id=not-an-objectid",
                f"{FEEDBACK_BASE}/{template_id}/qrcode?organization_id=not-an-objectid",
                f"{FEEDBACK_BASE}/create?organization_id=not-an-objectid",
                f"{FEEDBACK_BASE}/{template_id}/view",
            ):
                assert client.get(path).status_code == 404, path


# --------------------------------------------------------------------------
# public feedback route — ผู้โดยสารสแกน QR เข้ามาโดยไม่ login
# --------------------------------------------------------------------------


def test_public_feedback_resolves_organization_from_the_car(app, two_orgs):
    """URL ใน QR ไม่มี organization_id หน่วยงานต้องมาจากตัวรถ"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()

            response = client.get(f"{CARS_BASE}/{data['car_a'].id}/feedback")

            assert response.status_code == 200
            assert "ให้คะแนน A" in response.data.decode()


def test_public_feedback_rejects_template_of_another_organization(app, two_orgs):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()

            response = client.get(
                f"{CARS_BASE}/{data['car_a'].id}/feedback?template_id={data['template_b'].id}"
            )

            assert response.status_code == 404


def test_public_feedback_without_a_template_reports_it(app, create_org, create_car):
    """เดิม render_template ด้วยข้อความไทยทำให้ TemplateNotFound เป็น 500"""
    with app.test_client() as client:
        with app.app_context():
            org = create_org("Org A")
            car = create_car(org, "กก 1111")

            response = client.get(f"{CARS_BASE}/{car.id}/feedback")
            body = response.data.decode()

            assert response.status_code == 404
            assert "ยังไม่มีแบบประเมินสำหรับรถคันนี้" in body
            # หน่วยงานที่ resolve จากรถถูกส่งเข้า template จริง
            assert "Org A" in body


def test_public_feedback_with_unknown_or_malformed_car_id_returns_404(app, two_orgs):
    with app.test_client() as client:
        with app.app_context():
            two_orgs()

            assert client.get(f"{CARS_BASE}/not-an-objectid/feedback").status_code == 404
            assert client.get(f"{CARS_BASE}/6710110432aaaaaaaaaaaaaa/feedback").status_code == 404


def test_public_feedback_post_saves_response_with_organization(
    app, two_orgs, create_car_application, make_question, create_feedback_template
):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            score = make_question("score", "ให้คะแนนคนขับ", is_required=True)
            text = make_question("text", "ข้อเสนอแนะ")
            template = create_feedback_template(
                data["org_a"], [data["car_a"]], name="แบบประเมินหลัก", questions=[score, text]
            )
            trip = create_car_application(data["org_a"], data["car_a"])

            response = client.post(
                f"{CARS_BASE}/{data['car_a'].id}/feedback?template_id={template.id}",
                data={
                    "car_application": str(trip.id),
                    f"answer_{score.question_id}": "5",
                    f"answer_{text.question_id}": "ประทับใจมาก",
                },
            )

            assert response.status_code == 200
            saved = models.CarFeedbackResponse.objects(feedback_template=template).first()
            assert saved is not None
            assert saved.organization == data["org_a"]
            assert saved.car == data["car_a"]
            assert saved.car_application == trip
            answers = {answer.question_id: answer for answer in saved.answers}
            assert answers[score.question_id].answer_score == 5
            assert answers[text.question_id].answer_text == "ประทับใจมาก"


def test_public_feedback_post_rejects_trip_of_another_car(
    app, two_orgs, create_car, create_car_application, make_question, create_feedback_template
):
    """เที่ยวของรถคันอื่นต้องไม่ถูกผูกเข้ากับผลตอบรับ"""
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            other_car = create_car(data["org_a"], "คค 3333")
            score = make_question("score", "ให้คะแนนคนขับ", is_required=True)
            template = create_feedback_template(
                data["org_a"], [data["car_a"]], name="แบบประเมินหลัก", questions=[score]
            )
            create_car_application(data["org_a"], data["car_a"])
            foreign_trip = create_car_application(data["org_a"], other_car)

            response = client.post(
                f"{CARS_BASE}/{data['car_a'].id}/feedback?template_id={template.id}",
                data={
                    "car_application": str(foreign_trip.id),
                    f"answer_{score.question_id}": "5",
                },
            )

            assert response.status_code == 200
            assert models.CarFeedbackResponse.objects(feedback_template=template).count() == 0


def test_public_feedback_post_requires_answers_for_required_questions(
    app, two_orgs, create_car_application, make_question, create_feedback_template
):
    with app.test_client() as client:
        with app.app_context():
            data = two_orgs()
            score = make_question("score", "ให้คะแนนคนขับ", is_required=True)
            template = create_feedback_template(
                data["org_a"], [data["car_a"]], name="แบบประเมินหลัก", questions=[score]
            )
            trip = create_car_application(data["org_a"], data["car_a"])

            response = client.post(
                f"{CARS_BASE}/{data['car_a'].id}/feedback?template_id={template.id}",
                data={"car_application": str(trip.id)},
            )

            assert response.status_code == 200
            assert models.CarFeedbackResponse.objects(feedback_template=template).count() == 0
