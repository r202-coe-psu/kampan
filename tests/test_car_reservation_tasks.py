"""งานของพนักงานขับรถ (ระบบจองรถ): พขร. เห็นเฉพาะงานของตัวเอง และปิดงานพร้อมเลขไมล์/น้ำมัน/ค่าใช้จ่าย"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from kampan import models
from kampan.web import redis_rq

BASE = "/car_reservation/tasks"


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """ปิดงานแล้วระบบส่งอีเมลเข้าคิว: กันการต่อ Redis จริง"""
    with patch.object(redis_rq.redis_queue, "queue", MagicMock(), create=True):
        yield


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Tasks Org")
    org.enabled_modules = ["car_reservation"]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "Tasks")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.driver = create_user("DriverA", "One")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.other_driver = create_user("DriverB", "Two")
    assign_user_to_org(s.other_driver, org, roles=["driver"])
    s.org_admin = create_user("Admin", "Tasks")
    assign_user_to_org(s.org_admin, org, roles=["admin"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")
    s.car.last_mileage = 10000
    s.car.save()

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for
    s.list_url = f"{BASE}/?organization_id={org.id}"

    def reservation(
        driver=None,
        status="active",
        location="กรุงเทพฯ",
        departure=datetime.datetime(2031, 1, 10, 8, 30),
        car=None,
    ):
        return models.CarReservation(
            organization=org,
            creator=s.requester,
            requester_unit="คณะวิศวกรรมศาสตร์",
            phone="081-234-5678",
            request_type="domestic",
            province_scope="in_province",
            location=location,
            request_reason="ประชุม",
            departure_datetime=departure,
            return_datetime=departure + datetime.timedelta(hours=8),
            pickup_place="หน้าอาคารอธิการบดี",
            pickup_time="07:30",
            status=status,
            route_snapshot=["supervisor", "dispatcher"],
            current_step=2,
            car=car or s.car,
            driver=driver or s.driver,
        ).save()

    s.reservation = reservation
    return s


def test_driver_task_list_shows_only_the_drivers_own_tasks(world):
    world.reservation(location="ที่ของฉัน")
    world.reservation(driver=world.other_driver, location="ที่ของคนอื่น")

    response = world.client_for(world.driver).get(world.list_url)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ที่ของฉัน" in html
    assert "ที่ของคนอื่น" not in html


@pytest.mark.parametrize("who", ["requester", "org_admin"])
def test_only_drivers_may_open_the_task_list(world, who):
    response = world.client_for(getattr(world, who)).get(world.list_url)

    assert response.status_code in (302, 403)
    assert "งานที่ต้องไป" not in response.get_data(as_text=True)


def test_task_card_shows_what_the_driver_needs_for_the_trip(world):
    world.reservation(location="เชียงใหม่")

    html = world.client_for(world.driver).get(world.list_url).get_data(as_text=True)
    # ขอบเขตเฉพาะส่วนงานที่ต้องไป (ทุกหน้ามี modal เลือกประเภทใบขอที่มีชื่อประเภทอยู่แล้ว)
    html = html.split('data-role="active-tasks"')[1].split('data-role="completed-tasks"')[0]

    for expected in (
        "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ",  # ประเภท
        "เชียงใหม่",  # ปลายทาง
        "10/01/2031 08:30",  # ออกเดินทาง
        "10/01/2031 16:30",  # กลับ
        "หน้าอาคารอธิการบดี",  # จุดรับ
        "07:30",  # เวลารับ
        "081-234-5678",  # เบอร์ผู้ขอ
        "กก 1234",  # ทะเบียน
    ):
        assert expected in html


def test_active_tasks_are_listed_upcoming_first_then_recent_completed(world):
    world.reservation(
        location="ไกลสุด", departure=datetime.datetime(2031, 3, 1, 8, 0)
    )
    world.reservation(location="ใกล้สุด", departure=datetime.datetime(2031, 1, 5, 8, 0))
    world.reservation(
        location="เสร็จแล้ว", status="completed", departure=datetime.datetime(2030, 12, 1, 8, 0)
    )

    html = world.client_for(world.driver).get(world.list_url).get_data(as_text=True)

    assert html.index("ใกล้สุด") < html.index("ไกลสุด") < html.index("เสร็จแล้ว")


def close_data(**overrides):
    data = {
        "mileage_out": "10000",
        "mileage_in": "10250",
        "fuel_liters": "20.5",
        "expense_case": "fleet_card",
        "cost_baht": "1200.50",
    }
    data.update(overrides)
    return data


def close_url(world, reservation):
    return f"{BASE}/{reservation.id}/close?organization_id={world.org.id}"


def close(world, reservation, user=None, **overrides):
    return world.client_for(user or world.driver).post(
        close_url(world, reservation), data=close_data(**overrides)
    )


def test_driver_closes_an_active_task_and_the_trip_report_is_recorded(world):
    reservation = world.reservation()

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert reservation.last_mileage_before == 10000
    assert reservation.last_mileage == 10250
    assert float(reservation.fuel_liters) == 20.5
    assert reservation.expense_case == "fleet_card"
    assert float(reservation.cost_baht) == 1200.50
    assert reservation.completed_at is not None


def test_closing_sets_the_cars_mileage_to_the_return_reading(world):
    close(world, world.reservation())

    world.car.reload()
    assert world.car.last_mileage == 10250


def test_closing_is_audited_as_completed_by_the_driver(world):
    reservation = world.reservation()

    close(world, reservation)

    reservation.reload()
    last = reservation.audit_logs[-1]
    assert (last.action, last.actor) == ("completed", world.driver)


def test_closing_shows_a_success_toast_on_the_task_list(world):
    reservation = world.reservation()
    client = world.client_for(world.driver)

    response = client.post(
        close_url(world, reservation), data=close_data(), follow_redirects=True
    )

    assert "ปิดงานเรียบร้อยแล้ว" in response.get_data(as_text=True)


def test_return_mileage_below_departure_mileage_is_refused(world):
    reservation = world.reservation()

    response = close(world, reservation, mileage_out="10000", mileage_in="9999")

    reservation.reload()
    world.car.reload()
    assert response.status_code == 200
    assert "เลข กม. กลับต้องไม่น้อยกว่าเลข กม. ออก" in response.get_data(as_text=True)
    assert reservation.status == "active"
    assert world.car.last_mileage == 10000


def test_return_mileage_is_required(world):
    reservation = world.reservation()

    response = close(world, reservation, mileage_in="")

    reservation.reload()
    assert response.status_code == 200
    assert reservation.status == "active"


def test_another_driver_cannot_close_the_task(world):
    reservation = world.reservation()

    response = close(world, reservation, user=world.other_driver)

    reservation.reload()
    assert response.status_code in (302, 403)
    assert reservation.status == "active"
    assert reservation.last_mileage is None


@pytest.mark.parametrize("status", ["pending", "completed", "cancelled"])
def test_only_an_active_task_can_be_closed(world, status):
    reservation = world.reservation(status=status)

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code in (302, 403)
    assert reservation.status == status
    assert reservation.last_mileage is None


def test_close_form_is_prefilled_with_the_cars_last_mileage(world):
    reservation = world.reservation()

    response = world.client_for(world.driver).get(close_url(world, reservation))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="mileage_out"' in html
    assert 'value="10000"' in html


def test_a_task_waits_for_the_earlier_active_task_of_the_same_car(world):
    world.reservation(location="งานแรก", departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(
        location="งานหลัง", departure=datetime.datetime(2031, 1, 9, 8, 0)
    )

    response = close(world, later)

    later.reload()
    assert later.status == "active"
    assert "งานแรก" in response.get_data(as_text=True).split("ต้องปิดงาน")[1]


def test_closing_the_earlier_task_first_unblocks_the_later_one(world):
    earlier = world.reservation(departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))

    close(world, earlier)
    close(world, later, mileage_out="10250", mileage_in="10300")

    later.reload()
    assert later.status == "completed"


def test_an_earlier_task_of_another_car_does_not_block(world, create_car):
    other_car = create_car(world.org, "ขข 5678")
    world.reservation(
        departure=datetime.datetime(2031, 1, 5, 8, 0), car=other_car
    )
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))

    close(world, later)

    later.reload()
    assert later.status == "completed"


def start_url(world, reservation):
    return f"{BASE}/{reservation.id}/start?organization_id={world.org.id}"


def test_driver_starts_a_task_and_the_start_is_audited(world):
    reservation = world.reservation()

    response = world.client_for(world.driver).post(start_url(world, reservation))

    reservation.reload()
    assert response.status_code == 302
    assert reservation.started_at is not None
    assert reservation.status == "active"
    last = reservation.audit_logs[-1]
    assert (last.action, last.actor) == ("started", world.driver)
    assert last.get_action_display() == "เริ่มงาน"


def test_pressing_start_again_keeps_the_first_start_time(world):
    reservation = world.reservation()
    client = world.client_for(world.driver)
    client.post(start_url(world, reservation))
    reservation.reload()
    first = reservation.started_at

    client.post(start_url(world, reservation))

    reservation.reload()
    assert reservation.started_at == first
    assert [log.action for log in reservation.audit_logs].count("started") == 1


def test_another_driver_cannot_start_the_task(world):
    reservation = world.reservation()

    response = world.client_for(world.other_driver).post(start_url(world, reservation))

    reservation.reload()
    assert response.status_code in (302, 403)
    assert reservation.started_at is None


def test_task_card_offers_start_before_start_and_close_after(world):
    reservation = world.reservation()
    client = world.client_for(world.driver)

    before = client.get(world.list_url).get_data(as_text=True)
    client.post(start_url(world, reservation))
    after = client.get(world.list_url).get_data(as_text=True)

    assert f"/{reservation.id}/start" in before
    assert f"/{reservation.id}/start" not in after
    assert f"/{reservation.id}/close" in after


def test_driver_can_still_close_a_task_that_was_never_started(world):
    reservation = world.reservation()

    close(world, reservation)

    reservation.reload()
    assert reservation.status == "completed"
    assert reservation.started_at is None


def test_task_list_offers_close_only_for_tasks_that_can_be_closed_now(world):
    earlier = world.reservation(departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))
    done = world.reservation(status="completed")
    client = world.client_for(world.driver)
    client.post(start_url(world, earlier))

    html = client.get(world.list_url).get_data(as_text=True)

    assert f"/{earlier.id}/close" in html
    assert f"/{later.id}/close" not in html
    assert f"/{done.id}/close" not in html
    assert "ปิดงานก่อนหน้าให้เสร็จก่อน" in html


def test_request_detail_shows_the_trip_report_once_completed(world):
    reservation = world.reservation()
    close(world, reservation, mileage_out="9000", mileage_in="10500")

    response = world.client_for(world.requester).get(
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    )

    report = response.get_data(as_text=True).split('data-role="trip-report"')[1]
    for expected in (
        "9000",  # กม. ออก
        "10500",  # กม. กลับ
        "1500",  # ระยะทางรวม
        "20.50",  # น้ำมัน (ลิตร)
        "เติมฟลีตการ์ดน้ำมัน",  # กรณีค่าใช้จ่าย
        "1,200.50",  # เป็นเงิน
    ):
        assert expected in report


def test_request_detail_has_no_trip_report_before_the_task_is_closed(world):
    reservation = world.reservation()

    response = world.client_for(world.requester).get(
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    )

    assert 'data-role="trip-report"' not in response.get_data(as_text=True)


def test_a_driver_opening_the_car_reservation_home_lands_on_the_task_list(world):
    home = f"/car_reservation/requests/?organization_id={world.org.id}"

    response = world.client_for(world.driver).get(home)

    assert response.status_code == 302
    assert "/car_reservation/tasks" in response.headers["Location"]


def test_a_requester_opening_the_car_reservation_home_stays_there(world):
    home = f"/car_reservation/requests/?organization_id={world.org.id}"

    response = world.client_for(world.requester).get(home)

    assert response.status_code == 200


def test_a_driver_who_is_also_a_dispatcher_keeps_the_home(world):
    both = world.driver
    membership = models.OrganizationUserRole.objects(
        organization=world.org, user=both
    ).get()
    membership.roles = ["driver", "dispatcher"]
    membership.save()
    home = f"/car_reservation/requests/?organization_id={world.org.id}"

    response = world.client_for(both).get(home)

    assert response.status_code == 200


def test_task_menu_is_in_the_sidebar_only_for_drivers(world):
    home = f"/car_reservation/requests/?organization_id={world.org.id}"

    as_driver = (
        world.client_for(world.driver)
        .get(home, follow_redirects=True)
        .get_data(as_text=True)
    )
    as_staff = world.client_for(world.requester).get(home).get_data(as_text=True)
    as_admin = world.client_for(world.org_admin).get(home).get_data(as_text=True)

    assert f"{BASE}/?organization_id={world.org.id}" in as_driver
    assert f"{BASE}/" not in as_staff
    assert f"{BASE}/" not in as_admin
