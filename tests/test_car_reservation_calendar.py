"""ปฏิทินการจองรถ: สมาชิกทุกคนของหน่วยงานเห็นตารางรถของหน่วยงานตัวเอง (เฉพาะคำขอที่ยังมีผลกับรถ)"""

import datetime
import re

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


def test_events_are_limited_to_the_requested_date_range(world):
    inside = world.reservation(location="ในเดือน")
    spanning_in = world.reservation(
        location="ข้ามจากเดือนก่อน",
        departure=datetime.datetime(2030, 12, 30, 8, 0),
        return_=datetime.datetime(2031, 1, 2, 17, 0),
    )
    world.reservation(
        location="เดือนก่อน",
        departure=datetime.datetime(2030, 12, 10, 8, 0),
        return_=datetime.datetime(2030, 12, 10, 17, 0),
    )
    world.reservation(
        location="เดือนหน้า",
        departure=datetime.datetime(2031, 2, 1, 8, 0),
        return_=datetime.datetime(2031, 2, 1, 17, 0),
    )

    events = world.events(
        {"start": "2031-01-01T00:00:00+07:00", "end": "2031-02-01T00:00:00+07:00"}
    )

    assert {event["id"] for event in events} == {str(inside.id), str(spanning_in.id)}


def modal_url(world, reservation, organization=None):
    organization = organization or world.org
    return f"{BASE}/{reservation.id}/modal?organization_id={organization.id}"


def test_modal_shows_trip_car_driver_status_stepper_and_link_to_the_request(world):
    reservation = world.reservation(
        departure=datetime.datetime(2031, 1, 10, 8, 30),
        return_=datetime.datetime(2031, 1, 12, 17, 0),
        location="เชียงใหม่",
        car=world.car,
        driver=world.driver,
    )

    response = world.client.get(modal_url(world, reservation))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ" in html
    assert world.requester.get_name() in html
    assert "เชียงใหม่" in html
    assert "10/01/2031" in html and "08:30" in html
    assert "12/01/2031" in html and "17:00" in html
    assert "กก 1234" in html
    assert world.driver.get_name() in html
    assert 'data-status="active"' in html
    assert html.count("data-state=") == 3
    assert (
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
        in html
    )


def test_modal_stepper_marks_where_a_pending_request_is_in_its_route(world):
    reservation = world.reservation(status="pending")  # อยู่ขั้นที่สอง (ผู้จัดรถ)
    reservation.step_approvals = [
        models.car_reservations.StepApproval(
            step_key="supervisor", decision="approved"
        )
    ]
    reservation.save()

    html = world.client.get(modal_url(world, reservation)).get_data(as_text=True)

    states = re.findall(r'data-state="(\w+)"', html)
    assert states == ["done", "current", "waiting"]
    assert 'class="step step-current"' in html


def test_modal_of_another_organizations_reservation_is_404(world, create_org):
    other_org = create_org("Other Calendar Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    foreign = world.reservation(organization=other_org)

    response = world.client.get(modal_url(world, foreign))

    assert response.status_code == 404


def test_any_member_opens_the_calendar_page_with_a_new_request_button(world):
    response = world.client.get(f"{BASE}/?organization_id={world.org.id}")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert f"{BASE}/events?organization_id={world.org.id}" in html
    assert f"/car_reservation/requests/new?organization_id={world.org.id}" in html
    assert "ยื่นคำขอ" in html


def test_sidebar_links_every_member_to_the_calendar(world):
    html = world.client.get(
        f"/car_reservation/requests/?organization_id={world.org.id}"
    ).get_data(as_text=True)

    assert "ปฏิทินการจองรถ" in html
    assert f"{BASE}/?organization_id={world.org.id}" in html


def test_calendar_is_404_for_an_organization_without_the_module(
    app, create_org, create_user, assign_user_to_org, login_as
):
    org = create_org("Car Only Calendar Org")
    org.enabled_modules = ["car"]
    org.save()
    user = create_user("Car", "Calendar")
    assign_user_to_org(user, org, roles=["staff"])
    client = login_as(app.test_client(), user)

    for path in ("/", "/events", "/000000000000000000000000/modal"):
        response = client.get(f"{BASE}{path}?organization_id={org.id}")
        assert response.status_code == 404, path


def test_events_never_include_another_organizations_reservations(world, create_org):
    other_org = create_org("Other Calendar Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    world.reservation(organization=other_org, location="ของที่อื่น")
    mine = world.reservation(location="ของเรา")

    events = world.events()

    assert [event["id"] for event in events] == [str(mine.id)]
