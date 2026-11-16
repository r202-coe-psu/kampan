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


def test_each_type_link_opens_the_form_of_that_type(world):
    html = world.client.get(f"{BASE}/new?organization_id={world.org.id}").get_data(
        as_text=True
    )
    links = dict(zip((key for key, _ in TYPES), type_links(html)))
    assert set(links) == {key for key, _ in TYPES}

    for key, title in TYPES:
        page = world.client.get(links[key].replace("&amp;", "&"))
        assert page.status_code == 200
        heading = re.search(
            r'<span class="text-3xl font-bold">\s*(.*?)\s*</span>',
            page.get_data(as_text=True),
            re.S,
        )
        assert heading.group(1) == title


def test_unknown_request_type_is_still_404(world):
    page = world.client.get(f"{BASE}/new?organization_id={world.org.id}&type=nope")

    assert page.status_code == 404


def test_date_param_is_passed_on_to_the_type_links_and_ignored_when_invalid(world):
    with_date = world.client.get(
        f"{BASE}/new?organization_id={world.org.id}&date=2026-12-05"
    ).get_data(as_text=True)
    bad_date = world.client.get(
        f"{BASE}/new?organization_id={world.org.id}&date=<script>"
    ).get_data(as_text=True)

    assert len(type_links(with_date)) == 8  # picker cards + modal
    assert all("date=2026-12-05" in href for href in type_links(with_date))
    assert "date=" not in " ".join(type_links(bad_date))


def urgent_links(html):
    return re.findall(r'href="([^"]*requests/urgent\?[^"]*)"', html)


def test_staff_picker_has_no_urgent_option(world):
    page = world.client.get(f"{BASE}/?organization_id={world.org.id}")

    dialog = re.search(
        r'<dialog[^>]*id="new-request-modal".*?</dialog>', page.get_data(as_text=True), re.S
    ).group(0)
    assert urgent_links(dialog) == []


def test_dispatcher_picker_lists_urgent_as_a_fifth_option(
    app, world, create_user, assign_user_to_org, login_as
):
    dispatcher = create_user("Picker", "Dispatcher")
    assign_user_to_org(dispatcher, world.org, roles=["dispatcher"])
    client = login_as(app.test_client(), dispatcher)

    for url in (f"{BASE}/?organization_id={world.org.id}", f"{BASE}/new?organization_id={world.org.id}"):
        html = client.get(url).get_data(as_text=True)
        cards = re.search(r"<ul[^>]*data-request-type-cards.*?</ul>", html, re.S).group(0)
        assert len(type_links(cards)) == 4
        assert len(urgent_links(cards)) == 1
        assert "ขอใช้รถเร่งด่วน" in cards
