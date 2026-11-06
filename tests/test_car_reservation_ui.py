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
    expression = f"{within or '.'}//{tag}" + "".join(f"[{p}]" for p in predicates)
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


def test_sidebar_marks_only_the_current_page_as_active(world):
    index_href = f"{BASE}/requests/?organization_id={world.org.id}"

    for path, expected in [
        ("/requests/", index_href),
        ("/calendar/", f"{BASE}/calendar/?organization_id={world.org.id}"),
    ]:
        doc = world.page(world.staff, path)
        current = find(doc, "a", aria_current="page", within="//*[" + has_class("drawer-side") + "]")
        assert [a.get("href") for a in current] == [expected]
        assert "menu-active" in current[0].get("class")


def test_my_requests_has_a_shell_header_a_count_and_the_same_rows_as_table_and_cards(world):
    world.reservation(request_reason="ประชุมวิชาการ")
    world.reservation(request_reason="อบรมสัมมนา", is_urgent=True)
    world.reservation(creator=world.admin, request_reason="งานของคนอื่น")

    doc = world.page(world.staff, "/requests/")

    assert words(find(doc, "h1")[0]) == "คำขอของฉัน"
    assert find(doc, "p", data_role="page-subtitle")
    assert "ทั้งหมด 2 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    table_rows = find(doc, "tr", within="//table[" + has_class("table") + "]/tbody")
    cards = find(doc, "*", data_role="request-card")
    assert [words(r) for r in table_rows if "อบรมสัมมนา" in words(r)]
    assert len(table_rows) == 2 and len(cards) == 2
    assert all("งานของคนอื่น" not in words(c) for c in cards)
    assert any("ด่วน" in words(c) for c in cards if "อบรมสัมมนา" in words(c))


def test_my_requests_shows_an_empty_state_with_a_zero_count_when_there_are_none(world):
    doc = world.page(world.staff, "/requests/")

    assert "ทั้งหมด 0 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    assert "ยังไม่มีคำขอ" in words(find(doc, "div", role="status")[0])
    assert not find(doc, "table", "table")


def test_inbox_lists_waiting_requests_as_table_rows_and_cards_with_a_count(world):
    world.reservation(request_reason="รอผู้จัดรถ")
    world.reservation(request_reason="เรื่องด่วน", is_urgent=True)
    world.reservation(request_reason="ยังรอหัวหน้า", current_step=0)

    doc = world.page(world.dispatcher, "/requests/inbox")

    assert words(find(doc, "h1")[0]) == "รายการรออนุมัติ"
    assert "ทั้งหมด 2 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    rows = find(doc, "tr", within="//table[" + has_class("table") + "]/tbody")
    cards = find(doc, "*", data_role="request-card")
    assert len(rows) == 2 and len(cards) == 2
    urgent = [c for c in cards if find(c, "span", data_role="urgent-badge")]
    assert [words(c) for c in urgent if "เรื่องด่วน" in words(c)] and len(urgent) == 1


def test_inbox_shows_an_empty_state_with_a_zero_count_when_nothing_waits(world):
    doc = world.page(world.dispatcher, "/requests/inbox")

    assert "ทั้งหมด 0 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    assert "ไม่มีรายการรออนุมัติ" in words(find(doc, "div", role="status")[0])


def test_car_management_list_has_a_count_and_the_same_cars_as_table_and_cards(world, create_car):
    create_car(world.org, "ขข 5678", vehicle_type="ตู้")

    doc = world.page(world.admin, "/cars/")

    assert words(find(doc, "h1")[0]) == "จัดการรถ"
    assert "ทั้งหมด 2 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    rows = find(doc, "tr", within="//table[" + has_class("table") + "]/tbody")
    cards = find(doc, "*", data_role="car-card")
    assert sorted(words(r).split()[0] for r in rows) == ["กก", "ขข"]
    assert len(cards) == 2
    assert find(doc, "a", "btn-primary", data_role="add-car")


def test_car_management_shows_an_empty_state_with_an_add_action_when_there_are_no_cars(world):
    models.vehicles.Car.objects.delete()

    doc = world.page(world.admin, "/cars/")

    assert "ทั้งหมด 0 รายการ" in words(find(doc, "*", data_role="list-count")[0])
    assert "ยังไม่มีรถ" in words(find(doc, "div", role="status")[0])


def test_directory_counts_cars_and_drivers_separately(world, create_user, assign_user_to_org):
    driver = create_user("Somchai", "Driver")
    assign_user_to_org(driver, world.org, roles=["driver"])

    doc = world.page(world.staff, "/cars/directory")

    assert [words(c) for c in find(doc, "*", data_role="list-count")] == [
        "ทั้งหมด 1 รายการ",
        "ทั้งหมด 1 รายการ",
    ]
    assert len(find(doc, "*", data_role="car-card")) == 1
    assert len(find(doc, "*", data_role="driver-card")) == 1


def form_sections(doc):
    """{หัวข้อส่วน: ชื่อ field (name) ที่อยู่ในส่วนนั้น}"""
    return {
        words(find(section, "h2")[0]): {
            el.get("name") for el in section.xpath(".//*[@name]") if el.get("name") != "csrf_token"
        }
        for section in find(doc, "section", data_role="form-section")
    }


@pytest.mark.parametrize(
    "request_type, extra_sections",
    [
        ("domestic", ["ค่าใช้จ่าย"]),
        ("airport", ["ค่าใช้จ่าย"]),
        ("welfare", []),
        ("abroad", ["แนบไฟล์"]),
    ],
)
def test_request_form_groups_fields_under_headed_sections(world, request_type, extra_sections):
    doc = world.page(world.staff, "/requests/new", type=request_type)

    sections = form_sections(doc)
    assert list(sections) == ["ข้อมูลผู้ขอ", "การเดินทาง", "ข้อมูลเฉพาะของแบบฟอร์ม", *extra_sections]
    # ใบสวัสดิการใช้ "สังกัด" ในส่วนเฉพาะแบบฟอร์มแทนหน่วยงานผู้ขอ
    assert ("requester_unit" in sections["ข้อมูลผู้ขอ"]) == (request_type != "welfare")
    assert "phone" in sections["ข้อมูลผู้ขอ"]
    assert {"departure_date", "return_time", "pickup_place"} <= sections["การเดินทาง"]
    if request_type == "abroad":
        assert "project_file" in sections["แนบไฟล์"]
    if extra_sections == ["ค่าใช้จ่าย"]:
        assert {"in_office_of_president", "cost_responsibilities"} <= sections["ค่าใช้จ่าย"]


def test_request_form_has_a_submit_area_with_cancel_and_submit(world):
    doc = world.page(world.staff, "/requests/new", type="domestic")

    area = find(doc, "div", data_role="form-actions")[0]
    cancel = find(area, "a", "btn-ghost")[0]
    submit = find(area, "button", "btn-primary", type="submit")[0]
    assert words(cancel) == "ยกเลิก"
    assert cancel.get("href") == f"{BASE}/requests/?organization_id={world.org.id}"
    assert words(submit) == "ยื่นคำขอ"
