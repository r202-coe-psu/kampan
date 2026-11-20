"""ตำแหน่งผู้อนุมัติของระบบจองรถเป็น organization role และองค์กรเลือกเปิดใช้ได้ (Organization.enabled_roles)"""

import pathlib

from kampan import models
from kampan.models.organizations import ORGANIZATION_ROLES

ORIGINAL_ROLE_KEYS = [
    "staff",
    "endorser",
    "head",
    "supervisor supplier",
    "admin",
    "driver",
    "director",
    "manager",
]

APPROVAL_ROLES = [
    ("dispatcher", "ผู้จัดรถ"),
    ("vehicle_unit_head", "หัวหน้าหน่วยยานพาหนะ"),
    ("strategy_head", "หัวหน้างานยุทธศาสตร์และบริการกลาง"),
    ("physical_director", "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม"),
    ("vice_president_hatyai", "รองอธิการบดีวิทยาเขตหาดใหญ่"),
    ("president", "อธิการบดี"),
]

SETUP_CSS = (
    pathlib.Path(__file__).resolve().parent.parent
    / "kampan"
    / "web"
    / "static"
    / "css"
    / "setup.css"
)


def test_six_approval_positions_are_organization_roles():
    for item in APPROVAL_ROLES:
        assert item in ORGANIZATION_ROLES


def test_organization_that_never_set_roles_offers_only_the_original_eight(app, create_org):
    org = create_org("Plain Org")

    assert org.enabled_roles is None
    assert [key for key, _ in org.available_roles()] == ORIGINAL_ROLE_KEYS


def test_organization_with_enabled_roles_offers_exactly_those_with_labels(app, create_org):
    org = create_org("Reservation Org")
    org.enabled_roles = ["admin", "dispatcher"]
    org.save()
    org.reload()

    assert org.available_roles() == [
        ("admin", "ผู้ดูแล/เจ้าหน้าที่พัสดุ"),
        ("dispatcher", "ผู้จัดรถ"),
    ]


def test_every_approval_role_has_a_badge_color():
    css = SETUP_CSS.read_text()

    for key, _ in APPROVAL_ROLES:
        assert f".role-{key} " in css
