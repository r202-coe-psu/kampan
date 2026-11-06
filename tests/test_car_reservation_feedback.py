"""แบบประเมินความพึงพอใจของระบบจองรถ: ผู้ขอประเมินหลังปิดงาน และผู้ดูแลองค์กรดูผลสรุป"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from kampan import models, utils
from kampan.web import redis_rq

BASE = "/car_reservation/feedback"

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


SCORE_QUESTIONS = [
    "ความสะอาด",
    "ความเหมาะสมของรถยนต์กับการเดินทาง",
    "ความพร้อม (น้ำมัน/สภาพเครื่องยนต์)",
    "ระบบปรับอากาศ",
    "การขับขี่ (ความเร็ว/การปฏิบัติตามกฎจราจร)",
    "การตรงต่อเวลา",
    "ศึกษาเส้นทางก่อนการเดินทาง",
    "ความเอื้อเฟื้อ/มีจิตบริการ",
    "ความพึงพอใจในภาพรวม",
]


SCORE_KEYS = [
    "vehicle_cleanliness",
    "vehicle_suitability",
    "vehicle_readiness",
    "vehicle_air_conditioning",
    "driver_driving",
    "driver_punctuality",
    "driver_route_study",
    "driver_service_mind",
    "overall",
]


def all_scores(value=5, **overrides):
    data = {key: str(value) for key in SCORE_KEYS}
    data.update({key: str(score) for key, score in overrides.items()})
    return data


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
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
    s.org_admin = create_user("Admin", "Feedback")
    assign_user_to_org(s.org_admin, org, roles=["admin"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")

    s.client_for = lambda user: login_as(app.test_client(), user)

    def reservation(status="completed", organization=None, creator=None):
        departure = datetime.datetime(2031, 1, 10, 8, 30)
        return models.CarReservation(
            organization=organization or org,
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
            car=s.car,
            driver=s.driver,
        ).save()

    s.reservation = reservation
    s.url = lambda res, organization=None: (
        f"{BASE}/{res.id}?organization_id={(organization or org).id}"
    )
    return s


def test_requester_opens_the_form_of_a_completed_trip_with_header_filled_and_every_question(
    world,
):
    reservation = world.reservation()

    response = world.client_for(world.requester).get(world.url(reservation))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for header in ("10/01/2031", "เก๋ง", "กก 1234", "Driver Feedback"):
        assert header in html
    for question in SCORE_QUESTIONS:
        assert question in html
    assert "สภาพรถยนต์" in html and "พนักงานขับรถยนต์" in html
    assert "ข้อเสนอแนะเพิ่มเติม" in html


def test_requester_submits_scores_and_comment_and_one_response_is_saved(world):
    reservation = world.reservation()

    response = world.client_for(world.requester).post(
        world.url(reservation),
        data={**all_scores(4, driver_punctuality=2, overall=5), "comment": "คนขับสุภาพ"},
    )

    assert response.status_code == 302
    saved = models.CarReservationFeedback.objects(reservation=reservation)
    assert saved.count() == 1
    feedback = saved.first()
    assert feedback.organization == world.org
    assert feedback.creator == world.requester
    assert feedback.car == world.car
    assert feedback.driver == world.driver
    assert feedback.score_of("driver_punctuality") == 2
    assert feedback.score_of("overall") == 5
    assert feedback.score_of("vehicle_cleanliness") == 4
    assert feedback.comment == "คนขับสุภาพ"


@pytest.mark.parametrize("who", ["colleague", "driver", "org_admin"])
def test_only_the_requester_of_that_reservation_may_open_or_submit_the_survey(world, who):
    reservation = world.reservation()
    client = world.client_for(getattr(world, who))

    assert client.get(world.url(reservation)).status_code in (302, 403)
    assert client.post(world.url(reservation), data=all_scores()).status_code in (302, 403)
    assert models.CarReservationFeedback.objects.count() == 0


@pytest.mark.parametrize("status", ["pending", "active", "denied", "cancelled"])
def test_survey_is_closed_until_the_trip_is_completed(world, status):
    reservation = world.reservation(status=status)
    client = world.client_for(world.requester)

    assert client.get(world.url(reservation)).status_code in (302, 403)
    assert client.post(world.url(reservation), data=all_scores()).status_code in (302, 403)
    assert models.CarReservationFeedback.objects.count() == 0


def test_a_second_submit_is_refused_and_the_first_response_is_kept(world):
    reservation = world.reservation()
    client = world.client_for(world.requester)
    client.post(world.url(reservation), data=all_scores(5))

    second = client.post(
        world.url(reservation), data=all_scores(1), follow_redirects=True
    )

    assert "ประเมินแล้ว" in second.get_data(as_text=True)
    assert models.CarReservationFeedback.objects(reservation=reservation).count() == 1
    saved = models.CarReservationFeedback.objects(reservation=reservation).first()
    assert saved.score_of("overall") == 5


def test_opening_the_form_again_after_answering_shows_it_is_already_done(world):
    reservation = world.reservation()
    client = world.client_for(world.requester)
    client.post(world.url(reservation), data=all_scores(5))

    response = client.get(world.url(reservation), follow_redirects=True)

    assert "ประเมินแล้ว" in response.get_data(as_text=True)


@pytest.mark.parametrize("missing", ["vehicle_cleanliness", "driver_route_study", "overall"])
def test_every_score_question_is_required(world, missing):
    reservation = world.reservation()
    data = all_scores(4)
    del data[missing]

    response = world.client_for(world.requester).post(world.url(reservation), data=data)

    assert response.status_code == 200
    assert "กรุณาให้คะแนน" in response.get_data(as_text=True)
    assert models.CarReservationFeedback.objects.count() == 0


@pytest.mark.parametrize("bad", ["0", "6", "abc"])
def test_scores_outside_1_to_5_are_refused(world, bad):
    reservation = world.reservation()

    response = world.client_for(world.requester).post(
        world.url(reservation), data=all_scores(4, overall=bad)
    )

    assert response.status_code == 200
    assert models.CarReservationFeedback.objects.count() == 0


def test_the_comment_is_optional(world):
    reservation = world.reservation()

    response = world.client_for(world.requester).post(
        world.url(reservation), data=all_scores(3)
    )

    assert response.status_code == 302
    assert models.CarReservationFeedback.objects.first().comment == ""


def detail_url(world, reservation):
    return (
        f"/car_reservation/requests/{reservation.id}?organization_id={world.org.id}"
    )


def test_detail_page_offers_the_survey_to_the_requester_of_a_completed_trip(world):
    reservation = world.reservation()

    html = (
        world.client_for(world.requester)
        .get(detail_url(world, reservation))
        .get_data(as_text=True)
    )

    assert "ประเมินความพึงพอใจ" in html
    assert f"/car_reservation/feedback/{reservation.id}?organization_id=" in html


def test_detail_page_says_already_rated_instead_of_offering_the_survey_twice(world):
    reservation = world.reservation()
    client = world.client_for(world.requester)
    client.post(world.url(reservation), data=all_scores())

    html = client.get(detail_url(world, reservation)).get_data(as_text=True)

    assert "ประเมินแล้ว" in html
    assert f"/car_reservation/feedback/{reservation.id}" not in html


@pytest.mark.parametrize("who", ["colleague", "org_admin"])
def test_detail_page_hides_the_survey_from_everyone_but_the_requester(world, who):
    reservation = world.reservation()

    html = (
        world.client_for(getattr(world, who))
        .get(detail_url(world, reservation))
        .get_data(as_text=True)
    )

    assert f"/car_reservation/feedback/{reservation.id}" not in html


def test_detail_page_hides_the_survey_until_the_trip_is_completed(world):
    reservation = world.reservation(status="active")

    html = (
        world.client_for(world.requester)
        .get(detail_url(world, reservation))
        .get_data(as_text=True)
    )

    assert f"/car_reservation/feedback/{reservation.id}" not in html


def test_my_requests_list_links_to_the_survey_then_shows_it_is_done(world):
    reservation = world.reservation()
    client = world.client_for(world.requester)
    list_url = f"/car_reservation/requests/?organization_id={world.org.id}"

    before = client.get(list_url).get_data(as_text=True)
    client.post(world.url(reservation), data=all_scores())
    after = client.get(list_url).get_data(as_text=True)

    assert f"/car_reservation/feedback/{reservation.id}?organization_id=" in before
    assert f"/car_reservation/feedback/{reservation.id}" not in after
    assert "ประเมินแล้ว" in after


def test_a_reservation_of_another_organization_is_not_found(world, create_org):
    other_org = create_org("Other Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    foreign = world.reservation(organization=other_org)
    client = world.client_for(world.requester)

    assert client.get(world.url(foreign)).status_code == 404
    assert client.post(world.url(foreign), data=all_scores()).status_code == 404
    assert models.CarReservationFeedback.objects.count() == 0


def save_feedback(world, reservation=None, days_ago=0, comment="", **scores):
    reservation = reservation or world.reservation()
    return models.CarReservationFeedback(
        organization=reservation.organization,
        reservation=reservation,
        creator=reservation.creator,
        car=reservation.car,
        driver=reservation.driver,
        scores=[
            models.car_reservation_feedback.FeedbackScore(
                key=key, score=int(all_scores(4, **scores)[key])
            )
            for key in SCORE_KEYS
        ],
        comment=comment,
        created_date=datetime.datetime.now() - datetime.timedelta(days=days_ago),
    ).save()


def results_url(world, period=None):
    url = f"{BASE}/?organization_id={world.org.id}"
    return url + (f"&period={period}" if period else "")


def test_org_admin_sees_each_response_with_plate_driver_overall_score_and_comment(world):
    feedback = save_feedback(world, overall=5, comment="บริการดีมาก")

    response = world.client_for(world.org_admin).get(results_url(world))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    row = html.split('data-role="feedback-row"')[1]
    assert feedback.created_date.strftime("%d/%m/%Y") in row
    for expected in ("กก 1234", "Driver Feedback", "บริการดีมาก"):
        assert expected in row
    assert 'data-overall="5"' in row


@pytest.mark.parametrize("who", ["requester", "colleague", "driver"])
def test_only_org_admins_open_the_results(world, who):
    save_feedback(world, comment="ลับเฉพาะผู้ดูแล")

    response = world.client_for(getattr(world, who)).get(results_url(world))

    assert response.status_code in (302, 403)
    assert "ลับเฉพาะผู้ดูแล" not in response.get_data(as_text=True)


def test_results_never_include_another_organizations_responses(world, create_org):
    other_org = create_org("Other Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    save_feedback(
        world,
        reservation=world.reservation(organization=other_org),
        comment="ขององค์กรอื่น",
    )

    html = world.client_for(world.org_admin).get(results_url(world)).get_data(as_text=True)

    assert "ขององค์กรอื่น" not in html


def test_driver_closing_the_trip_emails_the_requester_the_survey_link_job(
    world, mock_redis_queue
):
    reservation = world.reservation(status="active")

    response = world.client_for(world.driver).post(
        f"/car_reservation/tasks/{reservation.id}/close?organization_id={world.org.id}",
        data={"mileage_out": "0", "mileage_in": "120", "expense_case": "fleet_card"},
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


def test_completed_email_gives_the_requester_the_survey_link(app, world, sent_emails):
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
        f"https://staging.example.test/car_reservation/feedback/{reservation.id}"
        f"?organization_id={world.org.id}"
    ) in email["body"]
    assert "กก 1234" in email["body"]


def test_org_default_template_of_the_completed_email_can_use_feedback_url(
    app, world, sent_emails
):
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
        f"โปรดประเมินที่ https://staging.example.test/car_reservation/feedback/"
        f"{reservation.id}?organization_id={world.org.id}"
    )
