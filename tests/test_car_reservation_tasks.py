"""งานของพนักงานขับรถ (ระบบจองรถ): พขร. เห็นเฉพาะงานของตัวเอง และปิดงานพร้อมเลขไมล์/น้ำมัน/ค่าใช้จ่าย"""

import base64
import datetime
import io
from unittest.mock import MagicMock, patch

import pytest

from kampan import models
from kampan.web import redis_rq

BASE = "/car_reservation/tasks"

# PNG 1x1 พิกเซลของจริง (ผ่านการตรวจเป็นภาพ JPEG/PNG)
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


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
        "mileage_photo_out": (io.BytesIO(PNG_BYTES), "out.png"),
        "mileage_photo_in": (io.BytesIO(PNG_BYTES), "in.png"),
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def close_url(world, reservation):
    return f"{BASE}/{reservation.id}/close?organization_id={world.org.id}"


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
    assert reservation.closed_ip == "10.1.2.3"
    assert reservation.closed_off_campus is False


def test_closing_from_outside_the_campus_ranges_is_still_allowed_but_flagged(world):
    configure_campus(world, "10.0.0.0/8")
    reservation = world.reservation()

    response = close(world, reservation, remote_addr="203.0.113.9")

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert reservation.closed_ip == "203.0.113.9"
    assert reservation.closed_off_campus is True


def test_closing_without_configured_ranges_records_the_ip_but_no_verdict(world):
    reservation = world.reservation()

    close(world, reservation, remote_addr="203.0.113.9")

    reservation.reload()
    assert reservation.closed_ip == "203.0.113.9"
    assert reservation.closed_off_campus is None


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
    assert reservation.closed_ip == "203.0.113.9"
    assert reservation.closed_off_campus is True


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


def photo_url(world, reservation, which):
    return (
        f"/car_reservation/requests/{reservation.id}/mileage_photo/{which}"
        f"?organization_id={world.org.id}"
    )


@pytest.mark.parametrize("missing", ["mileage_photo_out", "mileage_photo_in"])
def test_a_trip_cannot_be_closed_without_both_odometer_photos(world, missing):
    reservation = world.reservation()

    response = close(world, reservation, **{missing: None})

    reservation.reload()
    assert response.status_code == 200
    assert "กรุณาถ่ายรูปเลขไมล์" in response.get_data(as_text=True)
    assert reservation.status == "active"


def test_closing_with_both_photos_stores_them_with_the_server_receive_time(world):
    reservation = world.reservation()
    before = datetime.datetime.now()

    response = close(world, reservation)

    reservation.reload()
    assert response.status_code == 302
    assert reservation.status == "completed"
    assert before <= reservation.mileage_photos_at <= datetime.datetime.now()


@pytest.mark.parametrize("which", ["out", "in"])
def test_the_requester_can_open_each_odometer_photo_as_an_image(world, which):
    reservation = world.reservation()
    close(world, reservation)

    response = world.client_for(world.requester).get(photo_url(world, reservation, which))

    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert response.data == PNG_BYTES


def test_an_odometer_photo_url_is_404_for_an_unknown_side_or_before_closing(world):
    reservation = world.reservation()
    closed = world.reservation(departure=datetime.datetime(2031, 2, 10, 8, 30))
    close(world, closed, mileage_out="10000")
    client = world.client_for(world.requester)

    assert client.get(photo_url(world, reservation, "out")).status_code == 404
    assert client.get(photo_url(world, closed, "sideways")).status_code == 404


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
        photo_url(world, reservation, "out")
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

    response = close(world, reservation, mileage_photo_out=bad_upload)

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
    assert len(file_inputs) == 2
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
        ("mileage_photo_out", "mileage_photo_out", "image/jpeg,image/png"),
        ("mileage_photo_in", "mileage_photo_in", "image/jpeg,image/png"),
    ]
    # ซ่อนไว้ และต้องไม่มี required (ช่องที่ซ่อนจะโฟกัสไม่ได้ ทำให้เบราว์เซอร์บล็อกการส่งฟอร์ม)
    assert all(i.get("class") == "hidden" and i.get("required") is None for i in inputs)
    # ชื่อ data-photo ที่สคริปต์ใช้ตั้งชื่อไฟล์ ต้องตรงกับชื่อ field
    assert [f.get("data-photo") for f in doc.xpath("//fieldset[@data-photo]")] == [
        i.get("name") for i in inputs
    ]


def test_request_detail_shows_both_odometer_photos_to_those_who_may_see_them(world):
    reservation = world.reservation()
    close(world, reservation)

    html = (
        world.client_for(world.requester)
        .get(f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    report = html.split('data-role="trip-report"')[1]
    assert f"/requests/{reservation.id}/mileage_photo/out" in report
    assert f"/requests/{reservation.id}/mileage_photo/in" in report


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
    assert len(blocks) == 2
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
