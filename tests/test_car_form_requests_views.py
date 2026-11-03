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
