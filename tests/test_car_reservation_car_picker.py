"""ตัวเลือกรถแบบตาราง (#79 ส่วน B): endpoint `timeline.picker`, การคำนวณช่วง/แถบไฮไลต์/รถชน,
และฟอร์มจัดรถ (อนุมัติ งานด่วน งานแทรก) ที่ใช้ตารางนี้แทนการเลือกรถจาก dropdown"""

import datetime
import re

import pytest
from lxml import html as lxml_html

from kampan import models
from kampan.utils import car_reservation_flow as flow
from kampan.utils import car_timeline
from tests.test_car_reservation import (  # noqa: F401
    DAY,
    approve_url,
    assigned_request,
    detail_url,
    dispatch_data,
    insert_url,
    insert_world,
    mock_redis_queue,
    slot_data,
    urgent_data,
    urgent_url,
    world,
)
from tests.test_car_reservation_multi_car import (  # noqa: F401
    fleet,
    request_at_dispatcher_for,
)

PICKER = "/car_reservation/timeline/picker"
HOUR = datetime.timedelta(hours=1)


def stamp(value):
    return value.strftime("%Y-%m-%dT%H:%M")


@pytest.fixture
def picker_world(fleet):
    """fleet (รถเก๋ง 1 คัน รถตู้ 2 คัน) + ผู้จัดรถ client และฟังก์ชันขอ partial ของตัวเลือกรถ"""
    fleet.dispatcher_client = fleet.client_for(fleet.dispatcher)

    def picker(params=None, client=None, organization=None):
        query = {"organization_id": str((organization or fleet.org).id), **(params or {})}
        return (client or fleet.dispatcher_client).get(PICKER, query_string=query)

    def window(start=DAY, end=DAY + 9 * HOUR, **extra):
        return {"start": stamp(start), "end": stamp(end), **extra}

    def text(params=None, **kwargs):
        response = picker(params, **kwargs)
        assert response.status_code == 200, response.get_data(as_text=True)[:500]
        return response.get_data(as_text=True)

    fleet.picker = picker
    fleet.window = window
    fleet.text = text
    return fleet


def doc_of(page):
    return lxml_html.fromstring(f"<div>{page}</div>")


def row_of(page, car):
    """แถวรถ (div ของ car-row) ของรถคันนั้นในตัวเลือกรถ"""
    (row,) = doc_of(page).xpath(f"//div[@data-role='car-row'][@data-car-id='{car.id}']")
    return row


def roles_in(row, role):
    return row.xpath(f".//*[@data-role='{role}']")


# ------------------------------------------------------------ รถว่าง / รถชน


def test_a_free_car_is_selectable_and_has_no_busy_badge(picker_world):
    row = row_of(picker_world.text(picker_world.window()), picker_world.car)

    assert row.get("data-selectable") == "1"
    assert row.get("data-pick-state") == "free"
    assert not roles_in(row, "car-busy-badge")
    assert row.xpath(".//*[@data-role='pick-cell'][@aria-disabled='false']")


def test_a_car_held_by_another_request_is_disabled_with_the_requester_and_a_link(picker_world):
    blocking = assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 6 * HOUR,
        car=picker_world.car,
        driver=picker_world.driver2,
    )

    page = picker_world.text(picker_world.window())
    row = row_of(page, picker_world.car)

    assert row.get("data-selectable") == "0"
    assert row.get("data-pick-state") == "busy"
    assert roles_in(row, "car-busy-badge")[0].text_content().strip() == "ไม่ว่าง"
    conflict = roles_in(row, "conflict")[0].text_content()
    assert picker_world.requester.get_name() in conflict
    assert "งานเดิม" not in conflict  # บอกผู้ขอและเวลา ไม่ใช่รายละเอียดอื่น
    [link] = roles_in(row, "conflict-link")
    assert link.get("href") == detail_url(picker_world, blocking)
    assert link.get("target") == "_blank"
    # รถคันอื่นยังว่าง
    assert row_of(page, picker_world.car2).get("data-selectable") == "1"


def test_a_car_lent_through_diis_is_disabled_with_a_plain_badge_and_no_link(picker_world):
    models.vehicle_applications.CarApplication(
        organization=picker_world.org,
        car=picker_world.car2,
        location="สนามบินหาดใหญ่",
        status="active",
        using_type="general",
        request_reason="ไปราชการ",
        departure_datetime=DAY + 2 * HOUR,
        return_datetime=DAY + 6 * HOUR,
    ).save()

    row = row_of(picker_world.text(picker_world.window()), picker_world.car2)

    assert row.get("data-selectable") == "0"
    assert roles_in(row, "diis-badge")[0].text_content().strip() == "ยืมผ่านระบบเดิม"
    assert not roles_in(row, "conflict-link")
    assert not row.xpath(".//a")


@pytest.mark.parametrize(
    "status, blocks",
    [
        ("pending", True),
        ("active", True),
        ("cancel_requested", True),
        ("completed", False),
        ("cancelled", False),
        ("denied", False),
    ],
)
def test_only_the_statuses_the_server_blocks_on_make_a_car_busy(picker_world, status, blocks):
    assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 6 * HOUR,
        status=status,
        car=picker_world.car,
        driver=picker_world.driver2,
    )

    row = row_of(picker_world.text(picker_world.window()), picker_world.car)

    assert (row.get("data-selectable") == "0") is blocks


def test_a_booking_that_only_touches_the_window_edge_does_not_clash(picker_world):
    # ใช้ช่วงครึ่งเปิดเหมือน server: งานที่จบตอนที่คำขอเริ่มพอดีไม่ทับ
    assigned_request(
        picker_world, DAY - 3 * HOUR, DAY, car=picker_world.car, driver=picker_world.driver2
    )

    row = row_of(picker_world.text(picker_world.window()), picker_world.car)

    assert row.get("data-selectable") == "1"


def test_the_request_being_dispatched_does_not_clash_with_itself(picker_world):
    own = assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 6 * HOUR,
        car=picker_world.car,
        driver=picker_world.driver2,
    )

    without = row_of(picker_world.text(picker_world.window()), picker_world.car)
    with_exclude = picker_world.text(picker_world.window(exclude=str(own.id)))
    row = row_of(with_exclude, picker_world.car)

    assert without.get("data-selectable") == "0"
    assert row.get("data-selectable") == "1"
    # แท่งของคำขอตัวเองก็ไม่ถูกวาดเป็นงานอื่น
    assert str(own.id) not in with_exclude


def test_the_same_drivers_main_job_car_stays_selectable_for_an_insert_job(picker_world):
    # งานหลักของ พขร. คนเดิมใช้รถคันนี้ทับช่วงงานแทรก: ยกเว้นเฉพาะเมื่อส่ง driver ของงานแทรกมา (กติกา #76)
    assigned_request(
        picker_world,
        DAY,
        DAY + 9 * HOUR,
        car=picker_world.car,
        driver=picker_world.driver,
    )
    other_job = assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 5 * HOUR,
        car=picker_world.car2,
        driver=picker_world.driver2,
    )
    window = picker_world.window(DAY + 2 * HOUR, DAY + 4 * HOUR)

    no_driver = picker_world.text(window)
    same_driver = picker_world.text({**window, "driver": str(picker_world.driver.id)})

    assert row_of(no_driver, picker_world.car).get("data-selectable") == "0"
    assert row_of(same_driver, picker_world.car).get("data-selectable") == "1"
    # รถที่ พขร. คนอื่นถืออยู่ยังบล็อก แม้ระบุ driver
    blocked = row_of(same_driver, picker_world.car2)
    assert blocked.get("data-selectable") == "0"
    assert roles_in(blocked, "conflict-link")[0].get("href") == detail_url(picker_world, other_job)


def test_a_diis_loan_still_blocks_an_insert_jobs_own_driver(picker_world):
    models.vehicle_applications.CarApplication(
        organization=picker_world.org,
        car=picker_world.car,
        location="สนามบินหาดใหญ่",
        status="active",
        using_type="general",
        request_reason="ไปราชการ",
        departure_datetime=DAY,
        return_datetime=DAY + 9 * HOUR,
    ).save()

    page = picker_world.text(picker_world.window(driver=str(picker_world.driver.id)))

    assert row_of(page, picker_world.car).get("data-selectable") == "0"


def test_the_picker_agrees_with_the_servers_clash_check_for_every_car(picker_world):
    """ที่เห็นบนจอตรงกับที่ server บล็อก: เทียบ `_car_is_taken` ทีละคันในหลายสถานการณ์"""
    third = picker_world.car3
    assigned_request(
        picker_world,
        DAY + HOUR,
        DAY + 3 * HOUR,
        status="pending",
        car=picker_world.car,
        driver=picker_world.driver2,
    )
    assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 4 * HOUR,
        status="completed",
        car=picker_world.car2,
        driver=picker_world.driver2,
    )
    models.vehicle_applications.CarApplication(
        organization=picker_world.org,
        car=third,
        location="x",
        status="pending on header",
        using_type="general",
        request_reason="x",
        departure_datetime=DAY + 8 * HOUR,
        return_datetime=DAY + 12 * HOUR,
    ).save()
    app = models.CarReservation(
        organization=picker_world.org, departure_datetime=DAY, return_datetime=DAY + 9 * HOUR
    )

    page = picker_world.text(picker_world.window())

    for car in (picker_world.car, picker_world.car2, third):
        taken = flow._car_is_taken(app, car)
        assert (row_of(page, car).get("data-selectable") == "0") is bool(taken), car.license_plate


def test_conflicts_use_one_reservation_query_and_one_diis_query(picker_world, monkeypatch):
    calls = {"reservations": 0, "diis": 0}
    real_reservations = flow.overlapping_reservations
    real_diis = flow.diis_bookings_overlapping

    def reservations(*args, **kwargs):
        calls["reservations"] += 1
        return real_reservations(*args, **kwargs)

    def diis(*args, **kwargs):
        calls["diis"] += 1
        return real_diis(*args, **kwargs)

    monkeypatch.setattr(flow, "overlapping_reservations", reservations)
    monkeypatch.setattr(flow, "diis_bookings_overlapping", diis)

    picker_world.text(picker_world.window())

    assert calls == {"reservations": 1, "diis": 1}


# ------------------------------------------------------------ กลุ่มประเภท / ช่วงที่แสดง


def group_keys(page):
    return doc_of(page).xpath("//div[@data-role='group-head']/@data-group")


def test_the_requested_kind_group_comes_first_and_is_expanded(picker_world):
    page = picker_world.text(picker_world.window(kind="ตู้"))
    doc = doc_of(page)

    assert group_keys(page) == ["ตู้", "เก๋ง"]
    heads = {head.get("data-group"): head for head in doc.xpath("//div[@data-role='group-head']")}
    assert heads["ตู้"].get("data-requested") == "1"
    assert heads["ตู้"].get("data-default-collapsed") == "0"
    assert heads["เก๋ง"].get("data-default-collapsed") == "1"
    assert "ประเภทที่ขอ" in heads["ตู้"].text_content()
    # กลุ่มอื่นยังอยู่ในหน้า เข้าถึงได้ (พับไว้ ไม่ถูกตัดออก)
    assert row_of(page, picker_world.car).get("hidden") is not None
    assert row_of(page, picker_world.car2).get("hidden") is None


def test_without_a_requested_kind_groups_keep_the_standard_order_all_expanded(picker_world):
    page = picker_world.text(picker_world.window())

    assert group_keys(page) == ["ตู้", "เก๋ง"]  # ลำดับมาตรฐาน: บัส มินิบัส ตู้ เก๋ง
    assert doc_of(page).xpath("//div[@data-role='group-head'][@data-default-collapsed='1']") == []


def test_a_requested_kind_that_sorts_later_is_moved_to_the_front(picker_world):
    assert group_keys(picker_world.text(picker_world.window(kind="เก๋ง"))) == ["เก๋ง", "ตู้"]


def test_the_view_spans_the_window_plus_two_days_each_side_with_a_highlight_band(picker_world):
    # คำขอ DAY 08:00 – DAY 17:00 (วันเดียว) -> แสดง DAY-2 .. DAY+2 = 5 วัน
    page = picker_world.text(picker_world.window())
    doc = doc_of(page)

    dates = doc.xpath("//div[@data-date]/@data-date")
    assert dates == [(DAY.date() + datetime.timedelta(days=n)).isoformat() for n in range(-2, 3)]
    (band,) = doc.xpath("//div[@data-role='request-window']")
    total = 5 * 24
    left = round((2 * 24 + 8) / total * 100, 4)
    width = round(9 / total * 100, 4)
    assert f"left: {left}%; width: {width}%" in band.get("style")


def test_a_multi_day_window_band_spans_its_days(picker_world):
    start, end = DAY, DAY + datetime.timedelta(days=2, hours=1)  # 08:00 .. 09:00 สองวันถัดไป
    page = picker_world.text(picker_world.window(start, end))
    doc = doc_of(page)

    assert len(doc.xpath("//div[@data-date]")) == 7  # วันที่ 0..2 + เผื่อหน้า-หลังข้างละ 2 วัน
    (band,) = doc.xpath("//div[@data-role='request-window']")
    total = 7 * 24
    assert f"left: {round(56 / total * 100, 4)}%; width: {round(49 / total * 100, 4)}%" in band.get("style")


def test_the_range_is_clamped_to_31_days_and_the_band_is_clipped(picker_world):
    start, end = DAY, DAY + datetime.timedelta(days=40)
    page = picker_world.text(picker_world.window(start, end))
    doc = doc_of(page)

    assert len(doc.xpath("//div[@data-date]")) == 31
    assert "--tl-days: 31" in page
    (band,) = doc.xpath("//div[@data-role='request-window']")
    style = band.get("style")
    left, width = (float(v) for v in re.findall(r"([\d.]+)%", style))
    assert left + width == pytest.approx(100, abs=0.01)  # แถบถูกตัดที่ขอบขวาของช่วงที่แสดง


def test_picker_range_helper_pads_two_days_and_treats_midnight_return_as_previous_day():
    start = datetime.datetime(2026, 11, 11, 12)
    end = datetime.datetime(2026, 11, 12, 0)

    first, days = car_timeline.picker_range(start, end)

    assert first == datetime.date(2026, 11, 9)
    assert days == 5  # 9,10,11 + 12,13 (เวลากลับ 00:00 พอดีไม่นับวันที่ 12 เป็นวันของคำขอ แต่ยังเผื่อ 2 วัน -> ถึง 13)


def test_other_requests_in_the_range_are_drawn_as_bars(picker_world):
    assigned_request(
        picker_world,
        DAY + 2 * HOUR,
        DAY + 6 * HOUR,
        car=picker_world.car2,
        driver=picker_world.driver2,
    )

    bars = doc_of(picker_world.text(picker_world.window())).xpath("//button[@data-role='bar']")

    assert len(bars) == 1


# ------------------------------------------------------------ ช่องที่เลือก


def test_cars_chosen_in_other_slots_are_disabled_for_the_active_slot(picker_world):
    selected = f"{picker_world.car2.id},,{picker_world.car.id}"

    page = picker_world.text(picker_world.window(selected=selected, slot="2"))

    first = row_of(page, picker_world.car2)
    assert first.get("data-chosen-slot") == "1"
    assert first.get("data-pick-state") == "elsewhere"
    assert "เลือกในคันที่ 1 แล้ว" in roles_in(first, "pick-status")[0].text_content()
    assert first.xpath(".//*[@data-role='pick-cell'][@aria-disabled='true']")
    third = row_of(page, picker_world.car)
    assert third.get("data-chosen-slot") == "3"
    assert third.get("data-pick-state") == "elsewhere"
    # รถที่ไม่ได้เลือกยังว่าง
    assert row_of(page, picker_world.car3).get("data-pick-state") == "free"


def test_the_car_chosen_in_the_active_slot_stays_clickable_so_it_can_be_cleared(picker_world):
    page = picker_world.text(picker_world.window(selected=str(picker_world.car2.id), slot="1"))

    row = row_of(page, picker_world.car2)

    assert row.get("data-pick-state") == "chosen"
    assert roles_in(row, "pick-status")[0].text_content().strip() == "เลือกแล้ว"
    assert row.xpath(".//*[@data-role='pick-cell'][@aria-disabled='false']")


def test_a_selected_car_that_is_busy_stays_busy(picker_world):
    assigned_request(
        picker_world, DAY, DAY + 9 * HOUR, car=picker_world.car2, driver=picker_world.driver2
    )

    row = row_of(
        picker_world.text(picker_world.window(selected=str(picker_world.car2.id), slot="1")),
        picker_world.car2,
    )

    assert row.get("data-pick-state") == "busy"


# ------------------------------------------------------------ สิทธิ์


@pytest.mark.parametrize("who", ["requester", "supervisor", "stranger", "driver"])
def test_only_a_dispatcher_can_load_the_picker(picker_world, who):
    response = picker_world.picker(
        picker_world.window(), client=picker_world.client_for(getattr(picker_world, who))
    )

    assert response.status_code in (302, 403)
    assert "data-tl-grid" not in response.get_data(as_text=True)


def test_an_org_admin_without_the_dispatcher_role_is_denied(
    picker_world, create_user, assign_user_to_org
):
    admin = create_user("Admin", "NoDispatch")
    assign_user_to_org(admin, picker_world.org, roles=["admin"])

    response = picker_world.picker(picker_world.window(), client=picker_world.client_for(admin))

    assert response.status_code in (302, 403)


def test_a_system_admin_without_the_dispatcher_role_is_denied(picker_world, create_user):
    sysadmin = create_user("Sys", "Admin", roles=["admin"])

    response = picker_world.picker(picker_world.window(), client=picker_world.client_for(sysadmin))

    assert response.status_code in (302, 403)


def test_a_dispatcher_of_another_org_cannot_see_this_orgs_cars(
    picker_world, create_org, create_user, assign_user_to_org, create_car
):
    other_org = create_org("Picker Other Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    outsider = create_user("Outsider", "Dispatcher")
    assign_user_to_org(outsider, other_org, roles=["dispatcher"])
    create_car(other_org, "ซซ 9999", vehicle_type="ตู้")
    client = picker_world.client_for(outsider)

    denied = picker_world.picker(picker_world.window(), client=client)
    own = picker_world.picker(picker_world.window(), client=client, organization=other_org)

    assert denied.status_code in (302, 403)
    assert "กก 1234" not in denied.get_data(as_text=True)
    page = own.get_data(as_text=True)
    assert own.status_code == 200
    assert "ซซ 9999" in page
    assert "กก 1234" not in page and "ขข 5678" not in page


def test_a_clash_from_another_org_is_never_reported(
    picker_world, create_org, create_user, assign_user_to_org
):
    other_org = create_org("Picker Neighbour Org")
    outsider = create_user("Neighbour", "Requester")
    assign_user_to_org(outsider, other_org, roles=["staff"])
    models.CarReservation(
        organization=other_org,
        creator=outsider,
        request_type="domestic",
        province_scope="in_province",
        location="x",
        request_reason="x",
        departure_datetime=DAY,
        return_datetime=DAY + 9 * HOUR,
        status="active",
        assignments=[models.CarAssignment(car=picker_world.car, driver=picker_world.driver)],
    ).save()

    row = row_of(picker_world.text(picker_world.window()), picker_world.car)

    assert row.get("data-selectable") == "1"


# ------------------------------------------------------------ ค่าขยะ / ช่วงเวลาผิด


def test_garbage_parameters_do_not_crash_the_picker(picker_world):
    garbage = {
        "start": "not-a-date",
        "end": "99999-99-99T99:99",
        "kind": "'; drop table cars; --",
        "exclude": "zzz",
        "driver": "../../etc/passwd",
        "selected": "a,b,,%00,,,,,,,,,,,,",
        "slot": "99999999999999999999",
    }

    response = picker_world.picker(garbage)

    assert response.status_code == 200
    assert 'data-role="picker-hint"' in response.get_data(as_text=True)


def test_garbage_ids_are_ignored_when_the_window_is_valid(picker_world):
    page = picker_world.text(
        picker_world.window(
            kind="ไม่มีประเภทนี้", exclude="zzz", driver="x", selected="zz,,yy", slot="abc"
        )
    )

    assert row_of(page, picker_world.car).get("data-pick-state") == "free"
    assert group_keys(page) == ["ตู้", "เก๋ง"]  # kind ที่ไม่รู้จักไม่ทำให้จัดกลุ่มใหม่


def test_a_missing_window_shows_a_hint_not_an_error(picker_world):
    page = picker_world.text({"start": stamp(DAY)})

    assert "กรอกวัน-เวลาออกและกลับให้ครบ" in page
    assert "data-tl-grid" not in page


def test_an_end_that_is_not_after_the_start_shows_a_hint(picker_world):
    for end in (DAY, DAY - HOUR):
        page = picker_world.text({"start": stamp(DAY), "end": stamp(end)})

        assert "เวลากลับต้องหลังเวลาออก" in page
        assert "data-tl-grid" not in page


def test_a_garbage_organization_id_is_refused_not_a_server_error(picker_world):
    response = picker_world.dispatcher_client.get(
        PICKER, query_string={**picker_world.window(), "organization_id": "not-an-id"}
    )

    assert response.status_code in (302, 403, 404)
    assert "data-tl-grid" not in response.get_data(as_text=True)


# ------------------------------------------------------------ หน้าตารางรถปกติไม่เปลี่ยน


def test_the_fleet_timeline_page_is_unchanged_by_the_picker_changes(picker_world):
    page = picker_world.dispatcher_client.get(
        "/car_reservation/timeline/", query_string={"organization_id": str(picker_world.org.id)}
    ).get_data(as_text=True)

    assert "data-tl-grid" in page
    for picker_only in ("request-window", "data-pk-toggle", 'data-role="pick-cell"', "data-pick-state"):
        assert picker_only not in page
    assert "data-tl-toggle" in page


# ------------------------------------------------------------ ฟอร์มอนุมัติ


def approve_page(world, reservation):
    return world.dispatcher_client.get(detail_url(world, reservation)).get_data(as_text=True)


def test_the_approve_modal_has_the_picker_slot_buttons_and_the_fallback_selects(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 2)
    doc = lxml_html.fromstring(approve_page(picker_world, reservation))

    (picker,) = doc.xpath("//section[@id='car-picker']")
    assert picker.get("data-requested") == "2"
    assert picker.get("data-kind") == "ตู้"
    # ช่วงของคำขอคงที่: ไม่โหลดใหม่ด้วย htmx
    assert picker.get("hx-get") is None
    assert doc.xpath("//dialog[@data-role='approve-modal']//section[@id='car-picker']")
    slots = doc.xpath("//div[@data-picker-slot]")
    assert [slot.get("data-select-id") for slot in slots] == [
        "assignments-0-car",
        "assignments-1-car",
    ]
    for index in range(2):
        assert doc.xpath(f"//select[@name='assignments-{index}-car']")
    assert doc.xpath("//div[@data-role='request-window']")
    assert group_keys(approve_page(picker_world, reservation))[0] == "ตู้"


def test_the_approve_modal_marks_cars_held_by_other_requests_and_not_the_request_itself(
    picker_world,
):
    reservation = request_at_dispatcher_for(picker_world, 1)
    blocking = assigned_request(
        picker_world,
        reservation.departure_datetime + HOUR,
        reservation.departure_datetime + 3 * HOUR,
        car=picker_world.car2,
        driver=picker_world.driver2,
    )

    page = approve_page(picker_world, reservation)

    assert row_of(page, picker_world.car2).get("data-selectable") == "0"
    assert roles_in(row_of(page, picker_world.car2), "conflict-link")[0].get("href") == detail_url(
        picker_world, blocking
    )
    assert row_of(page, picker_world.car3).get("data-selectable") == "1"


def test_only_the_dispatcher_step_with_permission_gets_the_picker(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 1)

    for user in (picker_world.requester, picker_world.stranger):
        page = picker_world.client_for(user).get(detail_url(picker_world, reservation)).get_data(
            as_text=True
        )
        assert "car-picker" not in page


def test_posting_an_occupied_car_directly_is_still_refused_with_the_conflict_link(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 1)
    blocking = assigned_request(
        picker_world,
        reservation.departure_datetime + HOUR,
        reservation.departure_datetime + 3 * HOUR,
        car=picker_world.car2,
        driver=picker_world.driver2,
    )

    client = picker_world.dispatcher_client
    response = client.post(
        approve_url(picker_world, reservation),
        data=dispatch_data(picker_world.car2, picker_world.driver),
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert "รถ ขข 5678 มีงานช่วงเวลานี้แล้ว" in html
    assert "ดูคำขอที่ชน" in html
    assert detail_url(picker_world, blocking).replace("&", "&amp;") in html
    reservation.reload()
    assert reservation.assignments == []


def test_posting_the_same_car_twice_is_still_refused_by_the_flow(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 2)

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data={
            "comment": "",
            **slot_data(picker_world.car2, picker_world.driver),
            **slot_data(picker_world.car2, picker_world.driver2, index=1),
        },
        follow_redirects=True,
    )

    assert flow.DUPLICATE_CAR in response.get_data(as_text=True)
    reservation.reload()
    assert reservation.assignments == []


# ------------------------------------------------------------ เตือนรถคนละประเภท (server)


def toast_text(html, category):
    """ข้อความ toast ทั้งหมดของ category นั้น (success/error/info เป็น toast)"""
    return " ".join(
        re.findall(rf'data-toast-category="{category}".*?</div>', html, flags=re.S)
    )


TYPE_WARNING = "รถที่จัดไม่ตรงกับประเภทที่ผู้ขอขอ"


def warning_modal(html):
    """flash แบบ warning แสดงเป็น AlertModal "โปรดทราบ" ที่เปิดเองตอนโหลดหน้า"""
    return " ".join(re.findall(r'<dialog[^>]*id="flash-\d+".*?</dialog>', html, flags=re.S))


def test_a_car_of_a_different_type_than_requested_is_allowed_with_a_warning_flash(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 1)  # ผู้ขอขอรถตู้
    assert reservation.details.vehicle_kind == "ตู้"

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data=dispatch_data(picker_world.car, picker_world.driver),  # กก 1234 เป็นรถเก๋ง
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    reservation.reload()
    assert reservation.cars == [picker_world.car]  # ไม่บล็อก
    assert "บันทึกการอนุมัติเรียบร้อยแล้ว" in toast_text(html, "success")
    warning = warning_modal(html)
    assert TYPE_WARNING in warning
    assert "ขอ ตู้" in warning and "กก 1234 (เก๋ง)" in warning


def test_the_warning_names_only_the_cars_of_a_different_type(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 2)

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data={
            "comment": "",
            **slot_data(picker_world.car, picker_world.driver),
            **slot_data(picker_world.car2, picker_world.driver2, index=1),
        },
        follow_redirects=True,
    )

    warning = warning_modal(response.get_data(as_text=True))
    assert "กก 1234 (เก๋ง)" in warning
    assert "ขข 5678 (ตู้)" not in warning


def test_no_warning_when_every_car_matches_the_requested_type(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 2)

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data={
            "comment": "",
            **slot_data(picker_world.car2, picker_world.driver),
            **slot_data(picker_world.car3, picker_world.driver2, index=1),
        },
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert "บันทึกการอนุมัติเรียบร้อยแล้ว" in toast_text(html, "success")
    assert TYPE_WARNING not in html


def test_a_car_with_no_type_is_not_reported_as_a_different_type(picker_world, create_car):
    untyped = create_car(picker_world.org, "งง 0001")
    reservation = request_at_dispatcher_for(picker_world, 1)

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data=dispatch_data(untyped, picker_world.driver),
        follow_redirects=True,
    )

    assert TYPE_WARNING not in response.get_data(as_text=True)


def test_an_urgent_request_with_a_different_type_car_warns_after_it_is_created(picker_world):
    response = picker_world.dispatcher_client.post(
        urgent_url(picker_world),
        data=urgent_data(picker_world),  # ขอรถตู้ แต่ world.car เป็นรถเก๋ง
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)
    assert models.CarReservation.objects(organization=picker_world.org).count() == 1
    assert "สร้างคำขอเร่งด่วนเรียบร้อยแล้ว" in toast_text(html, "success")
    assert "กก 1234 (เก๋ง)" in warning_modal(html)


def test_a_failed_dispatch_gives_no_type_warning(picker_world):
    reservation = request_at_dispatcher_for(picker_world, 1)
    assigned_request(
        picker_world,
        reservation.departure_datetime,
        reservation.return_datetime,
        car=picker_world.car,
        driver=picker_world.driver2,
    )

    response = picker_world.dispatcher_client.post(
        approve_url(picker_world, reservation),
        data=dispatch_data(picker_world.car, picker_world.driver),
        follow_redirects=True,
    )

    assert TYPE_WARNING not in response.get_data(as_text=True)


# ------------------------------------------------------------ ฟอร์มงานด่วน


def test_the_urgent_form_renders_the_picker_container_with_htmx_reload_attributes(picker_world):
    doc = lxml_html.fromstring(
        picker_world.dispatcher_client.get(urgent_url(picker_world)).get_data(as_text=True)
    )

    (picker,) = doc.xpath("//section[@id='car-picker']")
    assert picker.get("hx-get").startswith(PICKER)
    assert f"organization_id={picker_world.org.id}" in picker.get("hx-get")
    assert picker.get("hx-trigger").startswith("change from:#car-picker-params")
    assert picker.get("hx-include") == "#car-picker-params input"
    assert picker.get("hx-target") == "#car-picker-body"
    assert picker.get("hx-swap") == "innerHTML"
    assert picker.get("data-window-inputs") == "departure_date,departure_time,return_date,return_time"
    assert picker.get("data-kind-input") == "vehicle_kind"
    assert picker.get("data-requested-input") == "vehicle_count"
    # พารามิเตอร์ของ endpoint อยู่ใน input ซ่อนที่ไม่ถูกส่งไปกับฟอร์มหลัก
    names = picker.xpath(".//*[@id='car-picker-params']//input/@name")
    assert names == ["start", "end", "kind", "driver", "selected", "slot"]
    assert all(
        i.get("form") == "car-picker-aux" for i in picker.xpath(".//*[@id='car-picker-params']//input")
    )
    # ยังไม่มีเวลา: คำใบ้แทนตาราง
    assert "กรอกวัน-เวลาออกและกลับให้ครบ" in picker.text_content()


def test_the_urgent_form_keeps_five_slot_buttons_and_the_fallback_selects(picker_world):
    doc = lxml_html.fromstring(
        picker_world.dispatcher_client.get(urgent_url(picker_world)).get_data(as_text=True)
    )

    slots = doc.xpath("//div[@data-picker-slot]")
    assert [slot.get("data-slot-number") for slot in slots] == ["1", "2", "3", "4", "5"]
    assert all(slot.get("hidden") is not None for slot in slots)  # JS เปิดให้ ไม่มี JS ใช้ <select>
    for index in range(5):
        assert doc.xpath(f"//select[@name='assignments-{index}-car']")
        assert doc.xpath(f"//select[@name='assignments-{index}-driver']")
    assert doc.xpath("//section[@id='car-picker'][@hidden]")


def test_the_urgent_form_shows_the_table_again_after_a_failed_post(picker_world):
    response = picker_world.dispatcher_client.post(
        urgent_url(picker_world),
        data=urgent_data(picker_world, vehicle_count="2"),  # จัดไม่ครบ: ฟอร์มไม่ผ่าน
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-role="request-window"' in page
    chosen = row_of(page, picker_world.car)
    # ผู้จัดรถเลือกรถไว้ในคันที่ 1 แล้ว: ช่องที่กำลังเลือกคือช่องว่างช่องแรก (คันที่ 2) จึงเลือกซ้ำคันที่ 1 ไม่ได้
    assert chosen.get("data-chosen-slot") == "1"
    assert chosen.get("data-pick-state") == "elsewhere"
    assert "เลือกในคันที่ 1 แล้ว" in roles_in(chosen, "pick-status")[0].text_content()
    assert row_of(page, picker_world.car2).get("data-pick-state") == "free"


def test_an_urgent_post_with_a_busy_car_is_refused_with_the_conflict_link(picker_world):
    data = urgent_data(picker_world)
    departure = datetime.datetime.combine(
        datetime.date.fromisoformat(data["departure_date"]), datetime.time(8)
    )
    blocking = assigned_request(
        picker_world,
        departure + HOUR,
        departure + 3 * HOUR,
        car=picker_world.car,
        driver=picker_world.driver2,
    )

    response = picker_world.dispatcher_client.post(urgent_url(picker_world), data=data)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ดูคำขอที่ชน" in html
    assert detail_url(picker_world, blocking).replace("&", "&amp;") in html
    assert models.CarReservation.objects(organization=picker_world.org, is_urgent=True).count() == 0
    # ตารางที่แสดงกลับมาก็ทำเครื่องหมายรถคันนั้นว่าไม่ว่าง
    assert row_of(html, picker_world.car).get("data-selectable") == "0"


# ------------------------------------------------------------ ฟอร์มงานแทรก


def test_the_insert_form_renders_the_picker_driver_reload_and_the_fallback_select(insert_world):
    doc = lxml_html.fromstring(
        insert_world.client_for(insert_world.dispatcher)
        .get(insert_url(insert_world))
        .get_data(as_text=True)
    )

    (picker,) = doc.xpath("//section[@id='car-picker']")
    assert picker.get("hx-get").startswith(PICKER)
    assert picker.get("hx-trigger").startswith("change from:#car-picker-params")
    assert picker.get("data-driver-input") == "driver"
    assert picker.get("data-window-inputs") == "departure_date,departure_time,return_date,return_time"
    assert picker.get("data-requested") is None and picker.get("data-kind") == ""
    assert len(doc.xpath("//div[@data-picker-slot]")) == 1
    assert doc.xpath("//select[@name='car']") and doc.xpath("//select[@name='driver']")
    # เวลามาก่อนรถในฟอร์ม
    html = lxml_html.tostring(doc, encoding="unicode")
    assert html.index('name="departure_date"') < html.index('id="car-picker"')


def test_the_insert_form_picker_keeps_the_main_job_car_selectable_for_the_chosen_driver(
    insert_world,
):
    client = insert_world.client_for(insert_world.dispatcher)
    params = {
        "organization_id": str(insert_world.org.id),
        "start": stamp(DAY + 2 * HOUR),
        "end": stamp(DAY + 3 * HOUR + HOUR // 2),
    }

    for driver, selectable in ((insert_world.driver.id, "1"), (None, "0")):
        query = dict(params, **({"driver": str(driver)} if driver else {}))
        page = client.get(PICKER, query_string=query).get_data(as_text=True)
        assert row_of(page, insert_world.car).get("data-selectable") == selectable


def test_the_insert_form_failed_post_shows_the_table_for_the_posted_driver(insert_world):
    from tests.test_car_reservation import insert_data

    other = insert_world.add_driver("Other", "Driver")
    response = insert_world.client_for(insert_world.dispatcher).post(
        insert_url(insert_world),
        data=insert_data(insert_world, driver=str(other.id), car=str(insert_world.car.id)),
    )

    page = response.get_data(as_text=True)
    assert response.status_code == 200  # other ไม่มีงานวันนั้น: ฟอร์มไม่ผ่าน
    # พขร. ที่ส่งมาไม่ใช่เจ้าของงานหลัก: รถของงานหลักยังบล็อก
    assert row_of(page, insert_world.car).get("data-selectable") == "0"


def test_an_insert_post_still_reuses_the_main_job_car_through_the_existing_flow(insert_world):
    from tests.test_car_reservation import insert_data

    response = insert_world.client_for(insert_world.dispatcher).post(
        insert_url(insert_world), data=insert_data(insert_world, car=str(insert_world.car.id))
    )

    assert response.status_code == 302, response.get_data(as_text=True)


# ------------------------------------------------------------ build_picker (หน่วย)


def test_build_picker_refuses_an_unusable_window(picker_world):
    with pytest.raises(ValueError):
        car_timeline.build_picker(picker_world.org, DAY, DAY)
    assert car_timeline.picker_or_hint(picker_world.org, None, DAY)[0] is None
    timeline, hint = car_timeline.picker_or_hint(picker_world.org, DAY, DAY + HOUR)
    assert timeline.picker.window_start == DAY and hint == ""


def test_parse_id_list_keeps_slot_positions_and_drops_garbage():
    one = "0123456789abcdef01234567"
    two = "fedcba987654321012345678"

    assert car_timeline.parse_id_list(f"{one},,{two}") == [one, "", two]
    assert car_timeline.parse_id_list(f"zz,{one},") == ["", one]
    assert car_timeline.parse_id_list(None) == []
    assert len(car_timeline.parse_id_list(",".join([one] * 50))) == car_timeline.PICKER_MAX_SLOTS
