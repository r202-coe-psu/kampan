"""เลือกประเภทใบขอใช้รถก่อนกรอกฟอร์ม: หน้าเลือกประเภท และ modal ที่เปิดจากทุกหน้าของระบบจองรถ"""

import re

import pytest

BASE = "/car_reservation/requests"

TYPES = [
    ("domestic", "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ"),
    ("airport", "ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่"),
    ("welfare", "ใบขอใช้รถประเภทสวัสดิการบุคลากร"),
    ("abroad", "ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ"),
]


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Picker Org")
    org.enabled_modules = ["car_reservation"]
    org.save()
    user = create_user("Picker", "One")
    assign_user_to_org(user, org, roles=["staff"])

    class World:
        pass

    w = World()
    w.org = org
    w.client = login_as(app.test_client(), user)
    return w


def type_links(html):
    """href ของลิงก์ที่ไปหน้าฟอร์มแต่ละประเภท ตามลำดับที่ปรากฏ"""
    return re.findall(r'href="([^"]*requests/new\?[^"]*type=[^"]*)"', html)


def test_new_request_without_a_type_lists_the_four_request_types_as_links(world):
    page = world.client.get(f"{BASE}/new?organization_id={world.org.id}")

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    for key, title in TYPES:
        assert title in html
        assert any(f"type={key}" in href for href in type_links(html))


def test_requests_list_has_the_type_modal_and_a_button_that_opens_it(world):
    page = world.client.get(f"{BASE}/?organization_id={world.org.id}")

    html = page.get_data(as_text=True)
    dialog = re.search(r'<dialog[^>]*id="new-request-modal".*?</dialog>', html, re.S)
    assert dialog, "modal is missing"
    modal_links = type_links(dialog.group(0))
    assert len(modal_links) == 4
    for key, title in TYPES:
        assert title in dialog.group(0)
        assert any(f"type={key}" in href for href in modal_links)
    assert len(re.findall(r"<a [^>]*data-open-new-request", html)) == 2
