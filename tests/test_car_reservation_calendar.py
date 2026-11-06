"""ปฏิทินการจองรถ: สมาชิกทุกคนของหน่วยงานเห็นตารางรถของหน่วยงานตัวเอง (เฉพาะคำขอที่ยังมีผลกับรถ)"""

import datetime

import pytest

from kampan import models

BASE = "/car_reservation/calendar"
MONTH = {"start": "2031-01-01", "end": "2031-02-01"}


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Calendar Org")
    org.enabled_modules = ["car_reservation"]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "Calendar")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.driver = create_user("Driver", "Calendar")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")
    s.client = login_as(app.test_client(), s.requester)

    def reservation(
        status="active",
        departure=datetime.datetime(2031, 1, 10, 8, 30),
        return_=datetime.datetime(2031, 1, 10, 17, 0),
        location="กรุงเทพฯ",
        organization=org,
        car=None,
        driver=None,
    ):
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
            route_snapshot=["supervisor", "dispatcher", "vehicle_unit_head"],
            current_step=1,
            car=car,
            driver=driver,
        ).save()

    s.reservation = reservation

    def events(params=None, organization=org, client=None):
        query = {"organization_id": str(organization.id), **(params or MONTH)}
        response = (client or s.client).get(f"{BASE}/events", query_string=query)
        assert response.status_code == 200, response.get_data(as_text=True)
        return response.get_json()

    s.events = events
    return s


def test_events_list_live_reservations_and_leave_out_denied_and_cancelled(world):
    shown = {
        status: world.reservation(status=status, location=f"ที่-{status}")
        for status in ("pending", "active", "completed", "cancel_requested")
    }
    for status in ("denied", "cancelled"):
        world.reservation(status=status, location=f"ที่-{status}")

    events = world.events()

    assert {event["id"] for event in events} == {str(r.id) for r in shown.values()}


def test_event_shows_departure_time_destination_and_plate_over_the_whole_trip(world):
    reservation = world.reservation(
        departure=datetime.datetime(2031, 1, 10, 8, 30),
        return_=datetime.datetime(2031, 1, 12, 17, 0),
        location="เชียงใหม่",
        car=world.car,
        driver=world.driver,
    )

    [event] = world.events()

    assert event["id"] == str(reservation.id)
    assert event["title"] == "08:30 น. เชียงใหม่ (กก 1234)"
    assert event["start"] == "2031-01-10"
    # วันสุดท้ายนับรวม: FullCalendar คาดหวังวันสิ้นสุดแบบ exclusive
    assert event["end"] == "2031-01-13"


def test_event_title_has_no_plate_until_a_car_is_assigned(world):
    world.reservation(status="pending", location="สงขลา")

    [event] = world.events()

    assert event["title"] == "08:30 น. สงขลา"


@pytest.mark.parametrize(
    "status, tone",
    [
        ("pending", "event-warning"),
        ("cancel_requested", "event-warning"),
        ("active", "event-success"),
        ("completed", "event-neutral"),
    ],
)
def test_event_color_follows_the_reservation_status(world, status, tone):
    world.reservation(status=status)

    [event] = world.events()

    assert event["classNames"] == [tone]
