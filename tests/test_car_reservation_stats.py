"""สถิติของระบบจองรถ: dashboard ภาระงานพนักงานขับรถ (ผู้จัดรถและผู้บริหาร) และสรุปงานของ พขร. เอง"""

import datetime
import re

import pytest

from kampan import models

DRIVERS_URL = "/car_reservation/stats/drivers"
SUMMARY_URL = "/car_reservation/tasks/summary"

HOUR = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Stats Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "Stats")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.driver = create_user("Alpha", "Driver")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.other_driver = create_user("Bravo", "Driver")
    assign_user_to_org(s.other_driver, org, roles=["driver"])
    s.org_admin = create_user("OrgAdmin", "Stats")
    assign_user_to_org(s.org_admin, org, roles=["admin"])
    s.managers = {}
    for key in (
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
    ):
        s.managers[key] = create_user(f"M{key.title().replace('_', '')}", "Stats")
        assign_user_to_org(s.managers[key], org, roles=[key])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")

    s.client_for = lambda user: login_as(app.test_client(), user)
    s.url = lambda path, **query: (
        f"{path}?organization_id={org.id}"
        + "".join(f"&{key}={value}" for key, value in query.items())
    )

    def job(driver, departure, hours, status="completed", mileage=None, **extra):
        """งานของ driver ออกเดินทาง departure กลับหลัง hours ชม. (mileage = (กม. ออก, กม. กลับ))"""
        reservation = models.CarReservation(
            organization=org,
            creator=s.requester,
            request_type="domestic",
            province_scope="in_province",
            location="กรุงเทพฯ",
            request_reason="ประชุม",
            departure_datetime=departure,
            return_datetime=departure + hours * HOUR,
            status=status,
            route_snapshot=["supervisor", "dispatcher"],
            current_step=2,
            car=s.car,
            driver=driver,
            **extra,
        )
        if mileage:
            reservation.last_mileage_before, reservation.last_mileage = mileage
        return reservation.save()

    s.job = job
    return s


def rows_of(response):
    """{ชื่อ พขร.: {ชื่อฟิลด์: ค่าข้อความ}} จากแถว data-role=driver-row ของตาราง"""
    html = response.get_data(as_text=True)
    rows = {}
    for row in re.findall(r'<tr[^>]*data-role="driver-row".*?</tr>', html, re.S):
        name = re.search(r'data-field="name">\s*(.*?)\s*<', row, re.S).group(1)
        rows[name] = dict(re.findall(r'data-field="(\w+)">\s*([^<\s]*)\s*<', row))
    return rows


def give_alpha_jobs_in_three_periods(world):
    now = datetime.datetime.now()
    # สัปดาห์นี้: ในเวลา 3 ชม. (ตามเวลากลับของใบขอ) วิ่ง 60 กม.
    world.job(world.driver, now - 2 * DAY, 3, mileage=(100, 160))
    # เดือนนี้: OT 4 ชม. (ตามเวลาเริ่ม/ปิดงานจริง) วิ่ง 40 กม.
    world.job(
        world.driver,
        now - 10 * DAY,
        1,
        mileage=(160, 200),
        is_overtime=True,
        started_at=now - 10 * DAY,
        completed_at=now - 10 * DAY + 4 * HOUR,
    )
    # ปีนี้: ในเวลา 2 ชม. วิ่ง 500 กม.
    world.job(world.driver, now - 60 * DAY, 2, mileage=(200, 700))
    # งานข้างหน้า 1 งาน (active) ไม่นับเป็นงานที่ทำแล้ว
    world.job(world.driver, now + 3 * DAY, 2, status="active")


@pytest.mark.parametrize(
    "period, expected",
    [
        ("week", {"in_hours": "1", "ot": "0", "hours": "3.0", "km": "60"}),
        (None, {"in_hours": "1", "ot": "1", "hours": "7.0", "km": "100"}),
        ("month", {"in_hours": "1", "ot": "1", "hours": "7.0", "km": "100"}),
        ("year", {"in_hours": "2", "ot": "1", "hours": "9.0", "km": "600"}),
    ],
)
def test_dispatcher_sees_each_drivers_workload_for_the_chosen_period(
    world, period, expected
):
    give_alpha_jobs_in_three_periods(world)
    query = {"period": period} if period else {}

    response = world.client_for(world.managers["dispatcher"]).get(
        world.url(DRIVERS_URL, **query)
    )

    assert response.status_code == 200
    rows = rows_of(response)
    assert rows["Alpha Driver"] == {**expected, "upcoming": "1"}
    assert rows["Bravo Driver"] == {
        "in_hours": "0",
        "ot": "0",
        "hours": "0.0",
        "km": "0",
        "upcoming": "0",
    }


def test_driver_filter_narrows_the_table_to_one_driver(world):
    give_alpha_jobs_in_three_periods(world)

    response = world.client_for(world.managers["dispatcher"]).get(
        world.url(DRIVERS_URL, driver=world.other_driver.id)
    )

    assert list(rows_of(response)) == ["Bravo Driver"]


@pytest.mark.parametrize(
    "role", ["dispatcher", "vehicle_unit_head", "strategy_head", "physical_director"]
)
def test_dispatcher_and_executives_may_open_the_driver_dashboard(world, role):
    response = world.client_for(world.managers[role]).get(world.url(DRIVERS_URL))

    assert response.status_code == 200


@pytest.mark.parametrize("who", ["driver", "requester"])
def test_drivers_and_requesters_are_refused_the_driver_dashboard(world, who):
    give_alpha_jobs_in_three_periods(world)

    response = world.client_for(getattr(world, who)).get(world.url(DRIVERS_URL))

    assert response.status_code in (302, 403)
    assert "Alpha Driver" not in response.get_data(as_text=True)


def test_sidebar_offers_the_dashboard_to_the_dispatcher_but_not_to_a_requester(world):
    dashboard_href = f"{DRIVERS_URL}?organization_id={world.org.id}"
    page = world.url("/car_reservation/requests/")

    for_dispatcher = world.client_for(world.managers["dispatcher"]).get(page)
    for_requester = world.client_for(world.requester).get(page)

    assert dashboard_href in for_dispatcher.get_data(as_text=True)
    assert DRIVERS_URL not in for_requester.get_data(as_text=True)


def test_dispatch_page_links_to_the_driver_dashboard(world):
    pending = world.job(world.driver, datetime.datetime.now() + 20 * DAY, 4, status="pending")
    pending.current_step = 1
    pending.save()

    html = (
        world.client_for(world.managers["dispatcher"])
        .get(f"/car_reservation/requests/{pending.id}?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    link = re.search(r'<a href="([^"]*)"[^>]*data-role="workload-dashboard-link"', html)
    assert link.group(1) == f"{DRIVERS_URL}?organization_id={world.org.id}"


def month_start():
    today = datetime.date.today()
    return datetime.datetime(today.year, today.month, 1)


def test_driver_summary_shows_only_their_own_counts_for_the_current_month(world):
    start = month_start()
    # Alpha เดือนนี้: ในเวลา 2 ชม. 30 กม. + OT 3 ชม. 20 กม. = 5.0 ชม. 50 กม.
    world.job(world.driver, start, 2, mileage=(1000, 1030))
    world.job(
        world.driver, start, 1, mileage=(1030, 1050), is_overtime=True,
        started_at=start, completed_at=start + 3 * HOUR,
    )
    # ไม่นับ: เดือนก่อน
    world.job(world.driver, start - DAY, 6, mileage=(0, 400))
    # ของคนขับคนอื่น (ต้องไม่โผล่)
    world.job(world.other_driver, start, 7, mileage=(2000, 2777))

    response = world.client_for(world.driver).get(world.url(SUMMARY_URL))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    figures = dict(re.findall(r'data-stat="(\w+)">\s*([^<\s]*)\s*<', html))
    assert figures == {"in_hours": "1", "ot": "1", "hours": "5.0", "km": "50"}
    assert "777" not in html


@pytest.mark.parametrize("who", ["requester", "org_admin"])
def test_non_drivers_are_refused_the_driver_summary(world, who):
    response = world.client_for(getattr(world, who)).get(world.url(SUMMARY_URL))

    assert response.status_code in (302, 403)


def test_task_list_links_to_the_driver_summary(world):
    html = world.client_for(world.driver).get(world.url("/car_reservation/tasks/")).get_data(as_text=True)

    assert f"{SUMMARY_URL}?organization_id={world.org.id}" in html
