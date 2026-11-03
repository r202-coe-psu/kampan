import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas

from kampan import models
from kampan.web import redis_rq


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """Mock redis queue to prevent actual Redis connections in tests."""
    mock_q = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", mock_q, create=True):
        yield mock_q


@pytest.fixture
def head_admin_setup(create_org, create_user, assign_user_to_org, create_car):
    org = create_org(name="กองกายภาพ")
    division = models.Division(name="ฝ่ายอาคาร", organization=org)
    division.save()

    staff = create_user("Staff", "User")
    head = create_user("Head", "User")
    admin = create_user("Admin", "User")

    staff_role = assign_user_to_org(staff, org, roles=["staff"])
    staff_role.division = division
    staff_role.save()
    head_role = assign_user_to_org(head, org, roles=["head"])
    head_role.division = division
    head_role.save()
    assign_user_to_org(admin, org, roles=["admin"])

    car = create_car(org, license_plate="กข-1234")

    template = models.car_form_templates.CarFormTemplate(
        organization=org,
        name="head แล้ว admin จัดรถ",
        steps=[
            models.car_form_templates.ApprovalStepDef(
                key="head",
                label="ผู้บังคับบัญชา",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            models.car_form_templates.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
        ],
    )
    template.save()

    return {
        "org": org,
        "staff": staff,
        "head": head,
        "admin": admin,
        "car": car,
        "template": template,
    }


def test_request_from_template_becomes_active_after_head_and_admin_approve(
    app, head_admin_setup, login_as
):
    """คำขอจาก template ที่ flow เป็น head -> admin(จัดรถ) ต้องเป็น active พร้อมรถหลังอนุมัติครบ 2 ขั้น"""
    s = head_admin_setup
    org_id = str(s["org"].id)

    staff_client = login_as(app.test_client(), s["staff"])
    res = staff_client.post(
        f"/vehicle_lending/car_form_requests/new/{s['template'].id}",
        data={
            "organization_id": org_id,
            "phone": "0812345678",
            "location": "จ.สงขลา",
            "request_reason": "ตรวจงานก่อสร้าง",
            "passenger_number": "3",
            "departure_date": "2026-03-10",
            "departure_time": "08:30",
            "return_date": "2026-03-10",
            "return_time": "16:30",
        },
    )
    assert res.status_code == 302

    car_app = models.vehicle_applications.CarApplication.objects(
        organization=s["org"]
    ).first()
    assert car_app is not None

    head_client = login_as(app.test_client(), s["head"])
    res = head_client.post(
        f"/vehicle_lending/car_form_requests/{car_app.id}/approve",
        data={"organization_id": org_id},
    )
    assert res.status_code == 302

    admin_client = login_as(app.test_client(), s["admin"])
    res = admin_client.post(
        f"/vehicle_lending/car_form_requests/{car_app.id}/approve",
        data={"organization_id": org_id, "car": str(s["car"].id)},
    )
    assert res.status_code == 302

    car_app.reload()
    assert car_app.status == "active"
    assert car_app.car == s["car"]
    assert [a.step_key for a in car_app.step_approvals] == ["head", "admin"]
    assert [a.decision for a in car_app.step_approvals] == ["approved", "approved"]


def test_head_denial_with_reason_denies_request_and_blocks_further_approval(
    app, head_admin_setup, login_as
):
    """head ที่เป็นผู้อนุมัติขั้นปัจจุบันปฏิเสธพร้อมเหตุผล คำขอต้องเป็น denied และอนุมัติต่อไม่ได้ (403)"""
    s = head_admin_setup
    org_id = str(s["org"].id)

    staff_client = login_as(app.test_client(), s["staff"])
    res = staff_client.post(
        f"/vehicle_lending/car_form_requests/new/{s['template'].id}",
        data={
            "organization_id": org_id,
            "phone": "0812345678",
            "location": "จ.สงขลา",
            "request_reason": "ตรวจงานก่อสร้าง",
            "passenger_number": "3",
            "departure_date": "2026-03-10",
            "departure_time": "08:30",
            "return_date": "2026-03-10",
            "return_time": "16:30",
        },
    )
    assert res.status_code == 302
    car_app = models.vehicle_applications.CarApplication.objects(
        organization=s["org"]
    ).first()

    head_client = login_as(app.test_client(), s["head"])
    res = head_client.post(
        f"/vehicle_lending/car_form_requests/{car_app.id}/deny",
        data={"organization_id": org_id, "denied_reason": "รถไม่ว่าง"},
    )
    assert res.status_code == 302

    car_app.reload()
    assert car_app.status == "denied"
    assert car_app.denied_reason == "รถไม่ว่าง"
    assert [(a.step_key, a.decision) for a in car_app.step_approvals] == [
        ("head", "denied")
    ]

    res = head_client.post(
        f"/vehicle_lending/car_form_requests/{car_app.id}/approve",
        data={"organization_id": org_id},
    )
    # acl แปลง 403 เป็น redirect ไปหน้า login (unauthorized_callback)
    assert res.status_code in (302, 403)
    if res.status_code == 302:
        assert "/login" in res.headers["Location"]

    car_app.reload()
    assert car_app.status == "denied"
    assert len(car_app.step_approvals) == 1


BASE = "/vehicle_lending/car_form_requests"


def _submit(client, template, org, **extra):
    return client.post(
        f"{BASE}/new/{template.id}",
        data={
            "organization_id": str(org.id),
            "phone": "0812345678",
            "location": "จ.สงขลา",
            "request_reason": "ตรวจงานก่อสร้าง",
            "passenger_number": "3",
            "departure_date": "2026-03-10",
            "departure_time": "08:30",
            "return_date": "2026-03-10",
            "return_time": "16:30",
            **extra,
        },
    )


def _approve(client, car_app, org, **extra):
    return client.post(
        f"{BASE}/{car_app.id}/approve",
        data={"organization_id": str(org.id), **extra},
    )


def _assert_forbidden(res):
    # acl แปลง 403 เป็น redirect ไปหน้า login (unauthorized_callback)
    assert res.status_code in (302, 403)
    if res.status_code == 302:
        assert "/login" in res.headers["Location"]


def _submit_and_get(app, login_as, s):
    res = _submit(login_as(app.test_client(), s["staff"]), s["template"], s["org"])
    assert res.status_code == 302
    return models.vehicle_applications.CarApplication.objects(
        organization=s["org"]
    ).first()


def test_head_from_another_division_cannot_approve_same_division_step(
    app, head_admin_setup, login_as, create_user, assign_user_to_org
):
    """head ต่างฝ่ายอนุมัติขั้นที่ same_division=True ไม่ได้ และสถานะคำขอไม่เปลี่ยน"""
    s = head_admin_setup
    other_division = models.Division(name="ฝ่ายอื่น", organization=s["org"])
    other_division.save()
    other_head = create_user("Otherhead", "User")
    role = assign_user_to_org(other_head, s["org"], roles=["head"])
    role.division = other_division
    role.save()

    car_app = _submit_and_get(app, login_as, s)

    res = _approve(login_as(app.test_client(), other_head), car_app, s["org"])

    _assert_forbidden(res)
    car_app.reload()
    assert car_app.status == "pending"
    assert car_app.current_step == 0
    assert len(car_app.step_approvals) == 0


def test_user_step_can_only_be_approved_by_that_specific_user(
    app, create_org, create_user, assign_user_to_org, create_car, login_as
):
    """ขั้น approver_type='user' อนุมัติได้เฉพาะ user นั้น ผู้ใช้อื่นที่มีทุก role ก็อนุมัติไม่ได้"""
    org = create_org(name="หน่วยงาน user-step")
    staff = create_user("Requester", "User")
    chosen = create_user("Chosen", "User")
    other = create_user("Another", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    assign_user_to_org(chosen, org, roles=["staff"])
    assign_user_to_org(
        other, org, roles=["admin", "head", "director", "endorser", "staff"]
    )
    car = create_car(org, license_plate="งจ-5555")
    template = models.car_form_templates.CarFormTemplate(
        organization=org,
        name="เจาะจงผู้อนุมัติ",
        steps=[
            models.car_form_templates.ApprovalStepDef(
                key="chosen",
                label="ผู้อนุมัติที่ระบุ",
                approver_type="user",
                user=chosen,
                assigns_vehicle=True,
            )
        ],
    )
    template.save()

    res = _submit(login_as(app.test_client(), staff), template, org)
    assert res.status_code == 302
    car_app = models.vehicle_applications.CarApplication.objects(
        organization=org
    ).first()

    res = _approve(login_as(app.test_client(), other), car_app, org, car=str(car.id))
    _assert_forbidden(res)
    car_app.reload()
    assert car_app.status == "pending"
    assert len(car_app.step_approvals) == 0

    res = _approve(login_as(app.test_client(), chosen), car_app, org, car=str(car.id))
    assert res.status_code == 302
    car_app.reload()
    assert car_app.status == "active"
    assert [a.step_key for a in car_app.step_approvals] == ["chosen"]


def test_user_of_org_b_cannot_submit_request_with_org_a_template(
    app, head_admin_setup, create_org, create_user, assign_user_to_org, login_as
):
    """ผู้ใช้ org B ส่งคำขอด้วย template ของ org A ไม่ได้ (404) และไม่เกิด CarApplication"""
    s = head_admin_setup
    org_b = create_org(name="หน่วยงาน B")
    user_b = create_user("Outsider", "User")
    assign_user_to_org(user_b, org_b, roles=["staff"])

    res = _submit(login_as(app.test_client(), user_b), s["template"], org_b)

    assert res.status_code == 404
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_editing_template_steps_after_submit_does_not_change_pending_request_flow(
    app, head_admin_setup, login_as
):
    """แก้ steps ของ template หลังส่งคำขอแล้ว flow ของคำขอเดิมต้องไม่เปลี่ยน (active หลังครบ 2 ขั้นเดิม)"""
    s = head_admin_setup
    org = s["org"]
    car_app = _submit_and_get(app, login_as, s)

    template = s["template"]
    template.steps.append(
        models.car_form_templates.ApprovalStepDef(
            key="director", label="ผู้อำนวยการ", approver_type="role", role="director"
        )
    )
    template.save()

    res = _approve(login_as(app.test_client(), s["head"]), car_app, org)
    assert res.status_code == 302
    res = _approve(
        login_as(app.test_client(), s["admin"]),
        car_app,
        org,
        car=str(s["car"].id),
    )
    assert res.status_code == 302

    car_app.reload()
    assert car_app.status == "active"
    assert [a.step_key for a in car_app.step_approvals] == ["head", "admin"]


def _at_vehicle_step(app, login_as, s):
    car_app = _submit_and_get(app, login_as, s)
    res = _approve(login_as(app.test_client(), s["head"]), car_app, s["org"])
    assert res.status_code == 302
    car_app.reload()
    assert car_app.current_step == 1
    return car_app


def test_vehicle_step_rejects_approval_without_car_or_with_car_from_another_org(
    app, head_admin_setup, create_org, create_car, login_as
):
    """ขั้นจัดรถ: อนุมัติโดยไม่เลือกรถ หรือเลือกรถของ org อื่น ต้องถูกปฏิเสธ (400) และสถานะไม่เปลี่ยน"""
    s = head_admin_setup
    other_car = create_car(create_org(name="หน่วยงานอื่น"), license_plate="ขค-9999")
    car_app = _at_vehicle_step(app, login_as, s)
    admin_client = login_as(app.test_client(), s["admin"])

    res = _approve(admin_client, car_app, s["org"])
    assert res.status_code == 400
    res = _approve(admin_client, car_app, s["org"], car=str(other_car.id))
    assert res.status_code == 400

    car_app.reload()
    assert car_app.status == "pending"
    assert car_app.current_step == 1
    assert car_app.car is None
    assert [a.step_key for a in car_app.step_approvals] == ["head"]


def test_vehicle_step_rejects_driver_who_is_not_a_member_of_the_org(
    app, head_admin_setup, create_org, create_user, assign_user_to_org, login_as
):
    """ขั้นจัดรถ: driver ที่ไม่ได้เป็นสมาชิก (driver) ของ org ต้องถูกปฏิเสธ (400) และสถานะไม่เปลี่ยน"""
    s = head_admin_setup
    outsider_driver = create_user("Outdriver", "User")
    assign_user_to_org(outsider_driver, create_org(name="หน่วยงานอื่น"), roles=["driver"])
    car_app = _at_vehicle_step(app, login_as, s)

    res = _approve(
        login_as(app.test_client(), s["admin"]),
        car_app,
        s["org"],
        car=str(s["car"].id),
        driver=str(outsider_driver.id),
    )

    assert res.status_code == 400
    car_app.reload()
    assert car_app.status == "pending"
    assert car_app.current_step == 1
    assert car_app.driver is None
    assert [a.step_key for a in car_app.step_approvals] == ["head"]


def _template_with_fields(org, fields):
    template = models.car_form_templates.CarFormTemplate(
        organization=org,
        name="template ที่มีฟิลด์เพิ่ม",
        fields=[models.car_form_templates.FormFieldDef(**f) for f in fields],
        steps=[
            models.car_form_templates.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
        ],
    )
    template.save()
    return template


def test_submitted_catalog_values_are_stored_under_details_key_and_custom_under_custom_prefix(
    app, head_admin_setup, login_as
):
    """ค่าฟิลด์ catalog เก็บที่ details.<catalog key> และค่า custom เก็บที่ details.custom_<key>"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"],
        [
            {"source": "catalog", "key": "vehicle_kind"},
            {"source": "catalog", "key": "province"},
            {"source": "catalog", "key": "cost_responsibility"},
            {
                "source": "custom",
                "key": "project_no",
                "label": "เลขที่โครงการ",
                "field_type": "text",
            },
        ],
    )

    res = _submit(
        login_as(app.test_client(), s["staff"]),
        template,
        s["org"],
        vehicle_kind="ตู้",
        province="สงขลา",
        cost_responsibility=["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง"],
        custom_project_no="PRJ-2569-01",
    )

    assert res.status_code == 302
    car_app = models.vehicle_applications.CarApplication.objects(
        organization=s["org"]
    ).first()
    assert car_app.details == {
        "vehicle_kind": "ตู้",
        "province": "สงขลา",
        "cost_responsibility": ["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง"],
        "custom_project_no": "PRJ-2569-01",
    }


def test_request_missing_a_required_catalog_field_is_not_created(
    app, head_admin_setup, login_as
):
    """ขาดฟิลด์ catalog ที่บังคับกรอก ต้องได้ 400 และไม่เกิด CarApplication"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "province", "is_required": True}]
    )

    res = _submit(login_as(app.test_client(), s["staff"]), template, s["org"])

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_radio_value_outside_catalog_choices_is_rejected(
    app, head_admin_setup, login_as
):
    """ค่า radio นอก choices ของ catalog ต้องถูกปฏิเสธ (400) และไม่เกิด CarApplication"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "vehicle_kind"}]
    )

    res = _submit(
        login_as(app.test_client(), s["staff"]),
        template,
        s["org"],
        vehicle_kind="เรือ",
    )

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_radio_value_outside_template_restricted_choices_is_rejected(
    app, head_admin_setup, login_as
):
    """template จำกัด choices เป็น ตู้/เก๋ง แล้วส่ง 'บัส' (อยู่ใน catalog แต่ถูกตัดออก) ต้องถูกปฏิเสธ (400)"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"],
        [{"source": "catalog", "key": "vehicle_kind", "choices": ["ตู้", "เก๋ง"]}],
    )

    res = _submit(
        login_as(app.test_client(), s["staff"]),
        template,
        s["org"],
        vehicle_kind="บัส",
    )

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_request_without_departure_date_is_rejected_with_400(
    app, head_admin_setup, login_as
):
    """ไม่ส่งวันที่ออกเดินทาง ต้องได้ 400 (ไม่ใช่ 500) และไม่เกิด CarApplication"""
    s = head_admin_setup

    res = _submit(
        login_as(app.test_client(), s["staff"]),
        s["template"],
        s["org"],
        departure_date="",
    )

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def _inbox(client, org):
    return client.get(f"{BASE}/inbox?organization_id={org.id}")


def test_inbox_shows_pending_request_only_to_users_who_can_act_on_its_current_step(
    app, head_admin_setup, login_as, create_user, assign_user_to_org
):
    """GET /inbox แสดงคำขอที่รออยู่ เฉพาะผู้ที่ทำขั้นปัจจุบันได้ (head ฝ่ายเดียวกัน แล้วเป็น admin หลัง head อนุมัติ)"""
    s = head_admin_setup
    other_division = models.Division(name="ฝ่ายอื่น", organization=s["org"])
    other_division.save()
    other_head = create_user("Otherhead", "User")
    role = assign_user_to_org(other_head, s["org"], roles=["head"])
    role.division = other_division
    role.save()
    car_app = _submit_and_get(app, login_as, s)
    car_app.location = "ตำบลบ่อยาง-อินบ็อกซ์"
    car_app.save()

    head_page = _inbox(login_as(app.test_client(), s["head"]), s["org"])
    other_head_page = _inbox(login_as(app.test_client(), other_head), s["org"])
    staff_page = _inbox(login_as(app.test_client(), s["staff"]), s["org"])
    admin_before = _inbox(login_as(app.test_client(), s["admin"]), s["org"])
    _approve(login_as(app.test_client(), s["head"]), car_app, s["org"])
    admin_after = _inbox(login_as(app.test_client(), s["admin"]), s["org"])

    assert head_page.status_code == 200
    assert "ตำบลบ่อยาง-อินบ็อกซ์" in head_page.get_data(as_text=True)
    assert "ตำบลบ่อยาง-อินบ็อกซ์" not in other_head_page.get_data(as_text=True)
    assert "ตำบลบ่อยาง-อินบ็อกซ์" not in staff_page.get_data(as_text=True)
    assert "ตำบลบ่อยาง-อินบ็อกซ์" not in admin_before.get_data(as_text=True)
    assert "ตำบลบ่อยาง-อินบ็อกซ์" in admin_after.get_data(as_text=True)


def test_paper_returns_the_template_pdf_filled_with_request_values_to_org_members_only(
    app, head_admin_setup, login_as, create_org, create_user, assign_user_to_org
):
    """GET /<id>/paper ส่ง PDF ของ template ที่เขียนค่าคำขอทับตาม placements ให้สมาชิก org เท่านั้น (org อื่นได้ 404)"""
    s = head_admin_setup
    blank = BytesIO()
    pdf = canvas.Canvas(blank, pagesize=(595, 842))
    pdf.drawString(50, 800, "BLANK-FORM")
    pdf.showPage()
    pdf.save()
    paper_file = models.car_form_templates.CarFormPaperFile(
        organization=s["org"],
        filename="form.pdf",
        data=blank.getvalue(),
        page_count=1,
        page_sizes=[[595, 842]],
    )
    paper_file.save()
    s["template"].paper_file = paper_file
    s["template"].placements = [
        models.car_form_templates.PaperPlacement(
            page=0, x=0.1, y=0.2, w=0.6, h=0.03, variable="app.location"
        )
    ]
    s["template"].save()
    car_app = _submit_and_get(app, login_as, s)
    org_b = create_org(name="หน่วยงาน B")
    user_b = create_user("Outsider", "User")
    assign_user_to_org(user_b, org_b, roles=["staff"])

    own = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/{car_app.id}/paper?organization_id={s['org'].id}"
    )
    outsider = login_as(app.test_client(), user_b).get(
        f"{BASE}/{car_app.id}/paper?organization_id={org_b.id}"
    )

    assert own.status_code == 200
    assert own.mimetype == "application/pdf"
    text = PdfReader(BytesIO(own.data)).pages[0].extract_text()
    assert "BLANK-FORM" in text
    assert "จ.สงขลา" in text
    assert outsider.status_code == 404


def test_paper_is_404_when_the_template_has_no_pdf(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)

    res = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/{car_app.id}/paper?organization_id={s['org'].id}"
    )

    assert res.status_code == 404


def test_new_lists_only_active_templates_of_the_current_org(
    app, head_admin_setup, login_as, create_org
):
    """GET /new แสดงเฉพาะ template ที่ active ของ org ปัจจุบัน (ไม่แสดงของ org อื่น หรือที่ปิดใช้งาน)"""
    s = head_admin_setup
    step = lambda: models.car_form_templates.ApprovalStepDef(
        key="admin", label="ผู้จัดรถ", approver_type="role", role="admin", assigns_vehicle=True
    )
    models.car_form_templates.CarFormTemplate(
        organization=create_org(name="หน่วยงานอื่น"), name="แบบฟอร์มของ org อื่น", steps=[step()]
    ).save()
    models.car_form_templates.CarFormTemplate(
        organization=s["org"], name="แบบฟอร์มที่ปิดแล้ว", status="disactive", steps=[step()]
    ).save()

    res = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new?organization_id={s['org'].id}"
    )

    html = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "head แล้ว admin จัดรถ" in html
    assert "แบบฟอร์มของ org อื่น" not in html
    assert "แบบฟอร์มที่ปิดแล้ว" not in html


def test_new_form_renders_core_fields_and_the_templates_details_fields(
    app, head_admin_setup, login_as
):
    """GET /new/<template_id> แสดงฟิลด์หลัก ฟิลด์ catalog (label จาก catalog) และฟิลด์ custom (label ที่ตั้งเอง)"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"],
        [
            {"source": "catalog", "key": "vehicle_kind"},
            {"source": "custom", "key": "project_no", "field_type": "text", "label": "เลขที่โครงการ"},
        ],
    )

    res = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new/{template.id}?organization_id={s['org'].id}"
    )

    html = res.get_data(as_text=True)
    assert res.status_code == 200
    for core in ("phone", "location", "request_reason", "passenger_number", "departure_date", "return_time"):
        assert f'name="{core}"' in html
    assert "ชนิดรถ" in html
    assert 'name="vehicle_kind"' in html
    assert "เลขที่โครงการ" in html
    assert 'name="custom_project_no"' in html


def test_submit_goes_to_the_requests_list_and_approve_deny_go_to_the_inbox(app, head_admin_setup, login_as):
    """ยื่นสำเร็จแล้วพาไปหน้ารวมคำขอใช้รถ ส่วนอนุมัติ/ปฏิเสธพาไปหน้ารายการที่ต้องอนุมัติ"""
    s = head_admin_setup
    inbox_path = f"{BASE}/inbox"

    submitted = _submit(login_as(app.test_client(), s["staff"]), s["template"], s["org"])
    first = models.vehicle_applications.CarApplication.objects(organization=s["org"]).first()
    approved = _approve(login_as(app.test_client(), s["head"]), first, s["org"])
    denied = login_as(app.test_client(), s["admin"]).post(
        f"{BASE}/{first.id}/deny",
        data={"organization_id": str(s["org"].id), "denied_reason": "รถไม่ว่าง"},
    )

    assert submitted.status_code == 302
    assert submitted.headers["Location"].split("?")[0].endswith(f"{BASE}/")
    for res in (approved, denied):
        assert res.status_code == 302
        assert inbox_path in res.headers["Location"]


def test_legacy_car_application_pages_render_a_template_request_without_using_type(
    app, head_admin_setup, login_as
):
    """คำขอจาก template (using_type ว่าง) ต้องไม่ทำให้ modal ปฏิทิน และหน้ารายการเดิมพัง"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    client = login_as(app.test_client(), s["staff"])
    org_q = f"organization_id={s['org'].id}"

    modal = client.get(f"/vehicle_lending/car_applications/{car_app.id}/modal?{org_q}")
    index = client.get(f"/vehicle_lending/car_applications?{org_q}")
    calendar = client.get(f"/vehicle_lending/car_applications/calendar?{org_q}")

    assert modal.status_code == 200
    assert "จ.สงขลา" in modal.get_data(as_text=True)
    assert index.status_code == 200
    assert calendar.status_code == 200


def test_sidebar_links_to_new_request_and_inbox_for_staff_and_templates_for_admin_only(
    app, head_admin_setup, login_as
):
    """sidebar มีลิงก์ยื่นคำขอและรายการที่ต้องอนุมัติสำหรับ staff ส่วนลิงก์จัดการ template เห็นเฉพาะ admin"""
    s = head_admin_setup
    org_q = f"?organization_id={s['org'].id}"

    staff_html = login_as(app.test_client(), s["staff"]).get(f"{BASE}/inbox{org_q}").get_data(as_text=True)
    admin_html = login_as(app.test_client(), s["admin"]).get(f"{BASE}/inbox{org_q}").get_data(as_text=True)

    assert f"{BASE}/new?organization_id={s['org'].id}" in staff_html
    assert f"{BASE}/inbox?organization_id={s['org'].id}" in staff_html
    assert "/vehicle_lending/car_form_templates/" not in staff_html
    assert f"/vehicle_lending/car_form_templates/?organization_id={s['org'].id}" in admin_html


def _vehicle_kind_options(html):
    import re

    select = re.search(r'<select[^>]*name="vehicle_kind".*?</select>', html, re.S).group(0)
    return re.findall(r'<option[^>]*value="([^"]*)"', select)


def test_requesters_vehicle_type_options_are_only_the_types_the_org_has_active_cars_of(
    app, head_admin_setup, login_as, create_org, create_car
):
    """ตัวเลือกประเภทรถของผู้ขอมีเฉพาะประเภทที่องค์กรมีรถ active (รถ disactive/ขององค์กรอื่นไม่นับ)"""
    s = head_admin_setup
    other_org = create_org(name="องค์กรอื่น")
    create_car(s["org"], license_plate="ตู้-1", vehicle_type="ตู้")
    create_car(s["org"], license_plate="บัส-1", vehicle_type="บัส", status="disactive")
    create_car(other_org, license_plate="เก๋ง-1", vehicle_type="เก๋ง")
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "vehicle_kind"}]
    )

    res = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new/{template.id}?organization_id={s['org'].id}"
    )

    assert res.status_code == 200
    assert _vehicle_kind_options(res.get_data(as_text=True)) == ["", "ตู้"]


def test_vehicle_type_the_org_has_no_active_car_of_is_rejected_and_nothing_is_created(
    app, head_admin_setup, login_as, create_car
):
    """ส่งประเภทรถที่องค์กรไม่มีรถ active (แต่อยู่ใน catalog) ต้องได้ 400 และไม่เกิด CarApplication"""
    s = head_admin_setup
    create_car(s["org"], license_plate="ตู้-1", vehicle_type="ตู้")
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "vehicle_kind"}]
    )

    res = _submit(
        login_as(app.test_client(), s["staff"]),
        template,
        s["org"],
        vehicle_kind="บัส",
    )

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_requesters_vehicle_type_options_fall_back_to_the_catalog_when_no_car_has_a_type(
    app, head_admin_setup, login_as
):
    """องค์กรที่ยังไม่ติดประเภทรถ ผู้ขอยังเลือกได้ครบตาม catalog"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "vehicle_kind"}]
    )

    res = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new/{template.id}?organization_id={s['org'].id}"
    )

    assert _vehicle_kind_options(res.get_data(as_text=True)) == [
        "", "บัส", "ตู้", "เก๋ง", "มินิบัส"
    ]


def test_vehicle_step_detail_lists_cars_of_the_requested_type_first_and_offers_a_show_all_types_toggle(
    app, head_admin_setup, login_as, create_car
):
    """ขั้นจัดรถ: option รถมี data-vehicle-type, select บอกประเภทที่ขอ, รถประเภทที่ขอขึ้นก่อน และมี checkbox แสดงรถทุกประเภท"""
    import re

    s = head_admin_setup
    create_car(s["org"], license_plate="บัส-1", vehicle_type="บัส")
    create_car(s["org"], license_plate="ตู้-1", vehicle_type="ตู้")
    car_app = _at_vehicle_step(app, login_as, s)
    car_app.details = {"vehicle_kind": "ตู้"}
    car_app.save()

    res = _detail(login_as(app.test_client(), s["admin"]), car_app, s["org"])

    html = res.get_data(as_text=True)
    select = re.search(r'<select[^>]*name="car".*?</select>', html, re.S).group(0)
    assert 'data-requested-type="ตู้"' in select
    assert re.findall(r'data-vehicle-type="([^"]*)"', select) == ["ตู้", "", "บัส"]
    assert "แสดงรถทุกประเภท" in html


def _requested_vehicle_type_at_vehicle_step(app, login_as, s, requested):
    car_app = _at_vehicle_step(app, login_as, s)
    car_app.details = {"vehicle_kind": requested}
    car_app.save()
    return car_app


def test_assigning_a_car_of_another_type_than_requested_succeeds_and_records_the_assigned_cars_type(
    app, head_admin_setup, login_as, create_car
):
    """จัดรถต่างประเภทจากที่ขอได้ และบันทึกประเภทของรถที่จัดไว้ใน assigned_vehicle_type"""
    s = head_admin_setup
    bus = create_car(s["org"], license_plate="บัส-1", vehicle_type="บัส")
    car_app = _requested_vehicle_type_at_vehicle_step(app, login_as, s, "ตู้")

    res = _approve(
        login_as(app.test_client(), s["admin"]), car_app, s["org"], car=str(bus.id)
    )

    assert res.status_code == 302
    car_app.reload()
    assert car_app.status == "active"
    assert car_app.car == bus
    assert car_app.assigned_vehicle_type == "บัส"


def test_assigning_a_matching_car_records_the_same_type(
    app, head_admin_setup, login_as, create_car
):
    """จัดรถตรงประเภทที่ขอ assigned_vehicle_type ต้องเท่ากับประเภทที่ขอ"""
    s = head_admin_setup
    van = create_car(s["org"], license_plate="ตู้-1", vehicle_type="ตู้")
    car_app = _requested_vehicle_type_at_vehicle_step(app, login_as, s, "ตู้")

    res = _approve(
        login_as(app.test_client(), s["admin"]), car_app, s["org"], car=str(van.id)
    )

    assert res.status_code == 302
    car_app.reload()
    assert car_app.assigned_vehicle_type == "ตู้"


def test_request_list_flags_a_car_of_another_type_than_requested(
    app, head_admin_setup, login_as, create_car
):
    """รายการคำขอแสดงป้าย 'จัดรถต่างประเภทจากที่ขอ' เมื่อประเภทที่จัดต่างจากที่ขอ และไม่แสดงเมื่อตรงกัน"""
    s = head_admin_setup
    bus = create_car(s["org"], license_plate="บัส-1", vehicle_type="บัส")
    car_app = _requested_vehicle_type_at_vehicle_step(app, login_as, s, "ตู้")
    client = login_as(app.test_client(), s["staff"])
    url = f"/vehicle_lending/car_applications?organization_id={s['org'].id}"

    _approve(login_as(app.test_client(), s["admin"]), car_app, s["org"], car=str(bus.id))
    mismatch_page = client.get(url).get_data(as_text=True)
    car_app.reload()
    car_app.details = {"vehicle_kind": "บัส"}
    car_app.save()
    matching_page = client.get(url).get_data(as_text=True)

    assert "จัดรถต่างประเภทจากที่ขอ" in mismatch_page
    assert "จัดรถต่างประเภทจากที่ขอ" not in matching_page


def test_new_form_marks_required_fields_with_a_red_asterisk(app, head_admin_setup, login_as):
    """ช่องที่บังคับกรอกมี * สีแดงต่อท้ายชื่อ ช่องที่ไม่บังคับไม่มี"""
    import re

    s = head_admin_setup
    template = _template_with_fields(
        s["org"],
        [
            {"source": "custom", "key": "project_no", "field_type": "text", "label": "เลขที่โครงการ", "is_required": True},
            {"source": "custom", "key": "note", "field_type": "text", "label": "หมายเหตุเพิ่มเติม"},
        ],
    )

    html = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new/{template.id}?organization_id={s['org'].id}"
    ).get_data(as_text=True)

    marked = {
        label.strip()
        for label in re.findall(r'<legend class="fieldset-legend">\s*([^<]+?)\s*<span class="text-error"[^>]*>\*</span>', html)
    }
    assert {"เบอร์โทรศัพท์", "สถานที่ที่ต้องการจะไป", "วันที่ออกเดินทาง", "เลขที่โครงการ"} <= marked
    assert "หมายเหตุเพิ่มเติม" not in marked


def _requests_list(client, org):
    return client.get(f"{BASE}/?organization_id={org.id}")


@pytest.fixture
def two_requests(app, head_admin_setup, login_as, create_user, assign_user_to_org):
    """คำขอ 2 ใบ: ของ staff (ฝ่ายอาคาร) และของ staff อีกคนในฝ่ายอื่น"""
    s = head_admin_setup
    other_division = models.Division(name="ฝ่ายอื่น", organization=s["org"])
    other_division.save()
    other_staff = create_user("Otherstaff", "User")
    role = assign_user_to_org(other_staff, s["org"], roles=["staff"])
    role.division = other_division
    role.save()

    mine = _submit_and_get(app, login_as, s)
    mine.location = "สถานที่ของสตาฟ-ก"
    mine.save()
    _submit(login_as(app.test_client(), other_staff), s["template"], s["org"])
    theirs = models.vehicle_applications.CarApplication.objects(creator=other_staff).first()
    theirs.location = "สถานที่ของสตาฟ-ข"
    theirs.save()
    return {**s, "other_staff": other_staff}


def test_requests_list_shows_staff_only_their_own_requests(app, two_requests, login_as):
    """พนักงาน (staff) เห็นเฉพาะคำขอที่ตัวเองยื่น"""
    s = two_requests
    res = _requests_list(login_as(app.test_client(), s["staff"]), s["org"])

    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "สถานที่ของสตาฟ-ก" in html
    assert "สถานที่ของสตาฟ-ข" not in html


@pytest.mark.parametrize("role", ["admin", "director", "endorser", "supervisor supplier"])
def test_requests_list_shows_every_request_in_the_org_to_admin_and_executive_roles(
    app, two_requests, login_as, create_user, assign_user_to_org, create_org, role
):
    """admin / ผอ. / ผู้อนุมัติ / หัวหน้าพัสดุ เห็นคำขอทุกใบใน org (แต่ไม่เห็นของ org อื่น)"""
    s = two_requests
    viewer = create_user("Viewer", role.replace(" ", ""))
    assign_user_to_org(viewer, s["org"], roles=[role])

    html = _requests_list(login_as(app.test_client(), viewer), s["org"]).get_data(as_text=True)

    assert "สถานที่ของสตาฟ-ก" in html
    assert "สถานที่ของสตาฟ-ข" in html


def test_requests_list_shows_head_the_requests_of_their_own_division(app, two_requests, login_as):
    """หัวหน้าฝ่ายเห็นคำขอของคนในฝ่ายตัวเอง ไม่เห็นของฝ่ายอื่น"""
    s = two_requests
    html = _requests_list(login_as(app.test_client(), s["head"]), s["org"]).get_data(as_text=True)

    assert "สถานที่ของสตาฟ-ก" in html
    assert "สถานที่ของสตาฟ-ข" not in html


def test_requests_list_does_not_show_requests_from_another_org(
    app, two_requests, login_as, create_org, assign_user_to_org
):
    """admin ของอีก org ดูรายการของ org ตัวเองแล้วไม่เห็นคำขอของ org นี้"""
    s = two_requests
    other_org = create_org(name="องค์กรอื่น")
    assign_user_to_org(s["admin"], other_org, roles=["admin"])

    html = _requests_list(login_as(app.test_client(), s["admin"]), other_org).get_data(as_text=True)

    assert "สถานที่ของสตาฟ-ก" not in html
    assert "สถานที่ของสตาฟ-ข" not in html


def test_sidebar_names_the_inbox_list_to_approve_and_links_the_requests_list(
    app, head_admin_setup, login_as
):
    """เมนูชื่อ "รายการที่ต้องอนุมัติ" (ไม่ใช่ "รอฉันอนุมัติ") และมีเมนู "คำขอใช้รถ" ไปหน้ารวมคำขอ"""
    s = head_admin_setup
    html = _requests_list(login_as(app.test_client(), s["staff"]), s["org"]).get_data(as_text=True)

    assert "รายการที่ต้องอนุมัติ" in html
    assert "รอฉันอนุมัติ" not in html
    assert f'href="{BASE}/?organization_id={s["org"].id}"' in html


# ---- audit log / หน้ารายละเอียด / modal ----


def _detail(client, car_app, org):
    return client.get(f"{BASE}/{car_app.id}?organization_id={org.id}")


def test_audit_log_records_who_did_what_and_when_through_submit_approve_and_deny(
    app, head_admin_setup, login_as
):
    """ยื่น อนุมัติ (พร้อมจัดรถ/คนขับ) และปฏิเสธ ต้องเก็บ audit log: ใคร ทำอะไร ขั้นไหน เมื่อไร และค่าที่เปลี่ยน"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    _approve(login_as(app.test_client(), s["head"]), car_app, s["org"], comment="ไปได้")
    _approve(
        login_as(app.test_client(), s["admin"]), car_app, s["org"],
        car=str(s["car"].id), comment="จัดรถให้แล้ว",
    )
    car_app.reload()

    logs = car_app.audit_logs
    assert [log.action for log in logs] == ["submitted", "approved", "approved"]
    assert [log.actor for log in logs] == [s["staff"], s["head"], s["admin"]]
    assert all(log.created_date is not None for log in logs)
    assert logs[1].step_label == "ผู้บังคับบัญชา"
    assert logs[1].comment == "ไปได้"
    assert logs[2].step_label == "ผู้จัดรถบริการ"
    assert {"field": "car", "label": "รถ", "old": "", "new": "กข-1234"} in logs[2].changes
    assert logs[2].changes[-1]["field"] == "status"
    assert logs[2].changes[-1]["new"] == "active"


def test_audit_log_records_denial_with_reason(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    login_as(app.test_client(), s["head"]).post(
        f"{BASE}/{car_app.id}/deny",
        data={"organization_id": str(s["org"].id), "denied_reason": "ไม่มีงบ"},
    )
    car_app.reload()

    last = car_app.audit_logs[-1]
    assert last.action == "denied"
    assert last.actor == s["head"]
    assert last.comment == "ไม่มีงบ"
    assert {"field": "status", "label": "สถานะ", "old": "pending", "new": "denied"} in last.changes


def test_detail_page_shows_stepper_with_who_approved_and_the_current_step_and_the_audit_log(
    app, head_admin_setup, login_as
):
    """หน้ารายละเอียดแสดง stepper: ขั้นที่ผ่านแล้วพร้อมชื่อผู้อนุมัติ ขั้นที่รออยู่ และ audit log"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    _approve(login_as(app.test_client(), s["head"]), car_app, s["org"], comment="ความเห็นหัวหน้า-xyz")

    res = _detail(login_as(app.test_client(), s["staff"]), car_app, s["org"])

    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'data-step-state="done"' in html
    assert 'data-step-state="current"' in html
    assert s["head"].get_resources_fullname_th() in html
    assert "ความเห็นหัวหน้า-xyz" in html
    assert "data-audit-log" in html
    assert html.count("data-audit-entry") == 2


def test_detail_page_is_hidden_from_staff_who_did_not_submit_it_and_from_other_orgs(
    app, head_admin_setup, login_as, create_user, assign_user_to_org, create_org
):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    stranger = create_user("Stranger", "User")
    assign_user_to_org(stranger, s["org"], roles=["staff"])
    other_org = create_org(name="องค์กรอื่น")
    assign_user_to_org(s["admin"], other_org, roles=["admin"])

    assert _detail(login_as(app.test_client(), stranger), car_app, s["org"]).status_code == 404
    assert _detail(login_as(app.test_client(), s["admin"]), car_app, other_org).status_code == 404
    assert _detail(login_as(app.test_client(), s["admin"]), car_app, s["org"]).status_code == 200


def test_inbox_is_a_table_with_a_view_button_and_approval_happens_on_the_detail_page(
    app, head_admin_setup, login_as
):
    """หน้ารายการที่ต้องอนุมัติเป็นตาราง แต่ละแถวมีปุ่มดู (ไปหน้ารายละเอียด) ไม่มีฟอร์มอนุมัติในหน้า
    ส่วนหน้ารายละเอียดของผู้อนุมัติขั้นปัจจุบันมี modal อนุมัติ/ปฏิเสธ"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    head = login_as(app.test_client(), s["head"])

    inbox = _inbox(head, s["org"]).get_data(as_text=True)
    detail = _detail(head, car_app, s["org"]).get_data(as_text=True)

    assert "<table" in inbox
    assert f'data-request-id="{car_app.id}"' in inbox
    assert f'href="{BASE}/{car_app.id}?organization_id={s["org"].id}"' in inbox
    assert "<dialog" not in inbox
    assert f'<dialog id="approve-{car_app.id}"' in detail
    assert f'<dialog id="deny-{car_app.id}"' in detail
    assert f"getElementById('approve-{car_app.id}').showModal()" in detail
    assert 'data-step-state="current"' in detail


def test_detail_page_has_no_approval_modals_for_someone_who_cannot_act(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)

    detail = _detail(login_as(app.test_client(), s["staff"]), car_app, s["org"]).get_data(as_text=True)

    assert "<dialog" not in detail


def test_approving_from_the_detail_page_returns_to_the_detail_page(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)

    res = _approve(login_as(app.test_client(), s["head"]), car_app, s["org"], next="detail")

    assert res.status_code == 302
    assert res.headers["Location"].split("?")[0].endswith(f"{BASE}/{car_app.id}")


def test_requests_list_links_each_request_to_its_detail_page(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)

    html = _requests_list(login_as(app.test_client(), s["staff"]), s["org"]).get_data(as_text=True)

    assert f'href="{BASE}/{car_app.id}?organization_id={s["org"].id}"' in html


def test_audit_log_shows_status_changes_with_thai_labels(app, head_admin_setup, login_as):
    """ใน audit log ค่าสถานะที่เปลี่ยนแสดงเป็นป้ายภาษาไทย (รออนุมัติ → ปฏิเสธ) ไม่ใช่ค่า pending/denied"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    login_as(app.test_client(), s["head"]).post(
        f"{BASE}/{car_app.id}/deny",
        data={"organization_id": str(s["org"].id), "denied_reason": "ไม่มีงบ"},
    )

    html = _detail(login_as(app.test_client(), s["staff"]), car_app, s["org"]).get_data(as_text=True)
    log = html[html.index("data-audit-log"):]

    assert "รออนุมัติ" in log
    assert "ปฏิเสธ" in log
    assert ">pending<" not in log
    assert ">denied<" not in log


def test_status_badge_carries_the_status_key_and_thai_label(app, head_admin_setup, login_as):
    s = head_admin_setup
    _submit_and_get(app, login_as, s)

    html = _requests_list(login_as(app.test_client(), s["staff"]), s["org"]).get_data(as_text=True)

    assert 'data-status="pending"' in html
    assert "รออนุมัติ" in html


def test_task_list_shows_an_active_template_request_with_its_form_name_and_a_status_badge(
    app, head_admin_setup, login_as
):
    """รายการงาน (car_tasks) แสดงคำขอจาก template ที่อนุมัติครบแล้ว พร้อมชื่อแบบฟอร์มแทนประเภทการใช้แบบเดิม"""
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    _approve(login_as(app.test_client(), s["head"]), car_app, s["org"])
    _approve(login_as(app.test_client(), s["admin"]), car_app, s["org"], car=str(s["car"].id))

    res = login_as(app.test_client(), s["admin"]).get(
        f"/vehicle_lending/car_tasks?organization_id={s['org'].id}"
    )

    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert s["template"].name in html
    assert 'data-status="active"' in html
    assert f'href="{BASE}/{car_app.id}?organization_id={s["org"].id}"' in html


# ---- ค้นหา ----


def test_requests_list_search_by_text_status_and_template(app, two_requests, login_as):
    """หน้าคำขอใช้รถ: ค้นด้วยข้อความ (สถานที่/เหตุผล/ชื่อผู้ขอ), สถานะ และแบบฟอร์ม"""
    s = two_requests
    admin = login_as(app.test_client(), s["admin"])
    base = f"{BASE}/?organization_id={s['org'].id}"

    by_text = admin.get(f"{base}&q=สตาฟ-ข").get_data(as_text=True)
    by_requester = admin.get(f"{base}&q=Otherstaff").get_data(as_text=True)
    by_status = admin.get(f"{base}&status=denied").get_data(as_text=True)
    by_template = admin.get(f"{base}&template_id={s['template'].id}").get_data(as_text=True)

    assert "สถานที่ของสตาฟ-ข" in by_text and "สถานที่ของสตาฟ-ก" not in by_text
    assert "สถานที่ของสตาฟ-ข" in by_requester and "สถานที่ของสตาฟ-ก" not in by_requester
    assert "สถานที่ของสตาฟ-" not in by_status
    assert "สถานที่ของสตาฟ-ก" in by_template and "สถานที่ของสตาฟ-ข" in by_template
    assert 'name="q"' in by_text and 'value="สตาฟ-ข"' in by_text


def test_inbox_search_by_text(app, two_requests, login_as):
    s = two_requests
    admin_view = login_as(app.test_client(), s["head"])
    base = f"{BASE}/inbox?organization_id={s['org'].id}"

    html = admin_view.get(f"{base}&q=ไม่มีคำนี้").get_data(as_text=True)
    all_html = admin_view.get(base).get_data(as_text=True)

    assert 'name="q"' in html
    assert "สถานที่ของสตาฟ-ก" in all_html
    assert "สถานที่ของสตาฟ-ก" not in html


def test_task_list_search_by_text(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)
    car_app.location = "ปลายทาง-งาน-xyz"
    car_app.save()
    _approve(login_as(app.test_client(), s["head"]), car_app, s["org"])
    _approve(login_as(app.test_client(), s["admin"]), car_app, s["org"], car=str(s["car"].id))
    admin = login_as(app.test_client(), s["admin"])
    base = f"/vehicle_lending/car_tasks?organization_id={s['org'].id}"

    hit = admin.get(f"{base}&q=งาน-xyz").get_data(as_text=True)
    miss = admin.get(f"{base}&q=ไม่มีคำนี้").get_data(as_text=True)

    assert 'name="q"' in hit
    assert "ปลายทาง-งาน-xyz" in hit
    assert "ปลายทาง-งาน-xyz" not in miss


# ---- WTForms + html-renderer ----


@pytest.fixture
def csrf_on(app):
    app.config["WTF_CSRF_ENABLED"] = True
    yield
    app.config["WTF_CSRF_ENABLED"] = False


def _csrf_from(html):
    import re

    return re.search(r'name="csrf_token" type="hidden" value="([^"]+)"|name="csrf_token" value="([^"]+)"', html)


def _token(html):
    m = _csrf_from(html)
    return m.group(1) or m.group(2)


def test_approve_and_deny_without_csrf_token_are_rejected(app, head_admin_setup, login_as, csrf_on):
    """เปิด CSRF แล้ว POST อนุมัติ/ปฏิเสธโดยไม่มี token ต้องไม่ผ่าน และสถานะไม่เปลี่ยน"""
    s = head_admin_setup
    app.config["WTF_CSRF_ENABLED"] = False
    car_app = _submit_and_get(app, login_as, s)
    app.config["WTF_CSRF_ENABLED"] = True
    head = login_as(app.test_client(), s["head"])

    approve = _approve(head, car_app, s["org"])
    deny = head.post(f"{BASE}/{car_app.id}/deny", data={"organization_id": str(s["org"].id), "denied_reason": "x"})

    assert approve.status_code == 400
    assert deny.status_code == 400
    car_app.reload()
    assert car_app.status == "pending" and car_app.current_step == 0


def test_approve_with_csrf_token_from_the_detail_page_succeeds(app, head_admin_setup, login_as, csrf_on):
    s = head_admin_setup
    app.config["WTF_CSRF_ENABLED"] = False
    car_app = _submit_and_get(app, login_as, s)
    app.config["WTF_CSRF_ENABLED"] = True
    head = login_as(app.test_client(), s["head"])
    token = _token(_detail(head, car_app, s["org"]).get_data(as_text=True))

    res = _approve(head, car_app, s["org"], csrf_token=token)

    assert res.status_code == 302
    car_app.reload()
    assert car_app.current_step == 1


def test_submit_without_csrf_token_is_rejected(app, head_admin_setup, login_as, csrf_on):
    s = head_admin_setup
    res = _submit(login_as(app.test_client(), s["staff"]), s["template"], s["org"])

    assert res.status_code == 400
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_approve_without_car_on_the_vehicle_step_shows_the_error_in_the_reopened_modal(
    app, head_admin_setup, login_as
):
    """ขั้นจัดรถไม่เลือกรถ: ได้ 400 พร้อมหน้ารายละเอียดที่เปิด modal อนุมัติค้างไว้และบอก error ที่ช่องรถ"""
    s = head_admin_setup
    car_app = _at_vehicle_step(app, login_as, s)

    res = _approve(login_as(app.test_client(), s["admin"]), car_app, s["org"], next="detail")

    assert res.status_code == 400
    html = res.get_data(as_text=True)
    assert "กรุณาเลือกรถ" in html
    assert f'data-open-modal="approve-{car_app.id}"' in html


def test_deny_without_reason_shows_the_error_and_keeps_the_request_pending(app, head_admin_setup, login_as):
    s = head_admin_setup
    car_app = _submit_and_get(app, login_as, s)

    res = login_as(app.test_client(), s["head"]).post(
        f"{BASE}/{car_app.id}/deny", data={"organization_id": str(s["org"].id), "denied_reason": "  "}
    )

    assert res.status_code == 400
    html = res.get_data(as_text=True)
    assert "กรุณาระบุเหตุผลที่ปฏิเสธ" in html
    assert f'data-open-modal="deny-{car_app.id}"' in html
    car_app.reload()
    assert car_app.status == "pending"


def test_submit_rejects_a_return_before_departure_with_a_thai_message_at_the_field(
    app, head_admin_setup, login_as
):
    s = head_admin_setup
    res = _submit(
        login_as(app.test_client(), s["staff"]), s["template"], s["org"],
        return_date="2026-03-09",
    )

    assert res.status_code == 400
    html = res.get_data(as_text=True)
    assert "วันเวลากลับต้องอยู่หลังวันเวลาออกเดินทาง" in html
    assert models.vehicle_applications.CarApplication.objects.count() == 0


def test_submit_without_phone_shows_a_thai_required_message(app, head_admin_setup, login_as):
    s = head_admin_setup
    res = _submit(login_as(app.test_client(), s["staff"]), s["template"], s["org"], phone="")

    assert res.status_code == 400
    assert "กรุณากรอกเบอร์โทรศัพท์" in res.get_data(as_text=True)


def test_request_form_renders_fields_with_the_html_renderer_components(app, head_admin_setup, login_as):
    """ฟิลด์หลักและฟิลด์ของ template ใช้ macro ของ html-renderer (fieldset id="field-<name>")
    ช่องติ๊กหลายข้อใช้ render_checkbox_list_field"""
    s = head_admin_setup
    template = _template_with_fields(
        s["org"], [{"source": "catalog", "key": "cost_responsibility"}, {"source": "catalog", "key": "province"}]
    )

    html = login_as(app.test_client(), s["staff"]).get(
        f"{BASE}/new/{template.id}?organization_id={s['org'].id}"
    ).get_data(as_text=True)

    for name in ("phone", "location", "request_reason", "passenger_number", "departure_date", "return_time", "province", "cost_responsibility"):
        assert f'id="field-{name}"' in html, name
    assert "checkbox checkbox-primary" in html


def test_search_bar_is_a_wtform_rendered_with_the_html_renderer(app, head_admin_setup, login_as):
    s = head_admin_setup
    html = login_as(app.test_client(), s["admin"]).get(
        f"{BASE}/?organization_id={s['org'].id}&q=abc"
    ).get_data(as_text=True)

    assert 'id="field-q"' in html
    assert 'id="field-template_id"' in html
    assert 'id="field-status"' in html
    assert 'value="abc"' in html


def test_task_filter_is_a_wtform_rendered_with_the_renderer_and_ignores_unknown_sort_fields(
    app, head_admin_setup, login_as
):
    s = head_admin_setup
    admin = login_as(app.test_client(), s["admin"])
    base = f"/vehicle_lending/car_tasks?organization_id={s['org'].id}"

    html = admin.get(f"{base}&q=abc").get_data(as_text=True)
    odd_sort = admin.get(f"{base}&sort_by=creator.password&order=sideways")

    for name in ("q", "date", "sort_by", "order"):
        assert f'id="field-{name}"' in html, name
    assert 'value="abc"' in html
    assert odd_sort.status_code == 200


def test_return_before_departure_is_reported_even_when_other_fields_are_missing(app, head_admin_setup, login_as):
    s = head_admin_setup
    res = _submit(
        login_as(app.test_client(), s["staff"]), s["template"], s["org"],
        phone="", return_date="2026-03-09",
    )

    html = res.get_data(as_text=True)
    assert "กรุณากรอกเบอร์โทรศัพท์" in html
    assert "วันเวลากลับต้องอยู่หลังวันเวลาออกเดินทาง" in html


def test_request_reason_is_limited_to_what_fits_one_line_on_the_paper_form(app, head_admin_setup, login_as):
    """เหตุผลยาวเกิน 60 ตัวถูกปฏิเสธ (ช่องเหตุผลบนใบพิมพ์เป็นบรรทัดเดียว) 60 ตัวพอดียื่นได้ และช่องกรอกมี maxlength"""
    s = head_admin_setup
    client = login_as(app.test_client(), s["staff"])
    CarApplication = models.vehicle_applications.CarApplication

    too_long = _submit(client, s["template"], s["org"], request_reason="ก" * 61)
    assert too_long.status_code == 400
    assert "เหตุผลยาวเกิน 60 ตัวอักษร" in too_long.get_data(as_text=True)
    assert CarApplication.objects(organization=s["org"]).count() == 0

    exact = _submit(client, s["template"], s["org"], request_reason="ก" * 60)
    assert exact.status_code == 302
    assert CarApplication.objects(organization=s["org"]).first().request_reason == "ก" * 60

    form = client.get(f"{BASE}/new/{s['template'].id}?organization_id={s['org'].id}")
    assert 'maxlength="60"' in form.get_data(as_text=True)
