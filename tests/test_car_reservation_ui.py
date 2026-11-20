"""โครงหน้าของระบบจองรถ: sidebar แบ่งกลุ่ม, หัวรายการ, ฟอร์มแบ่งส่วน, stepper และ timeline ของหน้ารายละเอียด"""

import datetime
import re

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
    "request_type, type_sections, extra_sections",
    [
        ("domestic", ["รถที่ต้องการ", "จุดหมายและวัตถุประสงค์"], ["ค่าใช้จ่าย"]),
        ("airport", ["เที่ยวบินและผู้โดยสาร"], ["ค่าใช้จ่าย"]),
        ("welfare", ["รายละเอียดงาน"], []),
        ("abroad", ["รถและจุดหมาย"], ["แนบไฟล์"]),
    ],
)
def test_request_form_groups_fields_under_headed_sections(
    world, request_type, type_sections, extra_sections
):
    doc = world.page(world.staff, "/requests/new", type=request_type)

    sections = form_sections(doc)
    assert list(sections) == ["ข้อมูลผู้ขอ", "การเดินทาง", *type_sections, *extra_sections]
    # ใบสวัสดิการใช้ "สังกัด" ในส่วนเฉพาะแบบฟอร์มแทนหน่วยงานผู้ขอ
    assert ("requester_unit" in sections["ข้อมูลผู้ขอ"]) == (request_type != "welfare")
    assert "phone" in sections["ข้อมูลผู้ขอ"]
    assert {"departure_date", "return_time", "pickup_place"} <= sections["การเดินทาง"]
    if request_type == "domestic":
        assert {"vehicle_kind", "vehicle_count", "passenger_number"} == sections["รถที่ต้องการ"]
        assert {"province_scope", "location", "request_reason"} <= sections[
            "จุดหมายและวัตถุประสงค์"
        ]
    if request_type == "abroad":
        assert "project_file" in sections["แนบไฟล์"]
    if extra_sections == ["ค่าใช้จ่าย"]:
        assert {"in_office_of_president", "cost_responsibilities"} <= sections["ค่าใช้จ่าย"]


@pytest.mark.parametrize("request_type", ["domestic", "abroad"])
def test_the_trip_purpose_field_says_what_it_asks_for(world, request_type):
    html = world.client_for(world.staff).get(
        f"/car_reservation/requests/new?organization_id={world.org.id}&type={request_type}"
    ).get_data(as_text=True)

    assert "วัตถุประสงค์การเดินทาง" in html
    assert 'placeholder="เช่น ประชุมวิชาการ' in html


def test_request_form_has_a_submit_area_with_cancel_and_submit(world):
    doc = world.page(world.staff, "/requests/new", type="domestic")

    area = find(doc, "div", data_role="form-actions")[0]
    cancel = find(area, "a", "btn-ghost")[0]
    submit = find(area, "button", "btn-primary", type="submit")[0]
    assert words(cancel) == "ยกเลิก"
    assert cancel.get("href") == f"{BASE}/requests/?organization_id={world.org.id}"
    assert words(submit) == "ยื่นคำขอ"


def detail(world, user, reservation):
    response = world.client_for(user).get(
        f"{BASE}/requests/{reservation.id}?organization_id={world.org.id}"
    )
    assert response.status_code == 200
    return lxml_html.fromstring(response.get_data(as_text=True))


def approval(step_key, decision="approved"):
    return models.car_reservations.StepApproval(
        step_key=step_key, decision=decision, decided_at=datetime.datetime(2031, 1, 2, 9, 0)
    )


def test_detail_summary_shows_the_status_urgent_badge_and_created_date(world):
    reservation = world.reservation(
        is_urgent=True, created_date=datetime.datetime(2030, 12, 25, 10, 30)
    )

    summary = find(detail(world, world.staff, reservation), "*", data_role="request-summary")[0]

    assert find(summary, "span", data_status="pending")
    assert find(summary, "span", data_role="urgent-badge")
    assert "25/12/2030" in words(summary)
    assert "รอผู้จัดรถ" in words(summary)


def test_detail_stepper_has_one_step_per_route_step_with_its_state_and_is_responsive(world):
    reservation = world.reservation(step_approvals=[approval("supervisor")])

    doc = detail(world, world.staff, reservation)

    stepper = find(doc, "ul", "steps")[0]
    classes = stepper.get("class").split()
    assert "steps-vertical" in classes and "md:steps-horizontal" in classes
    steps = find(stepper, "li", "step")
    assert [(words(li), li.get("data-state")) for li in steps] == [
        ("ผู้บังคับบัญชา", "done"),
        ("ผู้จัดรถ", "current"),
        ("หัวหน้าหน่วยยานพาหนะ", "waiting"),
    ]
    # ผ่านแล้ว = เขียวเข้ม, ขั้นที่ค้างอยู่ = เขียว + วงกระพริบ, ยังไม่ถึง = ไม่มีสี
    assert [
        [c for c in li.get("class").split() if c in ("step-done", "step-current", "step-primary")]
        for li in steps
    ] == [["step-done"], ["step-current"], []]
    assert words(steps[1]).startswith("ผู้จัดรถ")
    assert steps[1].get("aria-current") == "step"


def test_detail_stepper_marks_the_denied_step_as_an_error(world):
    reservation = world.reservation(
        status="denied", step_approvals=[approval("supervisor"), approval("dispatcher", "denied")]
    )

    steps = find(detail(world, world.staff, reservation), "li", "step")

    assert [li.get("data-state") for li in steps] == ["done", "denied", "waiting"]
    assert "step-error" in steps[1].get("class").split()


def info_sections(doc):
    """{หัวข้อการ์ดข้อมูล: ข้อความทั้งการ์ด}"""
    return {
        words(find(card, "h2")[0]): words(card)
        for card in find(doc, "*", data_role="info-section")
    }


def test_detail_groups_the_information_into_titled_cards(world):
    reservation = world.reservation(phone="081-234-5678", requester_unit="คณะวิศวกรรมศาสตร์")

    sections = info_sections(detail(world, world.staff, reservation))

    assert list(sections) == ["ข้อมูลผู้ขอ", "การเดินทาง"]
    assert "คณะวิศวกรรมศาสตร์" in sections["ข้อมูลผู้ขอ"] and "081-234-5678" in sections["ข้อมูลผู้ขอ"]
    assert "กรุงเทพฯ" in sections["การเดินทาง"] and "ประชุมวิชาการ" in sections["การเดินทาง"]
    assert "10/01/2031 08:30" in sections["การเดินทาง"]


def test_detail_adds_cards_for_the_assigned_car_and_the_form_details(world):
    reservation = world.reservation(
        status="active",
        car=world.car,
        driver=world.dispatcher,
        details=models.car_reservations.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=1, district="หาดใหญ่", province="สงขลา"
        ),
    )

    doc = detail(world, world.staff, reservation)

    sections = info_sections(doc)
    assert list(sections) == ["ข้อมูลผู้ขอ", "การเดินทาง", "รถและพนักงานขับรถ", "รายละเอียดตามแบบฟอร์ม"]
    assert find(doc, "dd", data_role="assigned-car") and "กก 1234" in sections["รถและพนักงานขับรถ"]
    assert "สงขลา" in sections["รายละเอียดตามแบบฟอร์ม"]


def audit(action, **fields):
    return models.car_reservations.ReservationAuditLog(
        action=action, created_date=datetime.datetime(2031, 1, 2, 9, 5), **fields
    )


def test_detail_audit_log_is_a_timeline_with_one_entry_per_action(world):
    reservation = world.reservation(
        audit_logs=[
            audit("submitted", actor=world.staff),
            audit("approved", actor=world.dispatcher, step_label="ผู้บังคับบัญชา", comment="เห็นชอบ"),
        ]
    )

    log = find(detail(world, world.staff, reservation), "ul", "timeline", data_role="audit-log")[0]

    entries = find(log, "li")
    assert len(entries) == 2
    assert "ยื่นคำขอ" in words(entries[0]) and "Staff" in words(entries[0])
    assert "อนุมัติ" in words(entries[1]) and "Dispatcher" in words(entries[1])
    assert "เห็นชอบ" in words(entries[1]) and "02/01/2031 09:05" in words(entries[1])


def change(label, old, new):
    return models.car_reservations.FieldChange(
        field=label, label=label, old=old, new=new
    )


def edited_reservation(world):
    return world.reservation(
        audit_logs=[
            audit("submitted", actor=world.staff),
            audit(
                "edited",
                actor=world.staff,
                comment="แก้ไขสถานที่",
                changes=[
                    change("สถานที่ปฏิบัติงาน", "กรุงเทพฯ", "เชียงใหม่"),
                    change("เวลาออกเดินทาง", "08:00", "09:30"),
                ],
            ),
        ]
    )


def test_detail_audit_entry_with_changes_offers_a_details_button_with_the_count(world):
    log = find(detail(world, world.staff, edited_reservation(world)), "ul", "timeline", data_role="audit-log")[0]

    submitted, edited = find(log, "li")
    assert "แก้ไข 2 รายการ" in words(edited)
    button = find(edited, "button", "btn", data_role="audit-details")[0]
    assert words(button) == "ดูรายละเอียด"
    assert "แก้ไข" not in words(submitted)
    assert not find(submitted, "button", data_role="audit-details")
    assert not find(submitted, "dialog")


def test_detail_audit_details_modal_lists_what_changed_from_old_to_new(world):
    log = find(detail(world, world.staff, edited_reservation(world)), "ul", "timeline", data_role="audit-log")[0]
    edited = find(log, "li")[1]
    button = find(edited, "button", data_role="audit-details")[0]
    dialog = find(edited, "dialog", "modal")[0]

    assert dialog.get("id") and dialog.get("id") in button.get("onclick")
    box = find(dialog, "div", "modal-box")[0]
    summary = words(box)
    for expected in ("แก้ไขคำขอ", "Staff", "02/01/2031 09:05", "แก้ไขสถานที่"):
        assert expected in summary
    table = find(box, "table", "table")[0]
    assert [words(th) for th in table.xpath(".//thead//th")] == ["ข้อมูล", "เดิม", "ใหม่"]
    rows = table.xpath(".//tbody/tr")
    assert [[words(td) for td in row.xpath("./td")] for row in rows] == [
        ["สถานที่ปฏิบัติงาน", "กรุงเทพฯ", "เชียงใหม่"],
        ["เวลาออกเดินทาง", "08:00", "09:30"],
    ]
    old, new = rows[0].xpath("./td")[1:]
    assert "line-through" in old.get("class") and "text-base-content/60" in old.get("class")
    assert "font-bold" in new.get("class")
    assert find(dialog, "form", "modal-backdrop", method="dialog")


def action_bar(doc):
    """แถบปุ่มดำเนินการที่หัวหน้า (ข้างปุ่มดูตัวอย่าง PDF) ไม่มีการ์ดดำเนินการด้านล่างแล้ว"""
    assert not find(doc, "div", "card", data_role="action-card")
    return find(doc, "div", data_role="action-bar")[0]


def test_detail_puts_approve_and_deny_buttons_in_the_header_and_the_approve_form_in_a_modal(world):
    reservation = world.reservation()
    approve_action = f"{BASE}/requests/{reservation.id}/approve?organization_id={world.org.id}"

    doc = detail(world, world.dispatcher, reservation)
    bar = action_bar(doc)

    approve = find(bar, "button", data_role="open-approve")
    deny = find(bar, "button", data_role="open-deny")
    assert [words(b) for b in approve] == ["อนุมัติ"] and "approve-modal" in approve[0].get("onclick")
    assert [words(b) for b in deny] == ["ไม่อนุมัติ"] and "deny-modal" in deny[0].get("onclick")
    modal = find(doc, "dialog", "modal", id="approve-modal")[0]
    assert find(find(modal, "form", action=approve_action)[0], "button", "btn-success", type="submit")
    assert not find(bar, "button", data_role="open-cancel")


def test_detail_header_offers_the_requester_only_the_cancel_action(world):
    reservation = world.reservation()

    bar = action_bar(detail(world, world.staff, reservation))

    assert [words(b) for b in find(bar, "button", data_role="open-cancel")] == ["ยกเลิกคำขอ"]
    assert not find(bar, "button", data_role="open-approve")


def test_detail_header_offers_the_dispatcher_to_acknowledge_a_cancel_request(world):
    reservation = world.reservation(status="cancel_requested", car=world.car)

    bar = action_bar(detail(world, world.dispatcher, reservation))

    assert [words(b) for b in find(bar, "button", type="submit") if "รับทราบ" in words(b)] == ["รับทราบการยกเลิก"]


def test_detail_header_has_no_action_buttons_when_the_viewer_can_do_nothing(world):
    reservation = world.reservation()

    bar = action_bar(detail(world, world.admin, reservation))

    assert not find(bar, "button", data_role="open-approve")
    assert not find(bar, "button", data_role="open-cancel")
    assert not find(bar, "a", data_role="edit-request")


@pytest.mark.parametrize(
    "viewer, modal_id, route, field",
    [("dispatcher", "deny-modal", "deny", "comment"), ("staff", "cancel-modal", "cancel", "reason")],
)
def test_detail_modals_post_their_form_and_close_from_the_backdrop(world, viewer, modal_id, route, field):
    reservation = world.reservation()
    action = f"{BASE}/requests/{reservation.id}/{route}?organization_id={world.org.id}"

    doc = detail(world, getattr(world, viewer), reservation)

    dialog = find(doc, "dialog", "modal", id=modal_id)[0]
    form = find(dialog, "form", "modal-box", action=action, method="post")[0]
    assert form.xpath(f".//*[@name='{field}']")
    assert find(form, "div", "modal-action")
    assert find(dialog, "form", "modal-backdrop", method="dialog")


def test_car_form_has_headed_sections_and_a_cancel_and_submit_area(world):
    doc = world.page(world.admin, "/cars/create")

    sections = form_sections(doc)
    assert list(sections) == ["ข้อมูลรถ", "รูปภาพ"]
    assert {"license_plate", "vehicle_type", "seat_count", "status", "description"} <= sections["ข้อมูลรถ"]
    assert "upload_image" in sections["รูปภาพ"]
    area = find(doc, "div", data_role="form-actions")[0]
    assert [words(a) for a in find(area, "a", "btn-ghost")] == ["ยกเลิก"]
    assert find(area, "button", "btn-primary", type="submit")


def test_calendar_and_type_picker_put_their_primary_action_and_subtitle_in_the_page_header(world):
    calendar = world.page(world.staff, "/calendar/")
    picker = world.page(world.staff, "/requests/new")

    actions = find(calendar, "div", data_role="page-actions")[0]
    assert find(actions, "a", "btn-primary", data_role="new-request")
    assert find(calendar, "p", data_role="page-subtitle")
    assert "เลือกแบบฟอร์มที่ต้องการยื่น" in words(find(picker, "p", data_role="page-subtitle")[0])


HARDCODED_COLOR = re.compile(
    r"#[0-9a-fA-F]{3,8}\b"
    r"|\b(?:text|bg|border|ring|from|to|via|fill|stroke|divide|outline)-"
    r"(?:red|blue|green|gray|slate|zinc|stone|amber|yellow|orange|lime|emerald|teal|cyan|sky|indigo|violet|purple|pink|rose|white|black)\b"
    r"|\[#|style=\"[^\"]*color|tns-black"
)


@pytest.mark.parametrize(
    "path, query",
    [
        ("/requests/", {}),
        ("/requests/inbox", {}),
        ("/requests/new", {}),
        ("/requests/new", {"type": "abroad"}),
        ("/cars/", {}),
        ("/cars/directory", {}),
        ("/cars/create", {}),
        ("/calendar/", {}),
    ],
)
def test_module_pages_use_theme_colors_only(world, path, query):
    doc = world.page(world.admin, path, **query)
    # footer เป็น template กลางของทุกระบบ (base/footer.html) อยู่นอกขอบเขตของระบบจองรถ
    for footer in doc.xpath("//footer"):
        footer.getparent().remove(footer)

    body = "".join(
        lxml_html.tostring(el, encoding="unicode")
        for el in doc.xpath("//*[contains(concat(' ', normalize-space(@class), ' '), ' drawer ')]")
    )
    assert HARDCODED_COLOR.findall(body) == []


@pytest.mark.parametrize(
    "user_attr, path", [("staff", "/requests/"), ("dispatcher", "/requests/inbox")]
)
def test_every_request_row_has_an_eye_button_that_opens_the_detail(world, user_attr, path):
    reservation = world.reservation(request_reason="ประชุมวิชาการ")

    doc = world.page(getattr(world, user_attr), path)

    rows = find(doc, "tr", within="//table[" + has_class("table") + "]/tbody")
    assert len(rows) == 1
    view = find(rows[0], "a", data_role="view-request")
    assert len(view) == 1
    assert f"/requests/{reservation.id}" in view[0].get("href")
    assert view[0].get("aria-label") == "ดูรายละเอียด"
    assert view[0].xpath(".//i[" + has_class("ph-eye") + "]")
