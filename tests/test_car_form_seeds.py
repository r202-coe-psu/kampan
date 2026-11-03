import datetime

import pytest

from kampan import models
from kampan.web.views.vehicle_lending.car_form_requests import _snapshot
from kampan.utils import car_form_paper
from kampan.utils import car_form_seeds


def test_seeding_physical_domestic_creates_valid_template_with_ordered_steps_fields_and_bound_approver(
    app, create_org, create_user
):
    """seed physical_domestic: 4 ขั้นเรียง head/admin/approver/director, 5 catalog fields + custom project_no, ขั้น approver ผูกกับ user ที่ส่งมา"""
    org = create_org(name="กองกายภาพ")
    approver = create_user("Wichai", "Approver")

    template = car_form_seeds.seed_template(
        org, "physical_domestic", approver_user=approver
    )

    template.validate()
    assert [s.key for s in template.steps] == ["head", "admin", "approver", "director"]
    assert [(f.source, f.key) for f in template.fields] == [
        ("catalog", "vehicle_kind"),
        ("catalog", "vehicle_count"),
        ("catalog", "district"),
        ("catalog", "province"),
        ("catalog", "cost_responsibility"),
        ("custom", "project_no"),
    ]
    approver_step = template.steps[2]
    assert approver_step.approver_type == "user"
    assert approver_step.user.id == approver.id


def test_seeding_twice_does_not_create_duplicate_template(app, create_org):
    """seed template เดิมซ้ำใน org เดียวกัน ต้องคืน template เดิมและไม่เพิ่มจำนวน"""
    org = create_org(name="กองกายภาพ")

    first = car_form_seeds.seed_template(org, "physical_domestic")
    second = car_form_seeds.seed_template(org, "physical_domestic")

    assert second.id == first.id
    assert models.car_form_templates.CarFormTemplate.objects(organization=org).count() == 1


PAPER_TITLES = {
    "diis_general": "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ",
    "physical_domestic": "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ",
}


@pytest.mark.parametrize("key", list(PAPER_TITLES))
def test_seeded_paper_renders_sample_request_with_form_title(
    app, create_org, create_user, assign_user_to_org, create_car, key
):
    """paper ของ template ที่ seed ต้อง render คำขอตัวอย่างได้โดยไม่ error และมีชื่อแบบฟอร์ม"""
    org = create_org(name="กองกายภาพ")
    requester = create_user("Somchai", "Jaidee")
    assign_user_to_org(requester, org, roles=["staff"])
    template = car_form_seeds.seed_template(org, key)

    application = models.vehicle_applications.CarApplication(
        organization=org,
        creator=requester,
        car=create_car(org, license_plate="กข-1234"),
        location="สงขลา",
        request_reason="ไปราชการ",
        departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
        return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
        details={"vehicle_kind": "ตู้", "province": "สงขลา"},
        template_snapshot=_snapshot(template),
    )
    application.save()

    html = car_form_paper.render_paper(application)

    assert PAPER_TITLES[key] in html


def test_seeding_diis_general_creates_template_with_head_and_admin_steps_and_no_fields(
    app, create_org
):
    """seed diis_general: ไม่มี detail field, 2 ขั้น head (same_division) -> admin (จัดรถ)"""
    template = car_form_seeds.seed_template(create_org(name="DIIS"), "diis_general")

    template.validate()
    assert template.name == "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)"
    assert len(template.fields) == 0
    assert [(s.key, s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", "head", True, False),
        ("admin", "admin", False, True),
    ]
