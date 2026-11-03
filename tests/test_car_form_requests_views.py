import datetime
from unittest.mock import MagicMock, patch

import pytest

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
            {"source": "custom", "key": "project_no", "field_type": "text"},
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
