"""งานของพนักงานขับรถ (ระบบจองรถ): พขร. เห็นเฉพาะงานของตัวเอง และปิดงานพร้อมเลขไมล์/น้ำมัน/ค่าใช้จ่าย"""

import base64
import datetime
import re
import io
from unittest.mock import MagicMock, patch

import pytest

from kampan import models, utils
from kampan.utils import notifications
from kampan.web import redis_rq

BASE = "/car_reservation/tasks"

# PNG 1x1 พิกเซลของจริง (ผ่านการตรวจเป็นภาพ JPEG/PNG)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """ปิดงานแล้วระบบส่งอีเมลเข้าคิว: กันการต่อ Redis จริง (คืน mock ไว้ตรวจ job ที่ส่งเข้าคิว)"""
    mock_q = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", mock_q, create=True):
        yield mock_q


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
            assignments=[
                models.CarAssignment(car=car or s.car, driver=driver or s.driver)
            ],
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
        "mileage_photo_in": (io.BytesIO(PNG_BYTES), "in.png"),
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def aid(reservation, assignment=None):
    """assignment_id ของชุดที่ระบุ (ไม่ระบุ = ชุดแรก)"""
    return (assignment or reservation.first_assignment).assignment_id


def close_url(world, reservation, assignment=None):
    return (
        f"{BASE}/{reservation.id}/close/{aid(reservation, assignment)}"
        f"?organization_id={world.org.id}"
    )


def close(world, reservation, user=None, remote_addr=None, headers=None, **overrides):
    return world.client_for(user or world.driver).post(
        close_url(world, reservation),
        data=close_data(**overrides),
        environ_base={"REMOTE_ADDR": remote_addr} if remote_addr else {},
        headers=headers or {},
    )


def test_driver_closes_an_active_task_and_the_trip_report_is_recorded(world):
    reservation = world.reservation()

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert reservation.first_assignment.last_mileage_before == 10000
    assert reservation.first_assignment.last_mileage == 10250
    assert float(reservation.first_assignment.fuel_liters) == 20.5
    assert reservation.first_assignment.expense_case == "fleet_card"
    assert float(reservation.first_assignment.cost_baht) == 1200.50
    assert reservation.first_assignment.completed_at is not None


def test_closing_sets_the_cars_mileage_to_the_return_reading(world):
    close(world, world.reservation())

    world.car.reload()
    assert world.car.last_mileage == 10250


def test_closing_logs_the_trip_report_as_changes(world):
    reservation = world.reservation()

    close(world, reservation)

    reservation.reload()
    changes = {
        change.label: (change.old, change.new)
        for change in reservation.audit_logs[-1].changes
    }
    assert changes == {
        "เลข กม. ออก": ("-", "10000"),
        "เลข กม. กลับ": ("-", "10250"),
        "น้ำมัน (ลิตร)": ("-", "20.50"),
        "กรณีค่าใช้จ่าย": ("-", "เติมฟลีตการ์ดน้ำมัน"),
        "เป็นเงิน (บาท)": ("-", "1,200.50"),
    }


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


def test_an_absurd_return_mileage_is_refused_and_never_reaches_the_car(world):
    reservation = world.reservation()

    response = close(world, reservation, mileage_out="10000", mileage_in=str(10**15))

    reservation.reload()
    world.car.reload()
    assert response.status_code == 200
    assert reservation.status == "active"
    assert world.car.last_mileage < 10**15


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
    assert reservation.first_assignment.last_mileage is None


@pytest.mark.parametrize("status", ["pending", "completed", "cancelled"])
def test_only_an_active_task_can_be_closed(world, status):
    reservation = world.reservation(status=status)

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code in (302, 403)
    assert reservation.status == status
    assert reservation.first_assignment.last_mileage is None


def test_close_form_is_prefilled_with_the_cars_last_mileage(world):
    reservation = world.reservation()

    response = world.client_for(world.driver).get(close_url(world, reservation))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'name="mileage_out"' in html
    assert 'value="10000"' in html


def test_a_later_task_can_close_while_an_earlier_one_of_the_same_car_is_still_open(world):
    """คนขับอีกคนลืมปิดงานก่อนหน้า ต้องไม่ทำให้งานหลังปิดไม่ได้"""
    earlier = world.reservation(departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))

    response = close(world, later, mileage_out="10300", mileage_in="10400")

    later.reload()
    earlier.reload()
    assert response.status_code == 302
    assert later.status == "completed"
    assert earlier.status == "active"


def test_closing_an_old_task_late_does_not_wind_the_car_mileage_back(world):
    earlier = world.reservation(departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))
    close(world, later, mileage_out="10300", mileage_in="10400")

    # งานเก่ามาปิดทีหลัง ฟอร์มตั้งต้นด้วยเลขไมล์สูงสุดของรถ คนขับแก้เป็นเลขจริงได้
    form = world.client_for(world.driver).get(close_url(world, earlier)).get_data(as_text=True)
    assert 'value="10400"' in form
    close(world, earlier, mileage_out="10000", mileage_in="10250")

    earlier.reload()
    world.car.reload()
    assert (earlier.first_assignment.last_mileage_before, earlier.first_assignment.last_mileage) == (10000, 10250)
    assert world.car.last_mileage == 10400


def test_an_earlier_task_of_another_car_does_not_block(world, create_car):
    other_car = create_car(world.org, "ขข 5678")
    world.reservation(
        departure=datetime.datetime(2031, 1, 5, 8, 0), car=other_car
    )
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))

    close(world, later)

    later.reload()
    assert later.status == "completed"


def start_url(world, reservation, assignment=None):
    return (
        f"{BASE}/{reservation.id}/start/{aid(reservation, assignment)}"
        f"?organization_id={world.org.id}"
    )


def test_driver_starts_a_task_and_the_start_is_audited(world):
    reservation = world.reservation()

    response = world.client_for(world.driver).post(start_url(world, reservation))

    reservation.reload()
    assert response.status_code == 302
    assert reservation.first_assignment.started_at is not None
    assert reservation.status == "active"
    last = reservation.audit_logs[-1]
    assert (last.action, last.actor) == ("started", world.driver)
    assert last.get_action_display() == "เริ่มงาน"


def test_starting_a_task_shows_a_success_toast_on_the_task_list(world):
    reservation = world.reservation(location="ศาลากลางสงขลา")
    client = world.client_for(world.driver)

    response = client.post(start_url(world, reservation))
    page = client.get(response.headers["Location"]).get_data(as_text=True)

    toast = re.search(r'<div[^>]*data-toast-category="success"[^>]*>(.*?)</div>', page, re.S)
    assert toast and "เริ่มงาน ศาลากลางสงขลา แล้ว" in toast.group(1)


def test_pressing_start_again_keeps_the_first_start_time(world):
    reservation = world.reservation()
    client = world.client_for(world.driver)
    client.post(start_url(world, reservation))
    reservation.reload()
    first = reservation.first_assignment.started_at

    client.post(start_url(world, reservation))

    reservation.reload()
    assert reservation.first_assignment.started_at == first
    assert [log.action for log in reservation.audit_logs].count("started") == 1


def test_another_driver_cannot_start_the_task(world):
    reservation = world.reservation()

    response = world.client_for(world.other_driver).post(start_url(world, reservation))

    reservation.reload()
    assert response.status_code in (302, 403)
    assert reservation.first_assignment.started_at is None


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
    assert reservation.first_assignment.started_at is None


def test_task_list_offers_close_only_for_tasks_that_can_be_closed_now(world):
    earlier = world.reservation(departure=datetime.datetime(2031, 1, 5, 8, 0))
    later = world.reservation(departure=datetime.datetime(2031, 1, 9, 8, 0))
    done = world.reservation(status="completed")
    client = world.client_for(world.driver)
    client.post(start_url(world, earlier))

    html = client.get(world.list_url).get_data(as_text=True)

    assert f"/{earlier.id}/close" in html
    # งานที่ยังไม่กดเริ่มงานต้องเริ่มก่อน ไม่ได้รอให้งานก่อนหน้าของรถปิด
    assert f"/{later.id}/close" not in html
    assert f"/{later.id}/start" in html
    assert f"/{done.id}/close" not in html
    assert 'data-role="blocked-by"' not in html


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


# ---- ปิดงานนอกมหาวิทยาลัย: ตรวจ IP ผู้ปิดงานกับช่วง IP ของมหาวิทยาลัย ----


@pytest.mark.parametrize(
    "ip, networks, expected",
    [
        ("10.1.2.3", ["10.0.0.0/8"], True),
        ("11.1.2.3", ["10.0.0.0/8"], False),
        ("192.168.1.5", ["10.0.0.0/8", "192.168.1.0/24"], True),
        ("192.168.2.5", ["10.0.0.0/8", "192.168.1.0/24"], False),
        ("2001:db8::1", ["2001:db8::/32"], True),
        ("2001:db9::1", ["2001:db8::/32"], False),
        ("2001:db8::1", ["10.0.0.0/8"], False),
        ("10.1.2.3", [], False),
        ("not-an-ip", ["10.0.0.0/8"], False),
        ("", ["10.0.0.0/8"], False),
        (None, ["10.0.0.0/8"], False),
        ("10.1.2.3", ["garbage", "10.0.0.0/8"], True),
        ("10.1.2.3", ["garbage"], False),
    ],
)
def test_ip_in_networks_matches_ipv4_and_ipv6_and_rejects_bad_input(
    ip, networks, expected
):
    from kampan.utils import campus_network

    assert campus_network.ip_in_networks(ip, networks) is expected


SETTINGS_URL = "/car_reservation/settings"


def save_campus_networks(world, text):
    return world.client_for(world.org_admin).post(
        f"{SETTINGS_URL}?organization_id={world.org.id}",
        data={
            "car_reservation_contact_phone": "",
            "car_reservation_campus_networks": text,
        },
    )


def test_org_admin_saves_campus_ip_ranges_one_per_line(world):
    response = save_campus_networks(
        world, "10.0.0.0/8\r\n\r\n 192.168.1.0/24 \r\n2001:db8::/32"
    )

    world.org.reload()
    assert response.status_code == 302
    assert world.org.car_reservation_campus_networks == [
        "10.0.0.0/8",
        "192.168.1.0/24",
        "2001:db8::/32",
    ]


def test_settings_page_shows_the_saved_campus_ip_ranges_in_the_textarea(world):
    save_campus_networks(world, "10.0.0.0/8\n192.168.1.0/24")

    html = (
        world.client_for(world.org_admin)
        .get(f"{SETTINGS_URL}?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    assert "10.0.0.0/8\n192.168.1.0/24</textarea>" in html


def test_an_invalid_campus_ip_range_is_rejected_and_nothing_is_saved(world):
    response = save_campus_networks(world, "10.0.0.0/8\nnot-a-cidr")

    world.org.reload()
    assert response.status_code == 200
    assert "not-a-cidr" in response.get_data(as_text=True)
    assert not world.org.car_reservation_campus_networks


OFF_CAMPUS_BADGE = "ปิดงานนอกมหาวิทยาลัย"


def configure_campus(world, *networks):
    world.org.car_reservation_campus_networks = list(networks)
    world.org.save()


def test_closing_from_inside_the_campus_ranges_is_recorded_as_on_campus(world):
    configure_campus(world, "10.0.0.0/8")
    reservation = world.reservation()

    response = close(world, reservation, remote_addr="10.1.2.3")

    reservation.reload()
    assert response.status_code == 302
    assert reservation.first_assignment.closed_ip == "10.1.2.3"
    assert reservation.first_assignment.closed_off_campus is False


def test_closing_from_outside_the_campus_ranges_is_still_allowed_but_flagged(world):
    configure_campus(world, "10.0.0.0/8")
    reservation = world.reservation()

    response = close(world, reservation, remote_addr="203.0.113.9")

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert reservation.first_assignment.closed_ip == "203.0.113.9"
    assert reservation.first_assignment.closed_off_campus is True


def test_closing_without_configured_ranges_records_the_ip_but_no_verdict(world):
    reservation = world.reservation()

    close(world, reservation, remote_addr="203.0.113.9")

    reservation.reload()
    assert reservation.first_assignment.closed_ip == "203.0.113.9"
    assert reservation.first_assignment.closed_off_campus is None


def test_a_spoofed_forwarded_for_header_cannot_make_a_trip_look_on_campus(world):
    configure_campus(world, "10.0.0.0/8")
    reservation = world.reservation()

    close(
        world,
        reservation,
        remote_addr="203.0.113.9",
        headers={"X-Forwarded-For": "10.1.2.3"},
    )

    reservation.reload()
    assert reservation.first_assignment.closed_ip == "203.0.113.9"
    assert reservation.first_assignment.closed_off_campus is True


def test_detail_and_task_card_warn_when_the_trip_was_closed_off_campus(world):
    configure_campus(world, "10.0.0.0/8")
    reservation = world.reservation()
    close(world, reservation, remote_addr="203.0.113.9")

    detail = world.client_for(world.requester).get(
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    )
    tasks = world.client_for(world.driver).get(world.list_url)

    assert OFF_CAMPUS_BADGE in detail.get_data(as_text=True)
    assert OFF_CAMPUS_BADGE in tasks.get_data(as_text=True)


@pytest.mark.parametrize("ranges, addr", [([], "203.0.113.9"), (["10.0.0.0/8"], "10.1.2.3")])
def test_no_warning_when_on_campus_or_when_no_ranges_are_configured(world, ranges, addr):
    configure_campus(world, *ranges)
    reservation = world.reservation()
    close(world, reservation, remote_addr=addr)

    detail = world.client_for(world.requester).get(
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    )
    tasks = world.client_for(world.driver).get(world.list_url)

    assert OFF_CAMPUS_BADGE not in detail.get_data(as_text=True)
    assert OFF_CAMPUS_BADGE not in tasks.get_data(as_text=True)


def photo_url(world, reservation, which, assignment=None):
    return (
        f"/car_reservation/requests/{reservation.id}/mileage_photo/"
        f"{aid(reservation, assignment)}/{which}?organization_id={world.org.id}"
    )


def test_a_trip_cannot_be_closed_without_the_return_odometer_photo(world):
    reservation = world.reservation()

    response = close(world, reservation, mileage_photo_in=None)

    reservation.reload()
    assert response.status_code == 200
    assert "กรุณาถ่ายรูปเลขไมล์" in response.get_data(as_text=True)
    assert reservation.status == "active"


def test_closing_stores_the_return_photo_with_the_server_receive_time(world):
    reservation = world.reservation()
    before = datetime.datetime.now()

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert before <= reservation.first_assignment.mileage_photos_at <= datetime.datetime.now()


def test_the_requester_can_open_the_return_odometer_photo_as_an_image(world):
    reservation = world.reservation()
    close(world, reservation)

    response = world.client_for(world.requester).get(photo_url(world, reservation, "in"))

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == PNG_BYTES


def test_an_odometer_photo_url_is_404_for_an_unknown_side_or_before_closing(world):
    reservation = world.reservation()
    closed = world.reservation(departure=datetime.datetime(2031, 2, 10, 8, 30))
    close(world, closed, mileage_out="10000")
    client = world.client_for(world.requester)

    assert client.get(photo_url(world, reservation, "in")).status_code == 404
    assert client.get(photo_url(world, closed, "sideways")).status_code == 404
    # ไม่ได้ถ่ายรูปก่อนออกแล้ว
    assert client.get(photo_url(world, closed, "out")).status_code == 404


@pytest.mark.parametrize(
    "who, allowed",
    [
        ("requester", True),
        ("driver", True),
        ("org_admin", True),
        ("dispatcher", True),
        ("approver", True),
        ("other_driver", False),
        ("colleague", False),
    ],
)
def test_odometer_photos_are_visible_only_to_those_involved_in_the_trip(
    world, create_user, assign_user_to_org, who, allowed
):
    world.dispatcher = create_user("Dispatch", "Tasks")
    assign_user_to_org(world.dispatcher, world.org, roles=["dispatcher"])
    world.approver = create_user("Approve", "Tasks")
    assign_user_to_org(world.approver, world.org, roles=["strategy_head"])
    world.colleague = create_user("Colleague", "Tasks")
    assign_user_to_org(world.colleague, world.org, roles=["staff"])
    reservation = world.reservation()
    close(world, reservation)

    response = world.client_for(getattr(world, who)).get(
        photo_url(world, reservation, "in")
    )

    assert (response.status_code == 200) is allowed


@pytest.mark.parametrize(
    "bad_upload",
    [
        (io.BytesIO(b"this is not an image"), "out.png"),
        (io.BytesIO(PNG_BYTES + b"\0" * (5 * 1024 * 1024)), "out.png"),
    ],
    ids=["not-an-image", "over-5-mb"],
)
def test_a_photo_that_is_not_a_small_jpeg_or_png_is_refused(world, bad_upload):
    reservation = world.reservation()

    response = close(world, reservation, mileage_photo_in=bad_upload)

    reservation.reload()
    assert response.status_code == 200
    assert reservation.status == "active"


def test_close_page_captures_photos_with_the_camera_and_has_no_visible_file_picker(
    world,
):
    reservation = world.reservation()

    html = (
        world.client_for(world.driver).get(close_url(world, reservation)).get_data(as_text=True)
    )

    assert 'enctype="multipart/form-data"' in html
    assert "getUserMedia" in html
    assert "ถ่ายรูป" in html
    assert "ใช้เบราว์เซอร์บนมือถือและอนุญาตให้ใช้กล้อง" in html
    file_inputs = [part.split(">")[0] for part in html.split("<input")[1:] if 'type="file"' in part.split(">")[0]]
    assert len(file_inputs) == 1
    assert all('class="hidden"' in tag for tag in file_inputs)


def test_close_page_photo_inputs_are_the_wtforms_file_fields_the_camera_script_fills(world):
    reservation = world.reservation()

    html = (
        world.client_for(world.driver).get(close_url(world, reservation)).get_data(as_text=True)
    )

    from lxml import html as lxml_html

    doc = lxml_html.fromstring(html)
    inputs = doc.xpath("//form[@id='close-form']//fieldset[@data-photo]//input[@type='file']")
    assert [(i.get("id"), i.get("name"), i.get("accept")) for i in inputs] == [
        ("mileage_photo_in", "mileage_photo_in", "image/jpeg,image/png"),
    ]
    # ซ่อนไว้ และต้องไม่มี required (ช่องที่ซ่อนจะโฟกัสไม่ได้ ทำให้เบราว์เซอร์บล็อกการส่งฟอร์ม)
    assert all(i.get("class") == "hidden" and i.get("required") is None for i in inputs)
    # ชื่อ data-photo ที่สคริปต์ใช้ตั้งชื่อไฟล์ ต้องตรงกับชื่อ field
    assert [f.get("data-photo") for f in doc.xpath("//fieldset[@data-photo]")] == [
        i.get("name") for i in inputs
    ]


def test_request_detail_shows_the_return_odometer_photo_to_those_who_may_see_it(world):
    reservation = world.reservation()
    close(world, reservation)

    html = (
        world.client_for(world.requester)
        .get(f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    report = html.split('data-role="trip-report"')[1]
    assert "/mileage_photo/" in report
    assert f"/mileage_photo/{aid(reservation)}/out" not in report
    assert f"/mileage_photo/{aid(reservation)}/in" in report
    # กดปุ่มดูรูป รูปอยู่ใน modal ไม่ได้แสดงเต็มในหน้า
    assert 'data-role="open-mileage-photo"' in report
    assert re.search(
        rf'<dialog id="mileage-photo-{aid(reservation)}-in".*?mileage_photo/', report, re.S
    )


def test_an_old_trip_closed_with_both_photos_still_shows_both(world):
    reservation = world.reservation()
    close(world, reservation)
    reservation.reload()
    reservation.first_assignment.mileage_photo_out.put(io.BytesIO(PNG_BYTES), filename="out.png", content_type="image/png")
    reservation.save()

    report = (
        world.client_for(world.requester)
        .get(f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}")
        .get_data(as_text=True)
        .split('data-role="trip-report"')[1]
    )

    assert f"/mileage_photo/{aid(reservation)}/out" in report
    assert f"/mileage_photo/{aid(reservation)}/in" in report


def test_request_detail_hides_the_odometer_photos_from_other_colleagues(
    world, create_user, assign_user_to_org
):
    colleague = create_user("Colleague", "Detail")
    assign_user_to_org(colleague, world.org, roles=["staff"])
    reservation = world.reservation()
    close(world, reservation)

    html = (
        world.client_for(colleague)
        .get(f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    assert "mileage_photo" not in html


def test_close_page_camera_video_and_preview_share_one_fixed_aspect_box(world):
    from lxml import html as lxml_html

    reservation = world.reservation()

    html = (
        world.client_for(world.driver).get(close_url(world, reservation)).get_data(as_text=True)
    )

    doc = lxml_html.fromstring(html)
    blocks = doc.xpath("//form[@id='close-form']//fieldset[@data-photo]")
    assert len(blocks) == 1
    for block in blocks:
        (video,) = block.xpath(".//video")
        (preview,) = block.xpath(".//img")
        video_classes = set(video.get("class").split())
        preview_classes = set(preview.get("class").split())
        aspects = {c for c in video_classes if c.startswith("aspect-")}
        assert aspects and aspects == {c for c in preview_classes if c.startswith("aspect-")}
        # สตรีม 4:3 ต้องไม่ถูก letterbox ด้วย aspect-video (16:9)
        assert "aspect-video" not in video_classes
        assert "object-cover" in video_classes and "object-cover" in preview_classes


# ---- คำขอหลายคัน: พขร. แต่ละคนเห็นและปิดเฉพาะชุดของตัวเอง -----------------------


@pytest.fixture
def pair(world, create_car):
    """คำขอ active 2 คัน: world.driver ขับ world.car (ไมล์ 10000) และ world.other_driver ขับ car2 (ไมล์ 50000)"""
    world.car2 = create_car(world.org, "ขข 5678", vehicle_type="ตู้")
    world.car2.last_mileage = 50000
    world.car2.save()
    world.two_cars = models.CarReservation(
        organization=world.org,
        creator=world.requester,
        requester_unit="คณะวิศวกรรมศาสตร์",
        phone="081-234-5678",
        request_type="domestic",
        province_scope="in_province",
        location="เชียงราย",
        request_reason="ประชุม",
        departure_datetime=datetime.datetime(2031, 1, 10, 8, 30),
        return_datetime=datetime.datetime(2031, 1, 10, 16, 30),
        pickup_place="หน้าอาคารอธิการบดี",
        pickup_time="07:30",
        status="active",
        route_snapshot=["supervisor", "dispatcher"],
        current_step=2,
        assignments=[
            models.CarAssignment(car=world.car, driver=world.driver),
            models.CarAssignment(car=world.car2, driver=world.other_driver),
        ],
    ).save()
    world.mine, world.theirs = world.two_cars.assignments
    return world


def email_events(mock_q, event):
    return [
        call.kwargs["args"]
        for call in mock_q.enqueue.call_args_list
        if call.args[0] is utils.car_reservation_email.send_car_reservation_email
        and call.kwargs["args"][1] == event
    ]


def card_of(html, location):
    cards = html.split('data-role="task-card"')[1:]
    return [card for card in cards if location in card]


def test_each_driver_sees_only_their_own_assignment_of_a_two_car_request(pair):
    mine = pair.client_for(pair.driver).get(pair.list_url).get_data(as_text=True)
    theirs = pair.client_for(pair.other_driver).get(pair.list_url).get_data(as_text=True)

    [card] = card_of(mine, "เชียงราย")
    assert "กก 1234" in card and "ขข 5678" not in card
    assert f"/close/{pair.mine.assignment_id}" not in card  # ยังไม่เริ่ม: ปุ่มเริ่มงานก่อน
    assert f"/start/{pair.mine.assignment_id}" in card
    assert str(pair.theirs.assignment_id) not in mine
    [other_card] = card_of(theirs, "เชียงราย")
    assert "ขข 5678" in other_card and "กก 1234" not in other_card
    assert f"/start/{pair.theirs.assignment_id}" in other_card


def test_a_closed_assignment_is_not_an_open_task_even_though_the_request_is_active(pair):
    pair.client_for(pair.driver).post(start_url(pair, pair.two_cars, pair.mine))
    close_response = pair.client_for(pair.driver).post(
        close_url(pair, pair.two_cars, pair.mine), data=close_data()
    )
    assert close_response.status_code == 302
    pair.two_cars.reload()
    assert pair.two_cars.status == "active"  # คันของอีกคนยังเปิดอยู่

    mine = pair.client_for(pair.driver).get(pair.list_url).get_data(as_text=True)
    theirs = pair.client_for(pair.other_driver).get(pair.list_url).get_data(as_text=True)

    open_part = mine.split('data-role="active-tasks"')[1].split('data-role="completed-tasks"')[0]
    done_part = mine.split('data-role="completed-tasks"')[1]
    assert "เชียงราย" not in open_part
    assert "เชียงราย" in done_part and "ปิดงานแล้ว" in done_part
    assert f"/close/{pair.mine.assignment_id}" not in mine
    # งานของอีกคนไม่กระทบ
    assert "เชียงราย" in theirs.split('data-role="active-tasks"')[1].split('data-role="completed-tasks"')[0]


def test_driver_close_page_shows_its_own_car_and_prefills_that_cars_mileage(pair):
    mine = pair.client_for(pair.driver).get(close_url(pair, pair.two_cars, pair.mine))
    theirs = pair.client_for(pair.other_driver).get(
        close_url(pair, pair.two_cars, pair.theirs)
    )

    assert 'value="10000"' in mine.get_data(as_text=True)
    assert "กก 1234" in mine.get_data(as_text=True)
    assert 'value="50000"' in theirs.get_data(as_text=True)
    assert "ขข 5678" in theirs.get_data(as_text=True)


def test_the_request_completes_only_after_the_second_driver_closes_and_the_requester_is_told_once(
    pair, mock_redis_queue
):
    first = pair.client_for(pair.driver).post(
        close_url(pair, pair.two_cars, pair.mine), data=close_data()
    )
    pair.two_cars.reload()
    assert first.status_code == 302
    assert pair.two_cars.status == "active"
    assert email_events(mock_redis_queue, "completed") == []
    assert "completed" not in [
        n.event for n in notifications.inbox(pair.requester, pair.org)
    ]

    second = pair.client_for(pair.other_driver).post(
        close_url(pair, pair.two_cars, pair.theirs),
        data=close_data(mileage_out="50000", mileage_in="50300"),
    )

    pair.two_cars.reload()
    assert second.status_code == 302, second.get_data(as_text=True)
    assert pair.two_cars.status == "completed"
    [job] = email_events(mock_redis_queue, "completed")
    assert job[2] == [pair.requester.email]
    assert [n.event for n in notifications.inbox(pair.requester, pair.org)].count("completed") == 1
    mine, theirs = pair.two_cars.assignments
    assert (mine.last_mileage_before, mine.last_mileage) == (10000, 10250)
    assert (theirs.last_mileage_before, theirs.last_mileage) == (50000, 50300)
    pair.car.reload()
    pair.car2.reload()
    assert (pair.car.last_mileage, pair.car2.last_mileage) == (10250, 50300)


def test_the_start_time_is_recorded_per_assignment(pair):
    pair.client_for(pair.driver).post(start_url(pair, pair.two_cars, pair.mine))

    pair.two_cars.reload()
    mine, theirs = pair.two_cars.assignments
    assert mine.started_at is not None
    assert theirs.started_at is None


@pytest.mark.parametrize("action", ["start", "close"])
def test_a_driver_cannot_start_or_close_another_drivers_assignment(pair, action):
    client = pair.client_for(pair.driver)
    url = (start_url if action == "start" else close_url)(pair, pair.two_cars, pair.theirs)

    response = (
        client.post(url) if action == "start" else client.post(url, data=close_data())
    )

    assert response.status_code in (302, 403)  # acl แปลง 403 บางกรณีเป็น redirect
    pair.two_cars.reload()
    theirs = pair.two_cars.assignments[1]
    assert theirs.started_at is None and theirs.completed_at is None
    assert pair.two_cars.status == "active"
    if action == "close":
        assert client.get(url).status_code in (302, 403)


def test_a_driver_cannot_use_an_assignment_id_of_another_request(pair):
    other = pair.reservation(driver=pair.driver, location="ที่อื่น")

    start = pair.client_for(pair.driver).post(start_url(pair, pair.two_cars, other.first_assignment))
    close_ = pair.client_for(pair.driver).post(
        close_url(pair, pair.two_cars, other.first_assignment), data=close_data()
    )

    assert start.status_code == 404 and close_.status_code == 404
    other.reload()
    assert other.first_assignment.started_at is None


def test_driver_summary_counts_each_assignment_once(pair):
    pair.two_cars.departure_datetime = datetime.datetime.now() - datetime.timedelta(hours=2)
    pair.two_cars.return_datetime = datetime.datetime.now() + datetime.timedelta(hours=2)
    pair.two_cars.save()

    html = pair.client_for(pair.driver).get(
        f"{BASE}/summary?organization_id={pair.org.id}"
    ).get_data(as_text=True)

    assert re.search(r'data-stat="in_hours">1<', html)
