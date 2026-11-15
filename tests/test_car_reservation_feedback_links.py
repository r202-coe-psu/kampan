"""ลิงก์ไปแบบประเมินของระบบจองรถ: อีเมลหลัง พขร. ปิดงาน, หน้ารายละเอียดใบขอ และคำขอของฉัน

ทุกลิงก์ชี้ไปหน้าประเมินสาธารณะของรถคันที่ใช้ พร้อม ``?reservation_id=`` เลือกเที่ยวนั้นให้
"""

import base64
import datetime
import io
import re
from unittest.mock import MagicMock, patch

import pytest

from kampan import models, utils
from kampan.web import redis_rq


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """กันการต่อ Redis จริง และให้ตรวจ job แจ้งเตือนที่ถูกส่งเข้าคิวได้"""
    mock_q = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", mock_q, create=True):
        yield mock_q


def email_jobs(mock_q, event):
    """[(request_id, event, recipients, host_url)] ของ job อีเมลจองรถที่ส่งเข้าคิวตามเหตุการณ์"""
    return [
        call.kwargs["args"]
        for call in mock_q.enqueue.call_args_list
        if call.args[0] is utils.car_reservation_email.send_car_reservation_email
        and call.kwargs["args"][1] == event
    ]


@pytest.fixture
def sent_emails(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, setting):
            pass

        def login(self):
            return True

        def quit(self):
            pass

        def send_email(self, receiver, subject, body, html=False, steps=None, app_name=None):
            sent.append({"receiver": receiver, "subject": subject, "body": body})
            return True

    monkeypatch.setattr(utils.email_utils, "PSUSMTP", FakeSMTP)
    return sent


@pytest.fixture
def world(
    app,
    create_org,
    create_user,
    assign_user_to_org,
    login_as,
    create_car,
    create_feedback_template,
    make_question,
):
    org = create_org("Feedback Org")
    org.enabled_modules = ["car_reservation"]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "Feedback")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.colleague = create_user("Colleague", "Feedback")
    assign_user_to_org(s.colleague, org, roles=["staff"])
    s.driver = create_user("Driver", "Feedback")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")
    s.template = create_feedback_template(
        org, [s.car], name="แบบประเมินรถเก๋ง", questions=[make_question("score", "ให้คะแนนบริการ")]
    )

    s.client_for = lambda user: login_as(app.test_client(), user)

    def reservation(status="completed", creator=None, car=None):
        departure = datetime.datetime(2031, 1, 10, 8, 30)
        return models.CarReservation(
            organization=org,
            creator=creator or s.requester,
            requester_unit="คณะวิศวกรรมศาสตร์",
            phone="081-234-5678",
            request_type="domestic",
            province_scope="in_province",
            location="กรุงเทพฯ",
            request_reason="ประชุม",
            departure_datetime=departure,
            return_datetime=departure + datetime.timedelta(hours=8),
            status=status,
            route_snapshot=["supervisor", "dispatcher"],
            current_step=2,
            car=car or s.car,
            driver=s.driver,
        ).save()

    s.reservation = reservation
    s.feedback_path = lambda res: f"/car_reservation/cars/{s.car.id}/feedback?reservation_id={res.id}"
    return s


def detail_url(world, reservation):
    return f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"


def test_detail_page_links_the_requester_of_a_completed_trip_to_the_car_survey_with_the_trip_selected(world):
    reservation = world.reservation()

    html = world.client_for(world.requester).get(detail_url(world, reservation)).get_data(as_text=True)

    assert "ประเมินความพึงพอใจ" in html
    assert f'href="{world.feedback_path(reservation)}"' in html


@pytest.mark.parametrize("who", ["colleague", "driver"])
def test_detail_page_hides_the_survey_link_from_everyone_but_the_requester(world, who):
    reservation = world.reservation()

    html = world.client_for(getattr(world, who)).get(detail_url(world, reservation)).get_data(as_text=True)

    assert f"/car_reservation/cars/{world.car.id}/feedback" not in html


@pytest.mark.parametrize("status", ["pending", "active", "denied", "cancelled"])
def test_detail_page_hides_the_survey_link_until_the_trip_is_completed(world, status):
    reservation = world.reservation(status=status)

    html = world.client_for(world.requester).get(detail_url(world, reservation)).get_data(as_text=True)

    assert f"/car_reservation/cars/{world.car.id}/feedback" not in html


def test_detail_page_hides_the_survey_link_when_the_car_has_no_survey(world, create_car):
    other_car = create_car(world.org, "ขข 5678")
    reservation = world.reservation(car=other_car)

    html = world.client_for(world.requester).get(detail_url(world, reservation)).get_data(as_text=True)

    assert f"/car_reservation/cars/{other_car.id}/feedback" not in html
    assert 'data-role="feedback-link"' not in html


def test_my_requests_list_links_to_the_car_survey_of_each_completed_trip(world):
    reservation = world.reservation()

    html = (
        world.client_for(world.requester)
        .get(f"/car_reservation/requests/?organization_id={world.org.id}")
        .get_data(as_text=True)
    )

    assert f'href="{world.feedback_path(reservation)}"' in html


def test_the_link_leads_to_the_public_survey_page_with_the_trip_selected(world):
    reservation = world.reservation()

    response = world.client_for(world.requester).get(world.feedback_path(reservation))
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "แบบประเมินรถเก๋ง" in body
    assert "ให้คะแนนบริการ" in body
    assert re.findall(r'<option(?=[^>]*\sselected)[^>]*\svalue="([0-9a-f]{24})"', body) == [str(reservation.id)]


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def test_driver_closing_the_trip_emails_the_requester_the_survey_link_job(world, mock_redis_queue):
    reservation = world.reservation(status="active")

    response = world.client_for(world.driver).post(
        f"/car_reservation/tasks/{reservation.id}/close?organization_id={world.org.id}",
        data={
            "mileage_out": "0",
            "mileage_in": "120",
            "expense_case": "fleet_card",
            "mileage_photo_out": (io.BytesIO(PNG_BYTES), "out.png"),
            "mileage_photo_in": (io.BytesIO(PNG_BYTES), "in.png"),
        },
    )

    assert response.status_code == 302
    jobs = email_jobs(mock_redis_queue, "completed")
    assert len(jobs) == 1
    request_id, event, recipients, host_url = jobs[0]
    assert request_id == str(reservation.id)
    assert recipients == [world.requester.email]
    assert host_url.startswith("http")


def test_a_refused_close_sends_no_completed_email(world, mock_redis_queue):
    reservation = world.reservation(status="active")

    world.client_for(world.driver).post(
        f"/car_reservation/tasks/{reservation.id}/close?organization_id={world.org.id}",
        data={"mileage_out": "500", "mileage_in": "100", "expense_case": "fleet_card"},
    )

    assert email_jobs(mock_redis_queue, "completed") == []


def test_completed_email_gives_the_requester_the_per_car_survey_link_with_the_trip(app, world, sent_emails):
    reservation = world.reservation()

    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(reservation.id),
            "completed",
            [world.requester.email],
            "https://staging.example.test",
        )

    assert [email["receiver"] for email in sent_emails] == [world.requester.email]
    email = sent_emails[0]
    assert "ประเมินความพึงพอใจ" in email["subject"]
    assert (
        f"https://staging.example.test/car_reservation/cars/{world.car.id}/feedback"
        f"?reservation_id={reservation.id}"
    ) in email["body"]
    assert "กก 1234" in email["body"]


def test_org_default_template_of_the_completed_email_can_use_feedback_url(app, world, sent_emails):
    reservation = world.reservation()
    models.EmailTemplate(
        name="ประเมินหลังปิดงาน",
        subject="ประเมิน {{ requester_name }}",
        body="โปรดประเมินที่ {{ feedback_url }}",
        type="car_reservation_completed",
        organization=world.org,
        is_default=True,
    ).save()

    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(reservation.id),
            "completed",
            [world.requester.email],
            "https://staging.example.test",
        )

    assert sent_emails[0]["subject"] == "ประเมิน Requester Feedback"
    assert sent_emails[0]["body"] == (
        f"โปรดประเมินที่ https://staging.example.test/car_reservation/cars/{world.car.id}/feedback"
        f"?reservation_id={reservation.id}"
    )
