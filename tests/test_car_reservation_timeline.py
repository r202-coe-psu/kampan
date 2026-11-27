"""หน้า "ตารางรถ" ของผู้จัดรถ: สิทธิ์เข้าถึง ตัวกรองใน query string htmx partial popover และเมนู sidebar"""

import datetime
import html
import re
from lxml import html as lxml_html
from urllib.parse import parse_qs, urlparse

import pytest

from kampan import models

BASE = "/car_reservation/timeline/"
CALENDAR = "/car_reservation/calendar/"
HX = {"HX-Request": "true"}

TODAY = datetime.date.today()


def at(day_offset, hour=0, minute=0):
    return datetime.datetime.combine(
        TODAY + datetime.timedelta(days=day_offset), datetime.time(hour, minute)
    )


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Timeline View Org")
    org.enabled_modules = ["car_reservation"]
    org.save()
    other_org = create_org("Timeline Other Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.other_org = other_org
    s.requester = create_user("Requester", "Timeline")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.dispatcher = create_user("Dispatcher", "Timeline")
    assign_user_to_org(s.dispatcher, org, roles=["dispatcher"])
    s.org_admin = create_user("Orgadmin", "Timeline")
    assign_user_to_org(s.org_admin, org, roles=["admin"])
    s.driver = create_user("Driver", "Timeline")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.outsider = create_user("Outsider", "Timeline")
    assign_user_to_org(s.outsider, other_org, roles=["dispatcher", "admin"])
    s.system_admin = create_user("Sysadmin", "Timeline", roles=["admin"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")
    s.van = create_car(org, "ขข 5678", vehicle_type="ตู้")

    s.client_of = lambda user: login_as(app.test_client(), user)
    s.client = s.client_of(s.dispatcher)

    def reservation(departure, return_, car=None, status="active", location="เชียงใหม่", **kwargs):
        organization = kwargs.pop("organization", org)
        return models.CarReservation(
            organization=organization,
            creator=s.requester,
            request_type="domestic",
            province_scope="in_province",
            location=location,
            request_reason="ประชุม",
            departure_datetime=departure,
            return_datetime=return_,
            status=status,
            passenger_number=4,
            assignments=kwargs.pop(
                "assignments", [models.CarAssignment(car=car or s.car, driver=s.driver)]
            ),
        ).save()

    s.reservation = reservation

    def get(params=None, client=None, headers=None, organization=org):
        query = {"organization_id": str(organization.id), **(params or {})}
        return (client or s.client).get(BASE, query_string=query, headers=headers or {})

    s.get = get

    def text(params=None, **kwargs):
        response = get(params, **kwargs)
        assert response.status_code == 200, response.get_data(as_text=True)[:500]
        return response.get_data(as_text=True)

    s.text = text
    return s


def bar_statuses(page):
    return re.findall(r'data-role="bar" data-status="([a-z_]+)"', page)


def links_in(page, role):
    """href ของลิงก์ในแถบนำทางที่ตรงกับ attribute (ถอด HTML entity แล้ว)"""
    return [html.unescape(h) for h in re.findall(role, page)]


def query_of(href):
    return parse_qs(urlparse(href).query)


# ------------------------------------------------------------ access


def test_dispatcher_and_org_admin_can_open_the_timeline(world):
    assert world.get().status_code == 200
    assert world.get(client=world.client_of(world.org_admin)).status_code == 200


@pytest.mark.parametrize("who", ["requester", "driver", "outsider", "system_admin"])
def test_everyone_else_is_denied(world, who):
    # outsider ถือ role ผู้จัดรถในองค์กรอื่น และ system admin ไม่ได้ถือ role ในองค์กรนี้ ก็ยังเปิดไม่ได้
    response = world.get(client=world.client_of(getattr(world, who)))

    # หน้า 403 ของระบบพากลับหน้าอื่น (302) แต่ต้องไม่ได้ตารางไปด้วย
    assert response.status_code in (302, 403)
    assert "data-tl-grid" not in response.get_data(as_text=True)


def test_a_logged_out_visitor_is_sent_to_login(world, app):
    response = app.test_client().get(BASE, query_string={"organization_id": str(world.org.id)})

    assert response.status_code in (302, 403)


def test_the_organization_with_the_module_disabled_has_no_timeline(world):
    world.org.enabled_modules = []
    world.org.save()

    assert world.get().status_code == 404


def test_the_page_is_scoped_to_the_organization_in_the_query(world, create_car):
    create_car(world.other_org, "จจ 9999", vehicle_type="เก๋ง")
    world.reservation(at(0, 12), at(0, 16), organization=world.other_org, car=world.car)

    page = world.text()

    assert "กก 1234" in page and "ขข 5678" in page
    assert "จจ 9999" not in page
    assert bar_statuses(page) == []


# ------------------------------------------------------------ sidebar


@pytest.mark.parametrize(
    "who, visible",
    [("dispatcher", True), ("org_admin", True), ("requester", False), ("driver", False)],
)
def test_the_sidebar_item_shows_only_to_dispatchers_and_admins(world, who, visible):
    client = world.client_of(getattr(world, who))

    page = client.get(CALENDAR, query_string={"organization_id": str(world.org.id)}).get_data(
        as_text=True
    )
    link = f"{BASE}?organization_id={world.org.id}"

    assert ("ตารางรถ" in page and link in html.unescape(page)) is visible


def test_the_sidebar_item_is_active_on_the_timeline_page(world):
    page = world.text()

    assert re.search(r'class="menu-active"[^>]*aria-current="page"[^>]*\s+href="[^"]*timeline', page)


# ------------------------------------------------------------ content


def test_cars_are_grouped_by_type_with_plate_seats_and_count(world):
    models.vehicles.Car.objects(id=world.van.id).update(set__seat_count=12)

    page = world.text()

    assert page.index("รถตู้") < page.index("รถเก๋ง")
    assert 'data-group="ตู้"' in page and 'data-group="เก๋ง"' in page
    assert "12 ที่นั่ง" in page
    assert re.search(r'data-role="group-count">1<', page)
    assert page.count('data-role="car-row"') == 2
    assert 'data-role="now-line"' in page


def test_a_trip_today_is_drawn_with_its_status_tone_and_geometry(world):
    world.reservation(at(0, 12), at(0, 16), status="pending")

    page = world.text({"days": 1})

    assert bar_statuses(page) == ["pending"]
    assert "tl-st-pending" in page
    assert "left: min(50.0%" in page
    assert re.search(r"width: 16\.666\d*%", page)


def test_cancelled_and_denied_stay_hidden_until_the_status_filter_is_set(world):
    world.reservation(at(0, 8), at(0, 9), status="cancelled", car=world.car)
    world.reservation(at(0, 10), at(0, 11), status="denied", car=world.van)

    assert bar_statuses(world.text()) == []
    shown = world.text({"status": ["cancelled", "denied"]})
    assert sorted(bar_statuses(shown)) == ["cancelled", "denied"]


def test_the_popover_summarises_the_request_and_links_to_its_detail_page(world):
    reservation = world.reservation(
        at(0, 8, 30), at(1, 17), location="สงขลา <b>x</b>", car=world.car
    )

    page = world.text()

    assert f"popovertarget=\"tl-pop-{reservation.id}-" in page
    assert 'data-role="bar-popover"' in page
    detail = f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    assert detail in html.unescape(page)
    assert "Requester Timeline" in page and "Driver Timeline" in page
    assert "4 คน" in page
    assert "อนุมัติแล้ว" in page
    # ข้อความของผู้ใช้ถูก escape
    assert "สงขลา <b>x</b>" not in page
    assert "สงขลา &lt;b&gt;x&lt;/b&gt;" in page


def test_the_overtime_badge_shows_in_the_popover(world):
    world.reservation(
        at(0, 8),
        at(0, 17),
        assignments=[models.CarAssignment(car=world.car, driver=world.driver, is_overtime=True)],
    )

    assert 'data-role="overtime-badge"' in world.text()


def test_a_two_car_request_shows_a_bar_in_each_cars_row(world):
    world.reservation(
        at(0, 8),
        at(0, 17),
        assignments=[
            models.CarAssignment(car=world.car, driver=world.driver),
            models.CarAssignment(car=world.van, driver=world.org_admin),
        ],
    )

    assert bar_statuses(world.text()) == ["active", "active"]


def test_the_free_during_filter_hides_an_occupied_car(world):
    world.reservation(at(1, 8), at(1, 12), car=world.car)
    window = {
        "free_from": at(1, 9).strftime("%Y-%m-%dT%H:%M"),
        "free_to": at(1, 10).strftime("%Y-%m-%dT%H:%M"),
    }

    page = world.text(window)

    assert "กก 1234" not in page and "ขข 5678" in page


def test_an_empty_result_explains_itself(world):
    page = world.text({"q": "ไม่มีทะเบียนนี้"})

    assert "ไม่พบรถที่ตรงกับตัวกรอง" in page
    assert 'data-role="car-row"' not in page


# ------------------------------------------------------------ htmx partial


def test_an_htmx_request_gets_only_the_grid_and_the_swapped_nav(world):
    world.reservation(at(0, 8), at(0, 17))

    response = world.get(headers=HX)
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<html" not in page and "<body" not in page
    assert "data-tl-grid" in page and 'data-role="bar"' in page
    # แถบนำทางตามมาด้วย hx-swap-oob เพื่อให้ปุ่ม ← → ตรงกับช่วงใหม่
    assert 'id="timeline-nav" hx-swap-oob="true"' in page
    assert "sidebar" not in page


def test_a_normal_request_gets_the_full_page(world):
    page = world.text()

    assert "<html" in page
    assert 'id="timeline-grid"' in page and 'hx-push-url="true"' in page
    assert "hx-swap-oob" not in page


def test_an_htmx_history_restore_gets_the_full_page(world):
    page = world.get(headers={**HX, "HX-History-Restore-Request": "true"}).get_data(as_text=True)

    assert "<html" in page


def test_the_partial_is_denied_to_a_plain_requester_too(world):
    response = world.get(client=world.client_of(world.requester), headers=HX)

    assert response.status_code in (302, 403)
    assert "data-tl-grid" not in response.get_data(as_text=True)


# ------------------------------------------------------------ query string


def test_the_filters_round_trip_through_the_query_string(world):
    params = {
        "start": (TODAY + datetime.timedelta(days=3)).isoformat(),
        "days": "7",
        "vehicle_type": ["ตู้"],
        "q": "ขข",
        "driver": str(world.driver.id),
        "status": ["pending", "cancelled"],
        "free_from": at(5, 8).strftime("%Y-%m-%dT%H:%M"),
        "free_to": at(5, 17).strftime("%Y-%m-%dT%H:%M"),
    }
    world.reservation(at(4, 8), at(4, 12), car=world.van, status="pending")
    world.reservation(at(4, 8), at(4, 12), car=world.van, status="cancelled")

    page = world.text(params)

    assert re.search(r'name="q"[^>]*value="ขข"', page)
    assert re.search(r'name="vehicle_type" value="ตู้"\s+checked', page)
    assert not re.search(r'name="vehicle_type" value="เก๋ง"\s+checked', page)
    assert re.search(r'name="status" value="pending"\s+checked', page)
    assert re.search(r'name="status" value="cancelled"\s+checked', page)
    assert not re.search(r'name="status" value="active"\s+checked', page)
    assert f'<option selected value="{world.driver.id}">' in page
    # ว่างช่วงแสดงด้วยปฏิทิน (วันที่ ISO ใน input ซ่อน) + ตัวเลือกเวลา ไม่ใช่ datetime-local ของเบราว์เซอร์
    assert f'name="free_from_date" class="w-full cursor-pointer input validator "' in page or 'name="free_from_date"' in page
    assert f'value="{at(5, 8):%Y-%m-%d}"' in page and 'value="08:00"' in page and 'value="17:00"' in page
    assert 'type="datetime-local"' not in page and "datetime-local" not in page.split("data-role=\"timeline-filter\"")[1].split("</form>")[0]
    assert 'name="start"' in page and f'value="{params["start"]}"' in page
    assert re.search(r'name="days" value="7"', page)
    assert sorted(bar_statuses(page)) == ["cancelled", "pending"]


def test_bars_use_the_daisyui_tooltip_component_not_a_native_title(world):
    world.reservation(at(1, 9), at(1, 12), location="ภูเก็ต", status="pending")
    doc = lxml_html.fromstring(world.text())

    (tip,) = doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' tooltip ')][contains(concat(' ', normalize-space(@class), ' '), ' tl-tip ')]")
    (content,) = tip.xpath("./div[contains(@class, 'tooltip-content')]")
    text = " ".join(content.text_content().split())
    assert "ภูเก็ต" in text and "พขร. Driver Timeline" in text and "รออนุมัติ" in text
    (bar,) = tip.xpath("./button[@data-role='bar']")
    assert bar.get("title") is None and "ภูเก็ต" in bar.get("aria-label")


def test_the_free_window_uses_the_calendar_and_time_picker_components(world):
    page = world.text({"free_from_date": at(5).strftime("%Y-%m-%d"), "free_from_time": "08:00",
                       "free_to_date": at(5).strftime("%Y-%m-%d"), "free_to_time": "17:00"})
    doc = lxml_html.fromstring(page)

    for name in ("free_from_date", "free_to_date"):
        # date_field: ปฏิทิน cally (ปุ่ม + popover) ค่า ISO อยู่ใน input ซ่อน
        (hidden,) = doc.xpath(f"//input[@type='hidden'][@name='{name}']")
        assert hidden.get("value") == at(5).strftime("%Y-%m-%d")
        assert doc.xpath(f"//*[@data-date-picker][@data-input-id='{name}']//calendar-date")
    assert doc.xpath("//input[@name='free_from_time'][@value='08:00']")
    assert doc.xpath("//input[@name='free_to_time'][@value='17:00']")
    assert not doc.xpath("//input[@type='datetime-local']")


def test_prev_next_and_day_links_keep_every_filter(world):
    start = TODAY + datetime.timedelta(days=3)
    page = world.text(
        {
            "start": start.isoformat(),
            "days": "7",
            "vehicle_type": ["ตู้", "บัส"],
            "q": "ขข",
            "status": ["pending"],
        }
    )
    nav = page[page.index('id="timeline-nav"') :]
    hrefs = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', nav)]
    prev_href, today_href, next_href = hrefs[:3]

    assert query_of(prev_href)["start"] == [(start - datetime.timedelta(days=7)).isoformat()]
    assert query_of(next_href)["start"] == [(start + datetime.timedelta(days=7)).isoformat()]
    for href in (prev_href, next_href, today_href):
        query = query_of(href)
        assert query["days"] == ["7"]
        assert query["q"] == ["ขข"]
        assert query["status"] == ["pending"]
        assert sorted(query["vehicle_type"]) == sorted(["บัส", "ตู้"])
        assert query["organization_id"] == [str(world.org.id)]
    # "วันนี้" กลับมาวันนี้ จึงไม่มี start
    assert "start" not in query_of(today_href)
    # ปุ่มจำนวนวันเปลี่ยนแค่ days
    day_links = {
        int(days): query_of(html.unescape(href))
        for days, href in re.findall(r'data-days="(\d+)"[^>]*\s+href="([^"]+)"', nav)
    }
    assert set(day_links) == {1, 7, 14, 30}
    assert day_links[30]["days"] == ["30"] and day_links[30]["q"] == ["ขข"]
    assert day_links[30]["start"] == [start.isoformat()]


def test_the_range_label_and_day_columns_follow_start_and_days(world):
    page = world.text({"start": "2031-01-10", "days": "7"})

    assert page.count('class="tl-daycell ') == 7
    assert 'data-date="2031-01-10"' in page and 'data-date="2031-01-16"' in page
    assert "10 ม.ค. 2574" in page and "16 ม.ค. 2574" in page
    # 2031 ไม่ใช่ปีปัจจุบัน จึงไม่มีเส้นเวลาปัจจุบัน
    assert 'data-role="now-line"' not in page


def test_holidays_and_weekends_are_flagged_in_the_header(world):
    models.CarHoliday(
        organization=world.org, date=datetime.date(2031, 1, 13), name="วันครู <i>"
    ).save()

    page = world.text({"start": "2031-01-10", "days": "7"})

    assert page.count("is-weekend") >= 4  # เสาร์-อาทิตย์ทั้งหัวและพื้นหลัง
    assert 'title="วันครู &lt;i&gt;"' in page


@pytest.mark.parametrize(
    "params",
    [
        {"start": "not-a-date"},
        {"start": "0001-01-01"},
        {"start": "9999-12-31", "days": "30"},
        {"days": "abc"},
        {"days": "-1"},
        {"days": "99999999999999999999"},
        {"vehicle_type": ["รถไฟ", ""], "status": ["bogus"]},
        {"driver": "<script>alert(1)</script>"},
        {"driver": "5f1d7f3b8f1b2c3d4e5f6a7b"},
        {"free_from": "garbage", "free_to": "also garbage"},
        {"free_from": "2031-01-02T10:00"},
        {"free_from": "2031-01-02T10:00", "free_to": "2031-01-02T09:00"},
        {"q": "x" * 5000},
        {"q": "(unclosed[regex"},
    ],
)
def test_garbage_query_values_never_cause_an_error(world, params):
    world.reservation(at(0, 8), at(0, 9))

    assert world.get(params).status_code == 200
    assert world.get(params, headers=HX).status_code == 200


def test_an_inverted_free_window_shows_a_message_and_filters_nothing(world):
    page = world.text({"free_from": "2031-01-02T10:00", "free_to": "2031-01-02T09:00"})

    assert 'data-role="free-error"' in page
    assert "กก 1234" in page and "ขข 5678" in page


def test_an_unknown_driver_id_is_ignored_not_an_empty_table(world):
    page = world.text({"driver": "5f1d7f3b8f1b2c3d4e5f6a7b"})

    assert "กก 1234" in page


def test_the_driver_filter_keeps_only_that_drivers_cars(world):
    world.reservation(at(0, 8), at(0, 9), car=world.car)
    other = world.reservation(
        at(0, 8),
        at(0, 9),
        car=world.van,
        assignments=[models.CarAssignment(car=world.van, driver=world.org_admin)],
    )

    page = world.text({"driver": str(world.driver.id)})

    assert "กก 1234" in page and "ขข 5678" not in page
    assert str(other.id) not in page
