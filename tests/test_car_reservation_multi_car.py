"""คำขอใช้รถหลายคัน (#73) ระดับ HTTP: ผู้จัดรถจัดหลายชุด ลดจำนวนคัน งานด่วน/งานแทรกแจ้ง พขร. ทุกคน
OT รายชุด ยืนยันเวลาปิดงานรายชุด รูปเลขไมล์รายชุด ใบขอ (PDF) รายชุด และลิงก์ประเมินทีละคัน"""

import datetime
import io

import pytest
from lxml import html as lxml_html

from kampan import models, utils
from kampan.utils import car_reservation_flow as flow
from kampan.utils import notifications
from tests.test_car_reservation import (  # noqa: F401
    BASE,
    CONFIRM_ENDED_AT,
    DAY,
    approve_url,
    assignment_id_of,
    confirmation_url,
    detail_url,
    dispatch_data,
    email_jobs,
    insert_data,
    insert_jobs,
    insert_url,
    insert_world,
    mock_redis_queue,
    overtime_url,
    post_insert,
    set_job_fields,
    slot_data,
    urgent_data,
    urgent_url,
    world,
)
from tests.test_car_reservation_tasks import PNG_BYTES


def events_of(user, org):
    return [n.event for n in notifications.inbox(user, org)]


@pytest.fixture
def fleet(world, create_car):
    """world + รถ/พขร. คันที่สองและสาม สำหรับจัดคำขอหลายคัน"""
    world.car2 = create_car(world.org, "ขข 5678", vehicle_type="ตู้")
    world.car3 = create_car(world.org, "คค 9012", vehicle_type="ตู้")
    world.driver2 = world.add_driver("Second", "Driver")
    world.driver3 = world.add_driver("Third", "Driver")
    return world


def request_at_dispatcher_for(world, vehicle_count):
    """คำขอในประเทศที่ขอ vehicle_count คัน รอผู้จัดรถ (หัวหน้าฝ่ายอนุมัติแล้ว)"""
    response = world.client_for(world.requester).post(
        f"{BASE}/new?organization_id={world.org.id}&type=domestic",
        data={**world.request_data(), "vehicle_count": str(vehicle_count)},
    )
    assert response.status_code == 302, response.get_data(as_text=True)
    reservation = (
        models.CarReservation.objects(creator=world.requester).order_by("-id").first()
    )
    world.client_for(world.supervisor).post(
        approve_url(world, reservation), data={"comment": ""}
    )
    reservation.reload()
    assert flow.current_step_key(reservation) == "dispatcher"
    return reservation


def two_car_data(world, comment="", **extra):
    return {
        "comment": comment,
        **slot_data(world.car, world.driver),
        **slot_data(world.car2, world.driver2, index=1),
        **extra,
    }


def dispatch(world, reservation, data):
    return world.client_for(world.dispatcher).post(
        approve_url(world, reservation), data=data
    )


def dispatch_and_read(world, reservation, data):
    """ส่งฟอร์มจัดรถแล้วตามไปหน้ารายละเอียดด้วย client เดิม (flash แสดงในหน้าถัดไป) คืน HTML"""
    response = world.client_for(world.dispatcher).post(
        approve_url(world, reservation), data=data, follow_redirects=True
    )
    assert response.status_code == 200
    return response.get_data(as_text=True)


def detail_html(world, reservation, user=None):
    return (
        world.client_for(user or world.requester)
        .get(detail_url(world, reservation))
        .get_data(as_text=True)
    )


# ---- ผู้จัดรถจัดหลายคัน ----------------------------------------------------


def test_dispatcher_form_renders_one_slot_per_requested_car_with_a_hint(fleet):
    reservation = request_at_dispatcher_for(fleet, 2)

    doc = lxml_html.fromstring(detail_html(fleet, reservation, fleet.dispatcher))

    slots = doc.xpath("//*[@data-role='assignment-slot']")
    assert len(slots) == 2
    for index in (0, 1):
        assert doc.xpath(f"//select[@name='assignments-{index}-car']")
        assert doc.xpath(f"//select[@name='assignments-{index}-driver']")
        assert doc.xpath(f"//input[@name='assignments-{index}-is_overtime']")
    assert not doc.xpath("//select[@name='assignments-2-car']")
    (hint,) = doc.xpath("//*[@data-role='vehicle-count-hint']")
    assert "ขอ 2 คัน" in hint.text_content()
    assert "ต้องใส่เหตุผล" in hint.text_content()
    assert doc.xpath("//textarea[@name='reduce_reason']")
    # คันแรกบังคับ คันถัดไปเว้นว่างได้
    (first_car,) = doc.xpath("//select[@name='assignments-0-car']")
    (second_car,) = doc.xpath("//select[@name='assignments-1-car']")
    assert first_car.get("required") is not None
    assert second_car.get("required") is None


def test_a_single_car_request_has_one_slot_and_no_reduce_reason_field(fleet):
    reservation = request_at_dispatcher_for(fleet, 1)

    doc = lxml_html.fromstring(detail_html(fleet, reservation, fleet.dispatcher))

    assert len(doc.xpath("//*[@data-role='assignment-slot']")) == 1
    assert not doc.xpath("//textarea[@name='reduce_reason']")


def test_dispatcher_assigns_two_cars_and_the_detail_shows_both_cards(fleet):
    reservation = request_at_dispatcher_for(fleet, 2)

    response = dispatch(
        fleet,
        reservation,
        {
            "comment": "",
            **slot_data(fleet.car, fleet.driver),
            **slot_data(fleet.car2, fleet.driver2, index=1, is_overtime=True),
        },
    )

    assert response.status_code == 302
    reservation.reload()
    assert [a.car for a in reservation.assignments] == [fleet.car, fleet.car2]
    assert [a.driver for a in reservation.assignments] == [fleet.driver, fleet.driver2]
    assert [a.is_overtime for a in reservation.assignments] == [False, True]
    assert reservation.current_step == 2
    doc = lxml_html.fromstring(detail_html(fleet, reservation))
    cards = doc.xpath("//*[@data-role='assignment']")
    assert len(cards) == 2
    first, second = (" ".join(c.text_content().split()) for c in cards)
    assert "รถคันที่ 1" in first and "กก 1234" in first and "Driver One" in first
    assert "รถคันที่ 2" in second and "ขข 5678" in second and "Second Driver" in second
    # OT รายชุด: ป้ายขึ้นเฉพาะคันที่ติ๊ก
    assert not cards[0].xpath(".//*[@data-role='overtime-badge']")
    assert cards[1].xpath(".//*[@data-role='overtime-badge']")


def test_every_assigned_driver_is_notified_in_the_app(fleet):
    reservation = request_at_dispatcher_for(fleet, 2)

    dispatch(fleet, reservation, two_car_data(fleet))

    assert events_of(fleet.driver, fleet.org) == ["driver_assigned"]
    assert events_of(fleet.driver2, fleet.org) == ["driver_assigned"]
    assert "driver_assigned" not in events_of(fleet.driver3, fleet.org)


def test_fewer_cars_than_requested_without_a_reason_is_refused(fleet, mock_redis_queue):
    reservation = request_at_dispatcher_for(fleet, 2)

    html = dispatch_and_read(fleet, reservation, dispatch_data(fleet.car, fleet.driver))

    reservation.reload()
    assert reservation.current_step == 1
    assert reservation.assignments == []
    assert reservation.details.vehicle_count == 2
    assert flow.REDUCE_REASON_REQUIRED in html
    assert email_jobs(mock_redis_queue, "vehicle_count_reduced") == []


def test_a_half_filled_slot_is_refused(fleet):
    reservation = request_at_dispatcher_for(fleet, 2)
    data = dispatch_data(fleet.car, fleet.driver)
    data["assignments-1-car"] = str(fleet.car2.id)  # คันที่ 2 เลือกรถแต่ไม่เลือก พขร.

    html = dispatch_and_read(fleet, reservation, {**data, "reduce_reason": "รถไม่พอ"})

    reservation.reload()
    assert reservation.current_step == 1
    assert reservation.assignments == []
    assert flow.CAR_AND_DRIVER_REQUIRED in html


@pytest.mark.parametrize(
    "slots, message",
    [
        ("car", flow.DUPLICATE_CAR),
        ("driver", flow.DUPLICATE_DRIVER),
    ],
)
def test_the_same_car_or_driver_twice_is_refused_with_a_flash(fleet, slots, message):
    reservation = request_at_dispatcher_for(fleet, 2)
    data = two_car_data(fleet)
    if slots == "car":
        data["assignments-1-car"] = str(fleet.car.id)
    else:
        data["assignments-1-driver"] = str(fleet.driver.id)

    html = dispatch_and_read(fleet, reservation, data)

    reservation.reload()
    assert reservation.current_step == 1
    assert message in html


def test_dispatcher_reduces_the_car_count_with_a_reason_and_the_requester_is_told(
    fleet, mock_redis_queue
):
    reservation = request_at_dispatcher_for(fleet, 2)

    response = dispatch(
        fleet,
        reservation,
        {**dispatch_data(fleet.car, fleet.driver), "reduce_reason": "รถอีกคันเข้าซ่อม"},
    )

    assert response.status_code == 302
    reservation.reload()
    assert len(reservation.assignments) == 1
    assert reservation.details.vehicle_count == 1
    reduced = [log for log in reservation.audit_logs if log.action == "vehicle_count_reduced"]
    assert [log.comment for log in reduced] == ["รถอีกคันเข้าซ่อม"]
    assert [(c.old, c.new) for c in reduced[0].changes] == [("2", "1")]
    # อีเมลถึงผู้ขอ บอกจำนวนที่ขอ/ที่จัดให้ และเหตุผล
    [email] = email_jobs(mock_redis_queue, "vehicle_count_reduced")
    request_id, _, recipients, _, variables = email
    assert request_id == str(reservation.id)
    assert recipients == [fleet.requester.email]
    assert (variables["requested_vehicle_count"], variables["assigned_vehicle_count"]) == (2, 1)
    assert variables["comment"] == "รถอีกคันเข้าซ่อม"
    assert "vehicle_count_reduced" in events_of(fleet.requester, fleet.org)


def test_assigning_the_full_count_does_not_send_a_reduced_notice(fleet, mock_redis_queue):
    reservation = request_at_dispatcher_for(fleet, 2)

    dispatch(fleet, reservation, two_car_data(fleet, reduce_reason="ไม่ได้ใช้"))

    reservation.reload()
    assert len(reservation.assignments) == 2
    assert email_jobs(mock_redis_queue, "vehicle_count_reduced") == []
    assert "vehicle_count_reduced" not in events_of(fleet.requester, fleet.org)
    assert not [l for l in reservation.audit_logs if l.action == "vehicle_count_reduced"]


def test_the_reduced_count_email_mentions_both_counts_and_the_reason(fleet):
    reservation = request_at_dispatcher_for(fleet, 2)
    dispatch(
        fleet,
        reservation,
        {**dispatch_data(fleet.car, fleet.driver), "reduce_reason": "รถอีกคันเข้าซ่อม"},
    )
    reservation.reload()

    variables = utils.car_reservation_email.template_variables(reservation, "http://x")
    subject, body = utils.car_reservation_email._render_file(
        "vehicle_count_reduced", variables
    )

    assert "น้อยกว่า" in subject
    assert "จำนวนรถที่ขอ: 2 คัน" in body
    assert "จำนวนรถที่จัดให้: 1 คัน" in body
    assert "รถอีกคันเข้าซ่อม" in body


# ---- งานด่วนและงานแทรก ------------------------------------------------------


def post_urgent(world, **overrides):
    return world.client_for(world.dispatcher).post(
        urgent_url(world), data=urgent_data(world, **overrides)
    )


def test_urgent_form_offers_five_slots_with_only_the_first_required(fleet):
    doc = lxml_html.fromstring(
        fleet.client_for(fleet.dispatcher).get(urgent_url(fleet)).get_data(as_text=True)
    )

    for index in range(5):
        assert doc.xpath(f"//select[@name='assignments-{index}-car']")
        assert doc.xpath(f"//select[@name='assignments-{index}-driver']")
    assert not doc.xpath("//select[@name='assignments-5-car']")
    (first,) = doc.xpath("//select[@name='assignments-0-car']")
    (second,) = doc.xpath("//select[@name='assignments-1-car']")
    assert first.get("required") is not None and second.get("required") is None
    # คันที่ 2 เป็นต้นไปพับไว้ใน <details>
    assert len(doc.xpath("//details[@data-role='assignment-slot']")) == 4


def test_urgent_request_with_two_cars_assigns_both_and_tells_both_drivers(fleet):
    response = post_urgent(
        fleet, vehicle_count="2", **slot_data(fleet.car2, fleet.driver2, index=1)
    )

    assert response.status_code == 302, response.get_data(as_text=True)
    [reservation] = models.CarReservation.objects(organization=fleet.org)
    assert [a.car for a in reservation.assignments] == [fleet.car, fleet.car2]
    assert [a.driver for a in reservation.assignments] == [fleet.driver, fleet.driver2]
    assert reservation.details.vehicle_count == 2
    assert reservation.status == "pending"
    assert events_of(fleet.driver, fleet.org) == ["driver_assigned"]
    assert events_of(fleet.driver2, fleet.org) == ["driver_assigned"]


def test_urgent_request_with_one_car_notifies_its_driver(fleet):
    response = post_urgent(fleet)

    assert response.status_code == 302, response.get_data(as_text=True)
    assert events_of(fleet.driver, fleet.org) == ["driver_assigned"]
    assert events_of(fleet.driver2, fleet.org) == []


def test_urgent_must_assign_exactly_the_vehicle_count_entered(fleet):
    # ขอ 2 แต่จัดคันเดียว: ผู้จัดรถเป็นผู้ขอเอง ไม่มีทางลดจำนวน
    response = post_urgent(fleet, vehicle_count="2")

    assert response.status_code == 200
    assert "ให้ครบ 2 คัน" in response.get_data(as_text=True)
    assert models.CarReservation.objects(organization=fleet.org).count() == 0


def test_urgent_with_more_assignments_than_the_vehicle_count_is_refused(fleet):
    response = post_urgent(
        fleet, vehicle_count="1", **slot_data(fleet.car2, fleet.driver2, index=1)
    )

    assert response.status_code == 200
    assert "ให้ครบ 1 คัน" in response.get_data(as_text=True)
    assert models.CarReservation.objects(organization=fleet.org).count() == 0


def test_urgent_with_a_half_filled_slot_is_refused(fleet):
    response = post_urgent(
        fleet,
        vehicle_count="2",
        **{"assignments-1-car": str(fleet.car2.id)},
    )

    assert response.status_code == 200
    assert models.CarReservation.objects(organization=fleet.org).count() == 0


def test_urgent_with_the_same_car_twice_shows_the_flow_error(fleet):
    response = post_urgent(
        fleet, vehicle_count="2", **slot_data(fleet.car, fleet.driver2, index=1)
    )

    assert response.status_code == 200
    assert flow.DUPLICATE_CAR in response.get_data(as_text=True)
    assert models.CarReservation.objects(organization=fleet.org).count() == 0


def test_urgent_form_caps_the_vehicle_count_at_the_slots_it_shows(fleet):
    response = post_urgent(fleet, vehicle_count="6")

    assert response.status_code == 200
    assert "ไม่เกิน 5 คัน" in response.get_data(as_text=True)
    assert models.CarReservation.objects(organization=fleet.org).count() == 0


def test_insert_job_tells_its_driver_in_the_app_and_by_email(insert_world, mock_redis_queue):
    response = post_insert(insert_world)

    assert response.status_code == 302, response.get_data(as_text=True)
    [job] = insert_jobs(insert_world)
    assert "driver_assigned" in events_of(insert_world.driver, insert_world.org)
    [email] = email_jobs(mock_redis_queue, "active")
    assert email[0] == str(job.id)
    assert insert_world.driver.email in email[2]


# ---- OT รายชุด -------------------------------------------------------------


def pending_two_cars(world):
    """คำขอ 2 คันที่จัดแล้ว ยังรอผู้อนุมัติขั้นถัดไป (แก้ OT ได้)"""
    reservation = request_at_dispatcher_for(world, 2)
    dispatch(world, reservation, two_car_data(world))
    reservation.reload()
    assert reservation.status == "pending"
    return reservation


def test_overtime_is_set_per_assignment(fleet):
    reservation = pending_two_cars(fleet)
    second = reservation.assignments[1]

    response = fleet.client_for(fleet.dispatcher).post(
        overtime_url(fleet, reservation, second), data={"is_overtime": "y"}
    )

    assert response.status_code == 302
    reservation.reload()
    assert [a.is_overtime for a in reservation.assignments] == [False, True]
    log = reservation.audit_logs[-1]
    assert log.action == "overtime_changed"
    assert "ขข 5678" in log.comment


def test_detail_has_one_overtime_form_per_assignment_for_the_dispatcher(fleet):
    reservation = pending_two_cars(fleet)

    doc = lxml_html.fromstring(detail_html(fleet, reservation, fleet.dispatcher))

    forms = doc.xpath("//form[@data-role='overtime-form']")
    assert [f.get("action").split("?")[0].rsplit("/", 1)[1] for f in forms] == [
        str(a.assignment_id) for a in reservation.assignments
    ]
    # ผู้ขอไม่เห็นฟอร์ม OT
    other = lxml_html.fromstring(detail_html(fleet, reservation))
    assert not other.xpath("//form[@data-role='overtime-form']")


def test_overtime_route_404s_for_an_unknown_assignment(fleet):
    reservation = pending_two_cars(fleet)
    other = request_at_dispatcher_for(fleet, 1)
    dispatch(fleet, other, dispatch_data(fleet.car3, fleet.driver3))
    other.reload()

    response = fleet.client_for(fleet.dispatcher).post(
        overtime_url(fleet, reservation, other.assignments[0]), data={"is_overtime": "y"}
    )

    assert response.status_code == 404
    other.reload()
    assert other.has_overtime is False


def test_overtime_of_every_assignment_locks_once_fully_approved(fleet):
    reservation = pending_two_cars(fleet)
    while reservation.status == "pending":
        key = flow.current_step_key(reservation)
        fleet.client_for(fleet.holders[key]).post(
            approve_url(fleet, reservation), data={"comment": ""}
        )
        reservation.reload()
    assert reservation.status == "active"

    for assignment in reservation.assignments:
        response = fleet.client_for(fleet.dispatcher).post(
            overtime_url(fleet, reservation, assignment), data={"is_overtime": "y"}
        )
        assert response.status_code in (302, 403)

    reservation.reload()
    assert reservation.has_overtime is False


# ---- ยืนยันเวลาปิดงานรายชุด -------------------------------------------------


def closed_two_car_trip(world, closed_second=True):
    """คำขอ 2 คัน active: ชุดแรกปิดแล้ว (เมื่อวาน) ชุดที่สองปิดแล้วหรือยังไม่ปิด"""
    reservation = models.CarReservation(
        organization=world.org,
        creator=world.requester,
        request_type="domestic",
        province_scope="in_province",
        location="ที่ไกล",
        request_reason="ประชุม",
        departure_datetime=DAY,
        return_datetime=DAY + datetime.timedelta(hours=9),
        status="active",
        route_snapshot=["supervisor", "dispatcher", "vehicle_unit_head"],
        current_step=3,
        assignments=[
            models.CarAssignment(car=world.car, driver=world.driver),
            models.CarAssignment(car=world.car2, driver=world.driver2),
        ],
    )
    completed = CONFIRM_ENDED_AT - datetime.timedelta(days=1)
    for assignment in reservation.assignments[: 2 if closed_second else 1]:
        assignment.started_at = completed - datetime.timedelta(hours=3)
        assignment.completed_at = completed
    if closed_second:
        reservation.status = "completed"
    return reservation.save()


def test_close_confirmation_cards_exist_only_for_closed_assignments(fleet):
    reservation = closed_two_car_trip(fleet, closed_second=False)

    doc = lxml_html.fromstring(detail_html(fleet, reservation))

    sections = doc.xpath("//*[@data-role='close-confirmation']")
    assert len(sections) == 1
    assert sections[0].get("data-status") == "pending"
    assert "รถคันที่ 1" in sections[0].text_content()


def test_requester_answers_each_assignment_separately(fleet):
    reservation = closed_two_car_trip(fleet)
    first, second = reservation.assignments
    client = fleet.client_for(fleet.requester)

    ok = client.post(
        confirmation_url(fleet, reservation, first), data={"decision": "correct"}
    )
    assert ok.status_code == 302
    reservation.reload()
    statuses = [a.close_confirmation_status() for a in reservation.assignments]
    assert statuses == ["confirmed", "pending"]

    dispute = client.post(
        confirmation_url(fleet, reservation, second),
        data={
            "decision": "incorrect",
            "actual_end_date": CONFIRM_ENDED_AT.date().isoformat(),
            "actual_end_time": "20:30",
            "note": "คันที่สองกลับช้า",
        },
    )
    assert dispute.status_code == 302
    reservation.reload()
    statuses = [a.close_confirmation_status() for a in reservation.assignments]
    assert statuses == ["confirmed", "disputed"]
    # ตอบได้ครั้งเดียวต่อชุด
    again = client.post(
        confirmation_url(fleet, reservation, first), data={"decision": "incorrect"}
    )
    assert again.status_code in (302, 403)
    reservation.reload()
    assert reservation.assignments[0].close_confirmation == "confirmed"


def test_the_3_day_window_runs_per_assignment(fleet):
    reservation = closed_two_car_trip(fleet)
    reservation.assignments[0].completed_at = CONFIRM_ENDED_AT - datetime.timedelta(days=5)
    reservation.save()
    client = fleet.client_for(fleet.requester)

    late = client.post(
        confirmation_url(fleet, reservation, reservation.assignments[0]),
        data={"decision": "correct"},
    )
    on_time = client.post(
        confirmation_url(fleet, reservation, reservation.assignments[1]),
        data={"decision": "correct"},
    )

    assert late.status_code in (302, 403)  # acl แปลง 403 บางกรณีเป็น redirect: ดูที่ค่าที่บันทึก
    assert on_time.status_code == 302
    reservation.reload()
    assert reservation.assignments[0].close_confirmation is None
    assert reservation.assignments[1].close_confirmation == "confirmed"


def test_close_confirmation_route_404s_for_an_unknown_assignment(fleet):
    reservation = closed_two_car_trip(fleet)
    other = closed_two_car_trip(fleet)

    response = fleet.client_for(fleet.requester).post(
        confirmation_url(fleet, reservation, other.assignments[0]),
        data={"decision": "correct"},
    )

    assert response.status_code == 404


def test_a_closed_assignment_of_a_still_active_request_can_be_answered(fleet):
    reservation = closed_two_car_trip(fleet, closed_second=False)

    response = fleet.client_for(fleet.requester).post(
        confirmation_url(fleet, reservation), data={"decision": "correct"}
    )

    assert response.status_code == 302
    reservation.reload()
    assert reservation.assignments[0].close_confirmation == "confirmed"
    assert reservation.status == "active"


# ---- รูปเลขไมล์รายชุด -------------------------------------------------------


def photo_url(world, reservation, assignment, side):
    return (
        f"{BASE}/{reservation.id}/mileage_photo/{assignment.assignment_id}/{side}"
        f"?organization_id={world.org.id}"
    )


def test_mileage_photo_route_serves_the_photo_of_the_assignment_in_the_url(fleet):
    reservation = closed_two_car_trip(fleet)
    first, second = reservation.assignments
    first.mileage_photo_in.put(
        io.BytesIO(PNG_BYTES), filename="a.png", content_type="image/png"
    )
    reservation.save()
    client = fleet.client_for(fleet.requester)

    ok = client.get(photo_url(fleet, reservation, first, "in"))
    missing = client.get(photo_url(fleet, reservation, second, "in"))

    assert ok.status_code == 200 and ok.data == PNG_BYTES
    assert missing.status_code == 404  # คันที่ 2 ยังไม่มีรูป ไม่ใช้รูปของคันแรกแทน


def test_mileage_photo_route_404s_for_an_unknown_assignment_and_403s_strangers(
    fleet, create_user, assign_user_to_org
):
    reservation = closed_two_car_trip(fleet)
    first = reservation.assignments[0]
    first.mileage_photo_in.put(
        io.BytesIO(PNG_BYTES), filename="a.png", content_type="image/png"
    )
    reservation.save()
    other = closed_two_car_trip(fleet)
    colleague = create_user("Col", "League")
    assign_user_to_org(colleague, fleet.org, roles=["staff"])

    unknown = fleet.client_for(fleet.requester).get(
        photo_url(fleet, reservation, other.assignments[0], "in")
    )
    forbidden = fleet.client_for(colleague).get(photo_url(fleet, reservation, first, "in"))

    assert unknown.status_code == 404
    assert forbidden.status_code in (302, 403)
    # พขร. ของอีกคันก็เป็นผู้เกี่ยวข้องกับเที่ยวนี้ (can_view_mileage_photos)
    assert (
        fleet.client_for(fleet.driver2)
        .get(photo_url(fleet, reservation, first, "in"))
        .status_code
        == 200
    )


def test_detail_shows_each_assignments_own_trip_report_and_photo_button(fleet):
    reservation = closed_two_car_trip(fleet)
    for number, assignment in enumerate(reservation.assignments):
        assignment.last_mileage_before = 1000 * (number + 1)
        assignment.last_mileage = 1000 * (number + 1) + 50 + number
    reservation.assignments[0].mileage_photo_in.put(
        io.BytesIO(PNG_BYTES), filename="a.png", content_type="image/png"
    )
    reservation.save()

    doc = lxml_html.fromstring(detail_html(fleet, reservation))

    reports = doc.xpath("//*[@data-role='trip-report']")
    assert len(reports) == 2
    assert "50" in reports[0].text_content() and "51" in reports[1].text_content()
    first_id = reservation.assignments[0].assignment_id
    assert f"/mileage_photo/{first_id}/in" in lxml_html.tostring(reports[0], encoding="unicode")
    assert not reports[1].xpath(".//*[@data-role='open-mileage-photo']")


# ---- ใบขอ (PDF) รายชุด -----------------------------------------------------


def paper_url(world, reservation, assignment=None):
    base = f"{BASE}/{reservation.id}/paper"
    if assignment is not None:
        base += f"/{assignment.assignment_id}"
    return f"{base}?organization_id={world.org.id}"


def test_the_bare_paper_route_still_returns_a_pdf_for_the_first_assignment(fleet):
    reservation = closed_two_car_trip(fleet)

    response = fleet.client_for(fleet.requester).get(paper_url(fleet, reservation))

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_paper_route_per_assignment_returns_a_pdf(fleet):
    reservation = closed_two_car_trip(fleet)

    response = fleet.client_for(fleet.requester).get(
        paper_url(fleet, reservation, reservation.assignments[1])
    )

    assert response.status_code == 200 and response.mimetype == "application/pdf"


def test_paper_route_404s_for_an_assignment_of_another_request(fleet):
    reservation = closed_two_car_trip(fleet)
    other = closed_two_car_trip(fleet)

    response = fleet.client_for(fleet.requester).get(
        paper_url(fleet, reservation, other.assignments[0])
    )

    assert response.status_code == 404


def test_paper_route_keeps_its_role_check_for_every_assignment(
    fleet, create_user, assign_user_to_org
):
    reservation = closed_two_car_trip(fleet)
    colleague = create_user("Col", "League")
    assign_user_to_org(colleague, fleet.org, roles=["staff"])

    response = fleet.client_for(colleague).get(
        paper_url(fleet, reservation, reservation.assignments[1])
    )

    assert response.status_code in (302, 403)


def test_pdf_modal_has_one_button_per_assignment_and_a_single_url_for_one_car(fleet):
    two = closed_two_car_trip(fleet)
    doc = lxml_html.fromstring(detail_html(fleet, two))
    buttons = doc.xpath("//dialog[@id='paper-preview-modal']//*[@data-role='paper-assignment']")
    assert [b.get("data-src").split("?")[0] for b in buttons] == [
        f"{BASE}/{two.id}/paper/{a.assignment_id}" for a in two.assignments
    ]
    # ชุดเดียวใช้ URL ใบเดียว (ไม่มีปุ่มเลือก)
    one = request_at_dispatcher_for(fleet, 1)
    dispatch(fleet, one, dispatch_data(fleet.car3, fleet.driver3))
    one.reload()
    one_doc = lxml_html.fromstring(detail_html(fleet, one))
    (modal,) = one_doc.xpath("//dialog[@id='paper-preview-modal']")
    assert modal.get("data-src").split("?")[0] == f"{BASE}/{one.id}/paper"
    assert not one_doc.xpath("//*[@data-role='paper-assignment']")


# ---- ลิงก์ประเมินทีละคัน ----------------------------------------------------


def survey_for(world, *cars):
    world_survey = models.CarFeedbackTemplate(
        organization=world.org,
        name="แบบประเมิน",
        cars=list(cars),
    )
    return world_survey.save()


def test_feedback_links_list_one_link_per_car_with_a_survey(fleet, app):
    from kampan.web.views.car_reservation import feedback as feedback_view

    reservation = closed_two_car_trip(fleet)
    survey_for(fleet, fleet.car, fleet.car2)

    with app.test_request_context(
        f"/car_reservation/requests/{reservation.id}?organization_id={fleet.org.id}"
    ):
        links = feedback_view.get_requester_feedback_links(reservation, fleet.requester)
        single = feedback_view.get_requester_feedback_url(reservation, fleet.requester)
        stranger = feedback_view.get_requester_feedback_links(reservation, fleet.driver)

    assert [link["car"] for link in links] == [fleet.car, fleet.car2]
    assert [link["assignment"] for link in links] == list(reservation.assignments)
    assert all(
        f"/cars/{link['car'].id}/feedback" in link["url"]
        and f"reservation_id={reservation.id}" in link["url"]
        for link in links
    )
    assert single == links[0]["url"]
    assert stranger == []


def test_feedback_links_skip_cars_without_a_survey_and_unfinished_requests(fleet, app):
    from kampan.web.views.car_reservation import feedback as feedback_view

    done = closed_two_car_trip(fleet)
    survey_for(fleet, fleet.car2)
    unfinished = closed_two_car_trip(fleet, closed_second=False)

    with app.test_request_context(
        f"/car_reservation/requests/{done.id}?organization_id={fleet.org.id}"
    ):
        links = feedback_view.get_requester_feedback_links(done, fleet.requester)
        none = feedback_view.get_requester_feedback_links(unfinished, fleet.requester)
        no_link = feedback_view.get_requester_feedback_url(unfinished, fleet.requester)

    assert [link["car"] for link in links] == [fleet.car2]
    assert none == [] and no_link is None


def test_detail_callout_shows_one_feedback_button_per_car(fleet):
    reservation = closed_two_car_trip(fleet)
    survey_for(fleet, fleet.car, fleet.car2)

    doc = lxml_html.fromstring(detail_html(fleet, reservation))

    buttons = doc.xpath("//*[@data-role='feedback-callout']//a[@data-role='feedback-link']")
    assert [b.get("data-car-id") for b in buttons] == [str(fleet.car.id), str(fleet.car2.id)]
    assert "กก 1234" in buttons[0].text_content()
    assert "ขข 5678" in buttons[1].text_content()
