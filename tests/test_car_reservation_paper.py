"""ใบขอใช้รถ (พิมพ์ PDF): เติมข้อมูลคำขอลงแบบฟอร์มทางการของแต่ละประเภท พร้อมชื่อ/ลายเซ็นผู้อนุมัติ"""

import datetime
import decimal
import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from PyPDF2 import PdfReader

from kampan import models
from kampan.utils import car_reservation_flow as flow
from kampan.web import redis_rq

BASE = "/car_reservation/requests"

APPROVAL_ROLE_KEYS = [
    "dispatcher",
    "vehicle_unit_head",
    "strategy_head",
    "physical_director",
    "vice_president_hatyai",
    "president",
]


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """อนุมัติแล้วระบบส่งอีเมลเข้าคิว: กันการต่อ Redis จริง"""
    with patch.object(redis_rq.redis_queue, "queue", MagicMock(), create=True):
        yield


def type_details(request_type):
    D = models.car_reservations
    if request_type == "domestic":
        return D.DomesticDetails(
            vehicle_kind="ตู้",
            vehicle_count=1,
            district="หาดใหญ่",
            province="สงขลา",
            in_office_of_president=True,
            cost_responsibilities=[D.COST_FUEL, D.COST_ALLOWANCE],
        )
    if request_type == "airport":
        return D.AirportDetails(
            transfer="pickup",
            flight_number="TG 123",
            flight_date=datetime.date(2026, 12, 3),
            arrival_time="09:10",
            passengers=[
                D.AirportPassenger(name="นภา รักดี", phone="081-000-1111"),
                D.AirportPassenger(name="ปราณี มีสุข", phone="082-000-2222"),
            ],
            requester_position="อาจารย์",
            in_office_of_president=True,
            cost_responsibilities=[D.COST_FUEL],
        )
    if request_type == "welfare":
        return D.WelfareDetails(
            employee_type="พนักงานมหาวิทยาลัย",
            affiliation="กองกายภาพและสิ่งแวดล้อม",
            vehicle_kind="ตู้",
            event_type="อุปสมบท",
            host_name="นายสมศักดิ์ ใจดี",
            house="12/3",
            subdistrict="คอหงส์",
            district="หาดใหญ่",
            province="สงขลา",
        )
    return D.AbroadDetails(
        section="คณะวิศวกรรมศาสตร์",
        document_number="ศธ 0521.1/123",
        vehicle_kind="ตู้",
        vehicle_count=1,
        city_state="กัวลาลัมเปอร์",
        country="มาเลเซีย",
        coordinator_name="นายประสาน งานดี",
        coordinator_phone="081-999-8888",
        requester_position="คณบดี",
    )


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (200, 80), (10, 10, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def pdf_page(response):
    return PdfReader(io.BytesIO(response.data)).pages[0]


def pdf_text(response):
    return pdf_page(response).extract_text()


def image_count(response):
    xobjects = pdf_page(response)["/Resources"].get("/XObject")
    if xobjects is None:
        return 0
    return sum(
        1
        for ref in xobjects.get_object().values()
        if ref.get_object().get("/Subtype") == "/Image"
    )


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Paper Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.division = models.Division(name="ฝ่ายบริการ", organization=org).save()
    s.other_division = models.Division(name="ฝ่ายอื่น", organization=org).save()

    def member(first, last, roles, division=None):
        user = create_user(first, last)
        membership = assign_user_to_org(user, org, roles=roles)
        if division is not None:
            membership.division = division
            membership.save()
        return user

    s.requester = member("สมชาย", "ใจดี", ["staff"], s.division)
    s.supervisor = member("ประเสริฐ", "มีสุข", ["head"], s.division)
    s.other_head = member("วิชัย", "หัวหน้า", ["head"], s.other_division)
    s.stranger = member("คนนอก", "ฝ่ายอื่น", ["staff"], s.other_division)
    s.org_admin = member("ผู้ดูแล", "ระบบ", ["admin"])
    s.holders = {"supervisor": s.supervisor}
    for key, first in zip(
        APPROVAL_ROLE_KEYS,
        ["สุธีรพร", "กนกดาริน", "ยุทธนา", "นิติธร", "วศิน", "นิวัติ"],
    ):
        s.holders[key] = member(first, "ผู้อนุมัติ", [key])
    s.dispatcher = s.holders["dispatcher"]
    s.driver = member("สมศักดิ์", "ขับดี", ["driver"])
    s.car = create_car(org, "กก 1234", vehicle_type="ตู้")

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for

    def reservation(request_type="domestic", approved_steps=None, province_scope=None):
        """คำขอที่ยื่นแล้วและเดินผ่าน `approved_steps` ขั้นแรก (ไม่ระบุ = ครบทุกขั้น)"""
        if request_type == "domestic" and province_scope is None:
            province_scope = "in_province"
        app_ = models.CarReservation(
            organization=org,
            division=s.division,
            creator=s.requester,
            requester_unit="คณะวิศวกรรมศาสตร์",
            phone="081-234-5678",
            request_type=request_type,
            province_scope=province_scope,
            location="ปีนัง ประเทศมาเลเซีย" if request_type == "abroad" else "กรุงเทพฯ",
            request_reason="ประชุมวิชาการ",
            departure_datetime=datetime.datetime(2026, 12, 3, 8, 30),
            return_datetime=datetime.datetime(2026, 12, 4, 17, 0),
            passenger_number=3,
            pickup_place="หน้าอาคารสำนักงานอธิการบดี",
            pickup_time="07:30",
            details=type_details(request_type),
        ).save()
        flow.submit(app_, s.requester)
        steps = list(app_.route_snapshot)
        if approved_steps is not None:
            steps = steps[:approved_steps]
        for key in steps:
            kwargs = {"car": s.car, "driver": s.driver} if key == "dispatcher" else {}
            flow.approve(app_, s.holders[key], **kwargs)
        return app_

    s.reservation = reservation

    def paper(user, reservation_):
        return client_for(user).get(
            f"{BASE}/{reservation_.id}/paper?organization_id={org.id}"
        )

    s.paper = paper
    return s


def test_requester_gets_the_official_form_filled_with_the_request_and_approvals(world):
    reservation = world.reservation("domestic")

    response = world.paper(world.requester, reservation)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    text = pdf_text(response)
    assert "ไปปฏิบัติงานภายในประเทศ" in text  # แบบฟอร์มต้นฉบับ
    assert "สมชาย ใจดี" in text  # ผู้ขอ
    assert "กรุงเทพฯ" in text  # สถานที่
    assert "กก 1234" in text  # ทะเบียนรถที่ผู้จัดรถเลือก
    assert "ประเสริฐ มีสุข" in text  # ผู้บังคับบัญชาที่อนุมัติ


def test_an_approvers_signature_image_is_placed_on_the_form(world):
    reservation = world.reservation("domestic", approved_steps=1)  # ผู้บังคับบัญชาอนุมัติแล้ว
    before = image_count(world.paper(world.requester, reservation))
    world.supervisor.signature.put(
        io.BytesIO(png_bytes()), filename="sign.png", content_type="image/png"
    )
    world.supervisor.save()

    after = image_count(world.paper(world.requester, reservation))

    assert (before, after) == (0, 1)


def test_a_step_that_has_not_approved_yet_is_left_blank(world):
    reservation = world.reservation("domestic", approved_steps=1)

    text = pdf_text(world.paper(world.requester, reservation))

    assert "ประเสริฐ มีสุข" in text  # ผู้บังคับบัญชาอนุมัติแล้ว
    assert "สุธีรพร ผู้อนุมัติ" not in text  # ผู้จัดรถยังไม่ถึงขั้น
    assert "กก 1234" not in text  # ยังไม่ได้จัดรถ


@pytest.mark.parametrize(
    "who", ["requester", "supervisor", "other_head", "dispatcher", "org_admin"]
)
def test_the_requester_approvers_dispatcher_and_admin_may_print_the_form(world, who):
    reservation = world.reservation("domestic")

    response = world.paper(getattr(world, who), reservation)

    assert response.status_code == 200


def test_an_unrelated_member_is_refused_the_form(world):
    reservation = world.reservation("domestic")

    response = world.paper(world.stranger, reservation)

    assert response.status_code in (302, 403)


@pytest.mark.parametrize(
    "request_type, shown",
    [
        ("airport", ["TG 123", "นภา รักดี", "081-000-1111", "อาจารย์"]),
        ("welfare", ["นายสมศักดิ์ ใจดี", "คอหงส์", "กก 1234"]),
        ("abroad", ["มาเลเซีย", "กัวลาลัมเปอร์", "นายประสาน งานดี", "ศธ 0521.1/123"]),
    ],
)
def test_each_request_type_fills_its_own_form_with_its_type_specific_details(
    world, request_type, shown
):
    reservation = world.reservation(request_type)

    response = world.paper(world.requester, reservation)

    assert response.status_code == 200
    text = pdf_text(response)
    for expected in shown:
        assert expected in text


def complete_trip(reservation, km_out=1000, km_in=1250, cost="1500"):
    assignment = reservation.assignments[0]
    assignment.last_mileage_before = km_out
    assignment.last_mileage = km_in
    assignment.cost_baht = decimal.Decimal(cost)
    assignment.started_at = datetime.datetime(2026, 12, 3, 8, 45)
    assignment.completed_at = datetime.datetime(2026, 12, 4, 17, 10)
    reservation.save()
    return reservation


def test_a_completed_trip_fills_the_trip_report_line_at_the_bottom_of_the_form(world):
    reservation = complete_trip(world.reservation("domestic"))

    text = pdf_text(world.paper(world.requester, reservation))

    for expected in ("1000", "1250", "250", "1,500"):  # กม.ออก, กม.กลับ, ระยะทางรวม, เป็นเงิน
        assert expected in text


def test_a_trip_that_is_not_completed_leaves_the_trip_report_line_blank(world):
    reservation = world.reservation("domestic")

    text = pdf_text(world.paper(world.requester, reservation))

    assert "1,500" not in text
    assert "1250" not in text


def test_a_completed_welfare_trip_also_fills_its_times_and_duration(world):
    reservation = complete_trip(world.reservation("welfare"), km_out=500, km_in=640, cost="2750.5")

    text = pdf_text(world.paper(world.requester, reservation))

    for expected in ("500", "640", "140", "2,750.50", "08:45", "17:10"):
        assert expected in text
    assert "32" in text and "25" in text  # 08:45 -> 17:10 วันถัดไป = 32 ชั่วโมง 25 นาที


@pytest.mark.parametrize("request_type", ["domestic", "airport", "welfare", "abroad"])
def test_the_requesters_own_signature_image_is_placed_on_the_form(world, request_type):
    reservation = world.reservation(request_type, approved_steps=0)
    before = image_count(world.paper(world.requester, reservation))
    world.requester.signature.put(
        io.BytesIO(png_bytes()), filename="sign.png", content_type="image/png"
    )
    world.requester.save()

    after = image_count(world.paper(world.requester, reservation))

    assert after == before + 1  # แบบฟอร์มต่างประเทศมีตราครุฑอยู่ในต้นฉบับแล้ว


def page_content(response):
    return pdf_page(response).get_contents().get_data()


def test_the_attention_circle_to_the_physical_director_is_ticked_only_when_the_route_reaches_him(
    world,
):
    in_province = world.reservation("domestic", approved_steps=0)
    out_of_province = world.reservation(
        "domestic", approved_steps=0, province_scope="out_of_province"
    )

    plain = page_content(world.paper(world.requester, in_province))
    ticked = page_content(world.paper(world.requester, out_of_province))

    assert len(ticked) > len(plain)  # เครื่องหมายถูกเป็นเส้นที่วาดเพิ่ม (ตำแหน่งตรวจดูด้วยตา)


def test_detail_page_offers_the_pdf_preview_only_to_users_who_may_print(world):
    reservation = world.reservation("domestic")
    url = f"{BASE}/{reservation.id}?organization_id={world.org.id}"

    for user, offered in ((world.requester, True), (world.stranger, False)):
        html = world.client_for(user).get(url).get_data(as_text=True)
        assert ('data-role="preview-paper"' in html) is offered


@pytest.mark.parametrize(
    "request_type, province_scope, unprinted",
    [
        ("domestic", "in_province", ["กนกดาริน"]),  # หัวหน้าหน่วยยานพาหนะ
        ("airport", None, ["กนกดาริน"]),
        ("welfare", None, ["กนกดาริน", "ยุทธนา"]),  # + หัวหน้างานยุทธศาสตร์
        ("abroad", None, ["กนกดาริน", "ยุทธนา", "วศิน"]),  # + รองอธิการบดี
    ],
)
def test_steps_without_a_signature_box_on_the_official_form_are_not_printed(
    world, request_type, province_scope, unprinted
):
    # ตัดสินแล้ว: ขั้นที่แบบฟอร์มจริงไม่มีช่องลงนาม ไม่พิมพ์ (ดูได้ในประวัติการดำเนินการ)
    reservation = world.reservation(request_type, province_scope=province_scope)

    text = pdf_text(world.paper(world.requester, reservation))

    for name in unprinted:
        assert name not in text


def two_car_trip(world, create_car, create_user, assign_user_to_org):
    """คำขอที่จัด 2 ชุด: ชุดแรกรถ/พขร. ในห้อง world ชุดสองรถและ พขร. อีกคู่ ปิดงานแยกกันคนละเลขไมล์"""
    reservation = complete_trip(world.reservation("domestic"), km_out=1000, km_in=1250, cost="1500")
    second_driver = create_user("สมหมาย", "ขับเก่ง")
    assign_user_to_org(second_driver, world.org, roles=["driver"])
    second = models.CarAssignment(
        car=create_car(world.org, "ขข 9999", vehicle_type="เก๋ง"),
        driver=second_driver,
        last_mileage_before=40,
        last_mileage=90,
        cost_baht=decimal.Decimal("300"),
        started_at=datetime.datetime(2026, 12, 3, 9, 0),
        completed_at=datetime.datetime(2026, 12, 3, 12, 30),
    )
    reservation.assignments.append(second)
    reservation.save()
    return reservation


def test_context_of_each_assignment_carries_its_own_car_driver_and_trip_report(
    world, create_car, create_user, assign_user_to_org
):
    from kampan.utils import car_reservation_paper as paper

    reservation = two_car_trip(world, create_car, create_user, assign_user_to_org)
    first, second = reservation.assignments

    first_context = paper.build_context(reservation, first)
    second_context = paper.build_context(reservation, second)

    assert (first_context["car_plate"], first_context["driver_name"]) == ("กก 1234", "สมศักดิ์ ขับดี")
    assert (first_context["km_out"], first_context["km_in"], first_context["km_total"]) == (1000, 1250, 250)
    assert first_context["trip_cost"] == "1,500"
    assert (second_context["car_plate"], second_context["driver_name"]) == ("ขข 9999", "สมหมาย ขับเก่ง")
    assert second_context["car_type"] == "เก๋ง"
    assert (second_context["km_out"], second_context["km_in"], second_context["km_total"]) == (40, 90, 50)
    assert second_context["trip_cost"] == "300"
    assert (second_context["trip_start_time"], second_context["trip_end_time"]) == ("09:00", "12:30")
    assert (second_context["trip_hours"], second_context["trip_minutes"]) == (3, 30)
    # ส่วนที่เหลือมาจากคำขอเหมือนกันทุกใบ
    assert first_context["location"] == second_context["location"]
    assert first_context["requester_name"] == second_context["requester_name"]


def test_context_without_an_assignment_uses_the_first_one(
    world, create_car, create_user, assign_user_to_org
):
    from kampan.utils import car_reservation_paper as paper

    reservation = two_car_trip(world, create_car, create_user, assign_user_to_org)

    assert paper.build_context(reservation)["car_plate"] == "กก 1234"


def test_context_of_a_request_without_assignments_leaves_car_and_driver_blank(world):
    from kampan.utils import car_reservation_paper as paper

    reservation = world.reservation("domestic", approved_steps=1)

    context = paper.build_context(reservation)

    assert context["car_plate"] == "" and context["driver_name"] == ""
    assert "km_total" not in context


def test_each_assignment_prints_its_own_pdf_with_its_own_car(
    world, create_car, create_user, assign_user_to_org
):
    reservation = two_car_trip(world, create_car, create_user, assign_user_to_org)
    first, second = reservation.assignments

    def paper_of(assignment=None):
        suffix = f"/{assignment.assignment_id}" if assignment else ""
        return world.client_for(world.requester).get(
            f"{BASE}/{reservation.id}/paper{suffix}?organization_id={world.org.id}"
        )

    bare, first_pdf, second_pdf = paper_of(), paper_of(first), paper_of(second)

    for response in (bare, first_pdf, second_pdf):
        assert response.status_code == 200 and response.mimetype == "application/pdf"
    assert "กก 1234" in pdf_text(bare) and "กก 1234" in pdf_text(first_pdf)
    second_text = pdf_text(second_pdf)
    assert "ขข 9999" in second_text and "กก 1234" not in second_text
    assert "สมหมาย ขับเก่ง" in second_text
    assert f"car_request_{reservation.id}_2.pdf" in second_pdf.headers["Content-Disposition"]
    assert f"car_request_{reservation.id}_1.pdf" in bare.headers["Content-Disposition"]


def test_a_single_car_request_keeps_the_original_download_name(world):
    reservation = world.reservation("domestic")

    response = world.paper(world.requester, reservation)

    assert f"car_request_{reservation.id}.pdf" in response.headers["Content-Disposition"]
