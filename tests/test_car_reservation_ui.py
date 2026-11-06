"""โครงหน้าของระบบจองรถ: sidebar แบ่งกลุ่ม, หัวรายการ, ฟอร์มแบ่งส่วน, stepper และ timeline ของหน้ารายละเอียด"""

import datetime

import pytest
from lxml import html as lxml_html

from kampan import models

BASE = "/car_reservation"


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("UI Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.staff = create_user("Staff", "Ui")
    assign_user_to_org(s.staff, org, roles=["staff"])
    s.admin = create_user("Admin", "Ui")
    assign_user_to_org(s.admin, org, roles=["admin"])
    s.dispatcher = create_user("Dispatcher", "Ui")
    assign_user_to_org(s.dispatcher, org, roles=["dispatcher"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for

    def page(user, path, **query):
        query = "&".join([f"organization_id={org.id}"] + [f"{k}={v}" for k, v in query.items()])
        response = client_for(user).get(f"{BASE}{path}?{query}")
        assert response.status_code == 200, response.get_data(as_text=True)
        return lxml_html.fromstring(response.get_data(as_text=True))

    s.page = page

    def reservation(creator=None, **overrides):
        fields = dict(
            organization=org,
            creator=creator or s.staff,
            request_type="domestic",
            province_scope="in_province",
            location="กรุงเทพฯ",
            request_reason="ประชุมวิชาการ",
            departure_datetime=datetime.datetime(2031, 1, 10, 8, 30),
            return_datetime=datetime.datetime(2031, 1, 10, 17, 0),
            status="pending",
            route_snapshot=["supervisor", "dispatcher", "vehicle_unit_head"],
            current_step=1,
        )
        fields.update(overrides)
        return models.CarReservation(**fields).save()

    s.reservation = reservation
    return s


def words(element):
    return " ".join(element.text_content().split())


def has_class(name):
    """predicate ของ xpath: element มี class นี้ (ตรงทั้งคำ)"""
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def find(doc, tag, *classes, within="", **attrs):
    """element ใน doc ที่ tag/class/attribute ตรงทั้งหมด (xpath ล้วน เพราะไม่มี cssselect)"""
    predicates = [has_class(c) for c in classes] + [f"@{k.replace('_', '-')}='{v}'" for k, v in attrs.items()]
    expression = f"{within}//{tag}" + "".join(f"[{p}]" for p in predicates)
    return doc.xpath(expression)


def sidebar_titles(doc):
    return [words(li) for li in find(doc, "li", "menu-title", within="//*[@class and " + has_class("drawer-side") + "]")]


def test_sidebar_groups_the_menu_under_titles_and_hides_approvals_from_non_approvers(world):
    assert sidebar_titles(world.page(world.dispatcher, "/requests/")) == [
        "การจอง",
        "การอนุมัติ",
        "รถ",
        "ตั้งค่า",
    ]
    assert sidebar_titles(world.page(world.staff, "/requests/")) == [
        "การจอง",
        "รถ",
        "ตั้งค่า",
    ]
