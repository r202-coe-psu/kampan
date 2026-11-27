"""แบบประเมินของคำขอที่จัดรถหลายคัน: ผลประเมินผูกกับคู่ (คำขอ, รถ) และ พขร. ของชุดที่รถตรงกัน"""

import datetime

import pytest

from kampan import models
from kampan.web.views.car_reservation import feedback as feedback_view

CARS_BASE = "/car_reservation/cars"
FEEDBACK_BASE = "/car_reservation/feedback"


@pytest.fixture
def fleet(
    app,
    create_org,
    create_user,
    assign_user_to_org,
    create_car,
    create_feedback_template,
    make_question,
    create_car_reservation,
):
    """คำขอหนึ่งใบที่จัดรถ 2 คัน (รถ A + พขร. 1, รถ B + พขร. 2) และแบบประเมินที่ผูกรถทั้งสองคัน"""
    org = create_org("Fleet Feedback Org")
    org.enabled_modules = ["car_reservation"]
    org.save()

    class World:
        pass

    w = World()
    w.org = org
    w.admin = create_user("Admin", "Fleet")
    assign_user_to_org(w.admin, org, roles=["admin"])
    w.driver_a = create_user("Alpha", "Driver")
    w.driver_b = create_user("Bravo", "Driver")
    w.car_a = create_car(org, "กก 1111")
    w.car_b = create_car(org, "ขข 2222")
    w.score = make_question("score", "ให้คะแนนบริการ", is_required=True)
    w.template = create_feedback_template(org, [w.car_a, w.car_b], questions=[w.score])
    w.reservation = create_car_reservation(
        org,
        assignments=[
            models.CarAssignment(car=w.car_a, driver=w.driver_a),
            models.CarAssignment(car=w.car_b, driver=w.driver_b),
        ],
        departure_datetime=datetime.datetime.now() - datetime.timedelta(hours=2),
        location="หาดใหญ่",
    )

    def answer(client, car, trip=None, score="4"):
        trip = trip or w.reservation
        return client.post(
            f"{CARS_BASE}/{car.id}/feedback?template_id={w.template.id}",
            data={"car_reservation": str(trip.id), f"answer_{w.score.question_id}": score},
        )

    w.answer = answer
    return w


def saved_pairs(world):
    return sorted(
        (str(r.car.license_plate), str(r.car_reservation.id))
        for r in models.CarFeedbackResponse.objects(feedback_template=world.template)
    )


def test_both_cars_of_one_request_can_be_answered_separately(app, fleet):
    with app.test_client() as client:
        first = fleet.answer(client, fleet.car_a)
        second = fleet.answer(client, fleet.car_b)

        assert first.status_code == 200 and second.status_code == 200
        assert saved_pairs(fleet) == [
            ("กก 1111", str(fleet.reservation.id)),
            ("ขข 2222", str(fleet.reservation.id)),
        ]


def test_several_passengers_can_answer_for_the_same_car_of_the_same_request(app, fleet):
    # รถบัสหนึ่งคันมีผู้โดยสารหลายคน แต่ละคนตอบได้ ไม่จำกัดหนึ่งคำตอบต่อ (คำขอ, รถ)
    with app.test_client() as client:
        assert fleet.answer(client, fleet.car_a).status_code == 200
        assert fleet.answer(client, fleet.car_a, score="1").status_code == 200

        assert models.CarFeedbackResponse.objects(car=fleet.car_a).count() == 2


def test_the_public_page_of_each_car_offers_the_trip_of_that_car_only(
    app, fleet, create_car, create_car_reservation
):
    with app.test_client() as client:
        other_car = create_car(fleet.org, "คค 3333")
        fleet.template.cars.append(other_car)
        fleet.template.save()
        unrelated = create_car_reservation(
            fleet.org,
            other_car,
            location="ภูเก็ต",
            departure_datetime=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        page_a = client.get(f"{CARS_BASE}/{fleet.car_a.id}/feedback").data.decode()
        page_other = client.get(f"{CARS_BASE}/{other_car.id}/feedback").data.decode()

        assert f'value="{fleet.reservation.id}"' in page_a
        assert f'value="{unrelated.id}"' not in page_a
        assert f'value="{fleet.reservation.id}"' not in page_other


def test_posting_a_trip_of_another_car_is_refused_even_when_the_request_has_two_cars(
    app, fleet, create_car, create_car_reservation
):
    with app.test_client() as client:
        stranger_car = create_car(fleet.org, "คค 3333")
        fleet.template.cars.append(stranger_car)
        fleet.template.save()
        create_car_reservation(  # รถคันนี้มีเที่ยวของตัวเอง ฟอร์มจึงบังคับเลือกเที่ยว
            fleet.org, stranger_car, departure_datetime=datetime.datetime.now()
        )

        response = fleet.answer(client, stranger_car)

        assert response.status_code == 200  # ฟอร์มไม่ผ่านการตรวจ ไม่บันทึกอะไร
        assert models.CarFeedbackResponse.objects.count() == 0


def test_the_driver_of_a_response_is_the_driver_of_the_assignment_with_that_car(fleet):
    trips = feedback_view.get_filter_trips([fleet.car_a, fleet.car_b], fleet.org)

    both = feedback_view.get_trip_drivers(trips, [fleet.car_a, fleet.car_b])
    only_a = feedback_view.get_trip_drivers(trips, [fleet.car_a])

    assert {d.id for d in both} == {fleet.driver_a.id, fleet.driver_b.id}
    assert [d.id for d in only_a] == [fleet.driver_a.id]


def test_pair_counts_separate_the_two_cars_of_one_request(fleet, create_feedback_response, make_answer):
    for car in (fleet.car_a, fleet.car_a, fleet.car_b):
        create_feedback_response(
            fleet.template, car, car_reservation=fleet.reservation, answers=[make_answer(fleet.score, score=5)]
        )

    counts = feedback_view.get_response_pair_counts(fleet.template)

    assert counts == {
        (str(fleet.reservation.id), str(fleet.car_a.id)): 2,
        (str(fleet.reservation.id), str(fleet.car_b.id)): 1,
    }


def test_driver_filter_keeps_only_the_responses_of_the_drivers_own_car(
    app, fleet, login_as, create_feedback_response, make_answer
):
    for car, value in ((fleet.car_a, 5), (fleet.car_b, 1)):
        create_feedback_response(
            fleet.template, car, car_reservation=fleet.reservation, answers=[make_answer(fleet.score, score=value)]
        )
    cars = [fleet.car_a, fleet.car_b]
    trips = feedback_view.get_filter_trips(cars, fleet.org)
    pairs = [(trips[0], fleet.car_a)]

    filter_kwargs = feedback_view.build_response_filter(fleet.template, cars, driver_trips=pairs)
    responses = models.CarFeedbackResponse.objects(**filter_kwargs)
    report = feedback_view.build_response_report(
        fleet.template, fleet.org, cars, trips, driver_trips=pairs
    )

    assert [r.car.license_plate for r in responses] == ["กก 1111"]
    assert [row["license_plate"] for row in report["response_log"]] == ["กก 1111"]
    assert report["summary"]["total_responses"] == 1


def test_view_filters_by_driver_through_the_page(app, fleet, login_as, create_feedback_response, make_answer):
    for car in (fleet.car_a, fleet.car_b):
        create_feedback_response(
            fleet.template, car, car_reservation=fleet.reservation, answers=[make_answer(fleet.score, score=4)]
        )
    with app.test_client() as client:
        login_as(client, fleet.admin)
        base = f"{FEEDBACK_BASE}/{fleet.template.id}/view?organization_id={fleet.org.id}"

        everyone = client.get(base).data.decode()
        filtered = client.get(f"{base}&driver_id={fleet.driver_a.id}").data.decode()

        assert f'value="{fleet.driver_a.id}"' in everyone and f'value="{fleet.driver_b.id}"' in everyone
        # ตัวเลือกเที่ยวนับเฉพาะผลของชุดที่ พขร. ที่เลือกขับ (รถ A) ไม่นับผลของรถ B
        assert "กก 1111 / ขข 2222 · หาดใหญ่ (2)" in everyone
        assert "กก 1111 · หาดใหญ่ (1)" in filtered
