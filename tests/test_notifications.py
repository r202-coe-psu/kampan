"""แจ้งเตือนในระบบ (กระดิ่ง): เหตุการณ์ของคำขอใช้รถส่งถึงผู้เกี่ยวข้องในองค์กรเดียวกัน"""

from kampan.utils import notifications
from tests.test_car_reservation import (  # noqa: F401
    approve_url,
    mock_redis_queue,
    request_at_dispatcher,
    step_data,
    world,
)


def events_of(user, org):
    return [n.event for n in notifications.inbox(user, org)]


def test_submitting_a_request_notifies_the_division_head_but_not_the_requester(world):
    world.submit_request()

    assert events_of(world.supervisor, world.org) == ["submitted"]
    assert events_of(world.requester, world.org) == []


def test_dispatcher_assigning_a_driver_notifies_the_driver_and_the_next_approver(world):
    car_application = request_at_dispatcher(world)

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=step_data(world, "dispatcher")
    )

    assert events_of(world.driver, world.org) == ["driver_assigned"]
    assert events_of(world.holders["vehicle_unit_head"], world.org) == ["approved"]
    assert events_of(world.dispatcher, world.org) == ["approved"]  # จากขั้นผู้บังคับบัญชา


NOTI = "/car_reservation/notifications"


def test_opening_a_notification_marks_it_read_and_goes_to_the_request(world):
    car_application = world.submit_request()
    notification = notifications.inbox(world.supervisor, world.org).first()

    response = world.client_for(world.supervisor).get(
        f"{NOTI}/{notification.id}/open?organization_id={world.org.id}"
    )

    assert response.status_code == 302
    assert str(car_application.id) in response.headers["Location"]
    assert notifications.unread_count(world.supervisor, world.org) == 0


def test_a_user_cannot_open_someone_elses_notification(world):
    world.submit_request()
    notification = notifications.inbox(world.supervisor, world.org).first()

    response = world.client_for(world.stranger).get(
        f"{NOTI}/{notification.id}/open?organization_id={world.org.id}"
    )

    assert response.status_code == 404
    assert notifications.unread_count(world.supervisor, world.org) == 1


def test_bell_shows_the_unread_count_and_the_latest_notifications(world):
    world.submit_request()
    client = world.client_for(world.supervisor)

    badge = client.get(f"{NOTI}/badge?organization_id={world.org.id}").get_data(as_text=True)
    menu = client.get(f"{NOTI}/menu?organization_id={world.org.id}").get_data(as_text=True)

    assert 'data-role="notification-count"' in badge and ">1<" in badge
    assert "มีคำขอใช้รถรอการอนุมัติ" in menu


def test_read_all_clears_the_unread_count(world):
    world.submit_request()

    response = world.client_for(world.supervisor).post(
        f"{NOTI}/read-all?organization_id={world.org.id}"
    )

    assert response.status_code == 302
    assert notifications.unread_count(world.supervisor, world.org) == 0


def test_the_notifications_page_lists_only_my_notifications_in_this_organization(
    world, create_org
):
    world.submit_request()
    other_org = create_org("Other Org")
    notifications.send(
        other_org, [world.supervisor], module="car_reservation", event="submitted",
        title="ของอีก org",
    )

    page = world.client_for(world.supervisor).get(f"{NOTI}?organization_id={world.org.id}")

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "มีคำขอใช้รถรอการอนุมัติ" in html
    assert "ของอีก org" not in html


def test_sidebar_has_a_bell_that_polls_the_unread_count(world):
    html = world.client_for(world.supervisor).get(
        f"/car_reservation/requests/?organization_id={world.org.id}"
    ).get_data(as_text=True)

    assert 'data-role="notification-bell"' in html
    assert f"{NOTI}/badge?organization_id={world.org.id}" in html
    assert "every 60s" in html
