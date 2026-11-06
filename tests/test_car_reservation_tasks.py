"""งานของพนักงานขับรถ (ระบบจองรถ): พขร. เห็นเฉพาะงานของตัวเอง และปิดงานพร้อมเลขไมล์/น้ำมัน/ค่าใช้จ่าย"""

import datetime

import pytest

from kampan import models

BASE = "/car_reservation/tasks"


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
