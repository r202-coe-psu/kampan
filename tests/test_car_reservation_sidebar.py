"""เมนู sidebar ของระบบจองรถอิงกับ role: ลิงก์ที่แสดงต้องกดแล้วเปิดหน้านั้นได้จริง ลิงก์ที่ผู้ใช้ใช้ไม่ได้ต้องไม่แสดง"""

from html.parser import HTMLParser
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

import pytest

from kampan import models
from kampan.web import redis_rq

HOME = "/car_reservation/requests/"

MY_REQUESTS = "คำขอของฉัน"
NEW_REQUEST = "ยื่นคำขอ"
INSERT = "เพิ่มงานแทรก"
CALENDAR = "ปฏิทินการจองรถ"
INBOX = "รายการรออนุมัติ"
TASKS = "รายการงาน"
DIRECTORY = "ข้อมูลรถและพนักงานขับรถ"
STATS = "ภาระงานพนักงานขับรถ"
MANAGE_CARS = "จัดการรถ"
FEEDBACK = "แบบประเมินความพึงพอใจ"
SETTINGS = "ตั้งค่า"
SWITCH_SYSTEM = "เปลี่ยนระบบ"
# ทุก role มีแจ้งเตือนของตัวเอง จึงเห็นเมนูนี้เสมอ
NOTIFICATIONS = "การแจ้งเตือน"

EVERYONE = {MY_REQUESTS, NEW_REQUEST, CALENDAR, DIRECTORY}
# ขอใช้รถเร่งด่วนย้ายไปอยู่ใน modal เลือกประเภทคำขอแล้ว (test_car_reservation_new_request_picker.py)
DISPATCH = EVERYONE | {INSERT, INBOX, STATS}
EXECUTIVE = EVERYONE | {INBOX, STATS}
ADMIN = EVERYONE | {STATS, MANAGE_CARS, FEEDBACK, SETTINGS}

# (org roles, global roles, ลิงก์ที่ต้องเห็นพอดี) ตัวเลขเป็นค่าจากสิทธิ์ของแต่ละ route ไม่ได้คำนวณจากโค้ด sidebar
ROLE_CASES = {
    "requester": (["staff"], [], EVERYONE),
    "division_head": (["head"], [], EVERYONE | {INBOX}),
    "dispatcher": (["dispatcher"], [], DISPATCH),
    "vehicle_unit_head": (["vehicle_unit_head"], [], EXECUTIVE),
    "strategy_head": (["strategy_head"], [], EXECUTIVE),
    "physical_director": (["physical_director"], [], EXECUTIVE),
    "vice_president_hatyai": (["vice_president_hatyai"], [], EVERYONE | {INBOX}),
    "president": (["president"], [], EVERYONE | {INBOX}),
    "driver": (["driver"], [], {CALENDAR, DIRECTORY, TASKS}),
    "driver_and_dispatcher": (["driver", "dispatcher"], [], DISPATCH | {TASKS}),
    "driver_and_head": (["driver", "head"], [], EVERYONE | {INBOX, TASKS}),
    "org_admin": (["admin"], [], ADMIN),
    "system_admin": (["staff"], ["admin"], ADMIN),
}


class SidebarLinks(HTMLParser):
    """ลิงก์ <a href> ในกรอบ data-role="sidebar": [(ข้อความ, href)]"""

    def __init__(self):
        super().__init__()
        self.depth = 0  # ความลึกของ <ul> ที่เป็น sidebar (0 = อยู่นอก sidebar)
        self.links = []
        self.anchor = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "ul" and (self.depth or attrs.get("data-role") == "sidebar"):
            self.depth += 1
        elif tag == "a" and self.depth and attrs.get("href"):
            self.anchor = {"href": attrs["href"], "text": []}

    def handle_data(self, data):
        if self.anchor is not None and data.strip():
            self.anchor["text"].append(" ".join(data.split()))

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor is not None:
            text = self.anchor["text"][0] if self.anchor["text"] else ""
            self.links.append((text, self.anchor["href"]))
            self.anchor = None
        elif tag == "ul" and self.depth:
            self.depth -= 1


def sidebar_links(response):
    parser = SidebarLinks()
    parser.feed(response.get_data(as_text=True))
    # ลิงก์โปรไฟล์ท้าย sidebar มีให้ทุก role จึงไม่นับในตารางเมนูตาม role
    return [
        (text, href)
        for text, href in parser.links
        if (
            urlsplit(href).path.startswith("/car_reservation")
            or urlsplit(href).path == "/select_system"
        )
        and urlsplit(href).path != "/car_reservation/profile"
    ]


@pytest.fixture(autouse=True)
def mock_redis_queue():
    with patch.object(redis_rq.redis_queue, "queue", MagicMock(), create=True):
        yield


@pytest.fixture
def make_org(create_org, create_user, assign_user_to_org, login_as, app):
    """org ที่เปิดโมดูลตามที่กำหนด + ผู้ใช้ที่มี role ตามที่ขอ (มีฝ่ายสังกัด)"""

    def _make(modules=("car_reservation",)):
        org = create_org("Sidebar Org")
        org.enabled_modules = list(modules)
        org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
        org.save()
        division = models.Division(name="ฝ่ายบริการ", organization=org)
        division.save()

        def user_with(roles, global_roles=(), name="Viewer", division_of=division):
            user = create_user(name, "Sidebar", roles=list(global_roles))
            member = assign_user_to_org(user, org, roles=roles)
            member.division = division_of
            member.save()
            return login_as(app.test_client(), user)

        return org, user_with

    return _make


def open_sidebar(client, org):
    response = client.get(f"{HOME}?organization_id={org.id}", follow_redirects=True)
    assert response.status_code == 200
    return sidebar_links(response)


@pytest.mark.parametrize("case", ROLE_CASES)
def test_sidebar_shows_exactly_the_links_the_role_can_use(make_org, case):
    roles, global_roles, expected = ROLE_CASES[case]
    org, user_with = make_org()
    client = user_with(roles, global_roles)

    links = open_sidebar(client, org)

    assert {text for text, _ in links} == expected | {NOTIFICATIONS}


@pytest.mark.parametrize("case", ROLE_CASES)
def test_every_sidebar_link_opens_its_own_page(make_org, case):
    roles, global_roles, _ = ROLE_CASES[case]
    org, user_with = make_org()
    client = user_with(roles, global_roles)

    broken = []
    for text, href in open_sidebar(client, org):
        response = client.get(href, follow_redirects=True)
        if (
            response.status_code != 200
            or response.request.path != urlsplit(href).path
        ):
            broken.append((text, href, response.status_code, response.request.path))

    assert broken == []


def test_switch_system_link_is_shown_when_org_has_several_modules(make_org):
    org, user_with = make_org(modules=("car_reservation", "procurement"))
    client = user_with(["staff"])

    links = open_sidebar(client, org)

    assert SWITCH_SYSTEM in {text for text, _ in links}
    for text, href in links:
        if text == SWITCH_SYSTEM:
            response = client.get(href, follow_redirects=True)
            assert (response.status_code, response.request.path) == (
                200,
                "/select_system",
            )


def test_switch_system_link_is_hidden_when_org_has_one_module(make_org):
    org, user_with = make_org(modules=("car_reservation",))
    client = user_with(["staff"])

    links = open_sidebar(client, org)

    assert SWITCH_SYSTEM not in {text for text, _ in links}


def test_switch_system_link_is_hidden_for_member_without_division(make_org):
    org, user_with = make_org(modules=("car_reservation", "procurement"))
    client = user_with(["staff"], division_of=None)

    links = open_sidebar(client, org)

    assert SWITCH_SYSTEM not in {text for text, _ in links}
