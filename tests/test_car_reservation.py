"""คำขอใช้รถของระบบจองรถ: ผู้ขอยื่น -> ผู้อนุมัติแต่ละขั้นตามเส้นทางที่ตรึงไว้ตอนยื่น"""

import datetime
import io
import re
from unittest.mock import MagicMock, patch

import pytest
from lxml import html as lxml_html

from kampan import models, utils
from kampan.utils import car_reservation_flow as flow
from kampan.web import redis_rq
from tests.test_car_reservation_tasks import PNG_BYTES

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
    """กันการต่อ Redis จริง และให้ตรวจ job แจ้งเตือนที่ถูกส่งเข้าคิวได้"""
    mock_q = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", mock_q, create=True):
        yield mock_q


def email_jobs(mock_q, event=None):
    """job แจ้งเตือนอีเมลของ car_reservation ที่ถูกส่งเข้าคิว: [(request_id, event, recipients, host_url)]"""
    jobs = [
        call.kwargs["args"]
        for call in mock_q.enqueue.call_args_list
        if call.args[0] is utils.car_reservation_email.send_car_reservation_email
    ]
    return [job for job in jobs if event is None or job[1] == event]


# ข้อมูลเฉพาะประเภทที่ผ่านกฎทุกข้อ (ใช้เป็นฐานของ request_data)
TYPE_SPECIFIC_DATA = {
    "domestic": {
        "vehicle_kind": "ตู้",
        "vehicle_count": "1",
        "district": "หาดใหญ่",
        "province": "สงขลา",
    },
    "airport": {
        "transfer": "pickup",
        "flight_number": "TG 123",
        "flight_date": (datetime.date.today() + datetime.timedelta(days=20)).isoformat(),
        "flight_arrival_time": "09:10",
        "flight_departure_time": "",
        "requester_position": "อาจารย์",
        "passengers-0-name": "สมชาย ใจดี",
        "passengers-0-phone": "089-111-2222",
        "eligibility_confirmed": "y",
    },
    "welfare": {
        "employee_type": "พนักงานมหาวิทยาลัย",
        "affiliation": "กองกายภาพและสิ่งแวดล้อม",
        "vehicle_kind": "ตู้",
        "event_type": "อุปสมบท",
        "host_name": "นายสมศักดิ์ ใจดี",
        "house": "12/3",
        "subdistrict": "คอหงส์",
        "district": "หาดใหญ่",
        "province": "สงขลา",
        "direct_relative_confirmed": "y",
    },
    "abroad": {
        "section": "คณะวิศวกรรมศาสตร์",
        "document_number": "ศธ 0521.1/123",
        "vehicle_kind": "ตู้",
        "vehicle_count": "1",
        "city_state": "กัวลาลัมเปอร์",
        "country": "มาเลเซีย",
        "coordinator_name": "นายประสาน งานดี",
        "coordinator_phone": "081-999-8888",
        "requester_position": "คณบดี",
    },
}


def project_file(content=b"%PDF-1.4 project", filename="project.pdf"):
    return (io.BytesIO(content), filename)


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Reservation Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.division = models.Division(name="ฝ่ายบริการ", organization=org)
    s.division.save()
    s.other_division = models.Division(name="ฝ่ายอื่น", organization=org)
    s.other_division.save()

    def assign_in_division(user, roles, division):
        member = assign_user_to_org(user, org, roles=roles)
        member.division = division
        member.save()
        return member

    s.assign_in_division = assign_in_division

    s.requester = create_user("Requester", "One")
    s.supervisor = create_user("Supervisor", "Two")
    s.other_head = create_user("OtherHead", "Five")
    s.dispatcher = create_user("Dispatcher", "Three")
    s.stranger = create_user("Stranger", "Four")
    assign_in_division(s.requester, ["staff"], s.division)
    assign_in_division(s.supervisor, ["head"], s.division)
    assign_in_division(s.other_head, ["head"], s.other_division)
    assign_user_to_org(s.stranger, org, roles=["staff"])
    assign_user_to_org(s.dispatcher, org, roles=["dispatcher"])

    # ผู้ถือ role อนุมัติที่เหลือ (คนละคน) เพื่อเดินครบทุกเส้นทาง
    s.holders = {"supervisor": s.supervisor, "dispatcher": s.dispatcher}
    for key in APPROVAL_ROLE_KEYS:
        if key == "dispatcher":
            continue
        holder = create_user(f"Holder{key.title().replace('_', '')}", "Position")
        assign_user_to_org(holder, org, roles=[key])
        s.holders[key] = holder

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for

    def request_data(
        request_type="domestic", province_scope="in_province", days_ahead=20
    ):
        departure = datetime.date.today() + datetime.timedelta(days=days_ahead)
        data = {
            "requester_unit": "คณะวิศวกรรมศาสตร์",
            "phone": "081-234-5678",
            "contact_name": s.requester.get_name(),
            "contact_email": s.requester.email,  # เหมือนค่าเริ่มต้นของฟอร์ม
            "location": "กรุงเทพฯ",
            "request_reason": "ประชุมวิชาการ",
            "departure_date": departure.isoformat(),
            "departure_time": "08:00",
            "return_date": (departure + datetime.timedelta(days=1)).isoformat(),
            "return_time": "17:00",
            "passenger_number": "3",
            "pickup_place": "หน้าอาคารสำนักงานอธิการบดี",
            "pickup_time": "07:30",
        }
        data.update(TYPE_SPECIFIC_DATA[request_type])
        if request_type == "abroad":
            data["project_file"] = project_file()
        if request_type == "domestic":
            data["province_scope"] = province_scope
        return data

    s.request_data = request_data

    def submit_request(request_type="domestic", province_scope="in_province"):
        data = request_data(request_type, province_scope)
        response = client_for(s.requester).post(
            f"{BASE}/new?organization_id={org.id}&type={request_type}", data=data
        )
        assert response.status_code == 302, response.get_data(as_text=True)
        return (
            models.CarReservation.objects(creator=s.requester)
            .order_by("-id")
            .first()
        )

    s.submit_request = submit_request
    s.submit_domestic_request = submit_request

    def add_driver(first_name="Driver", last_name="One", roles=("driver",)):
        user = create_user(first_name, last_name)
        assign_user_to_org(user, org, roles=list(roles))
        return user

    s.add_driver = add_driver
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")
    s.driver = add_driver()
    return s


def detail_url(world, car_application):
    return f"{BASE}/{car_application.id}?organization_id={world.org.id}"


def approve_url(world, car_application):
    return f"{BASE}/{car_application.id}/approve?organization_id={world.org.id}"


def step_data(world, key):
    """ฟอร์มอนุมัติของขั้น key (ขั้นผู้จัดรถต้องระบุรถและพนักงานขับรถ)"""
    if key == "dispatcher":
        return {"comment": "", "car": str(world.car.id), "driver": str(world.driver.id)}
    return {"comment": ""}


def test_requester_submits_domestic_request_and_it_waits_for_supervisor(world):
    car_application = world.submit_domestic_request()

    assert car_application.status == "pending"
    assert car_application.route_snapshot == [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ]

    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert page.status_code == 200
    assert "รอผู้บังคับบัญชา" in page.get_data(as_text=True)


def test_domestic_request_is_saved_with_its_form_fields_and_shown_on_detail(world):
    data = world.request_data("domestic")
    data.update(
        vehicle_kind="บัส",
        vehicle_count="2",
        district="บางกล่ำ",
        province="สงขลา",
        pickup_place="หน้าอาคารเรียนรวม",
        pickup_time="06:45",
    )

    response = post_new(world, data)

    assert response.status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.details.vehicle_kind == "บัส"
    assert saved.details.vehicle_count == 2
    assert saved.details.district == "บางกล่ำ"
    assert saved.details.province == "สงขลา"
    assert saved.pickup_place == "หน้าอาคารเรียนรวม"
    assert saved.pickup_time == "06:45"
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    for shown in ("บัส", "บางกล่ำ", "หน้าอาคารเรียนรวม", "06:45"):
        assert shown in html


def test_domestic_office_unit_request_saves_and_shows_the_cost_responsibilities(world):
    data = world.request_data("domestic")
    data["in_office_of_president"] = "y"
    data["cost_responsibilities"] = ["ค่าน้ำมันเชื้อเพลิง", "ค่าที่พักของพนักงานขับรถ"]

    assert post_new(world, data).status_code == 302

    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.details.in_office_of_president is True
    assert saved.details.cost_responsibilities == [
        "ค่าน้ำมันเชื้อเพลิง",
        "ค่าที่พักของพนักงานขับรถ",
    ]
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    assert "หน่วยงานในสำนักงานอธิการบดี" in html
    assert "ค่าที่พักของพนักงานขับรถ" in html
    assert "เบี้ยเลี้ยง" not in html


def test_domestic_cost_responsibilities_are_dropped_unless_the_office_box_is_ticked(
    world,
):
    data = world.request_data("domestic")
    data["cost_responsibilities"] = ["เบี้ยเลี้ยง"]

    assert post_new(world, data).status_code == 302

    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.details.in_office_of_president is False
    assert saved.details.cost_responsibilities == []
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    assert "เบี้ยเลี้ยง" not in html


def test_airport_request_is_saved_with_its_form_fields_and_shown_on_detail(world):
    data = world.request_data("airport")
    data.update(
        {
            "transfer": "dropoff",
            "flight_number": "FD 3201",
            "flight_arrival_time": "",
            "flight_departure_time": "14:35",
            "requester_position": "ผู้ช่วยอธิการบดี",
            "passengers-0-name": "นภา รักดี",
            "passengers-0-phone": "081-000-1111",
            "passengers-1-name": "ปราณี มีสุข",
            "passengers-1-phone": "082-000-2222",
            "in_office_of_president": "y",
            "cost_responsibilities": ["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง"],
        }
    )

    response = post_new(world, data, request_type="airport")

    assert response.status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.details.transfer == "dropoff"
    assert saved.details.flight_number == "FD 3201"
    assert saved.details.departure_time == "14:35"
    assert saved.details.arrival_time == ""
    assert saved.details.requester_position == "ผู้ช่วยอธิการบดี"
    assert [(p.name, p.phone) for p in saved.details.passengers] == [
        ("นภา รักดี", "081-000-1111"),
        ("ปราณี มีสุข", "082-000-2222"),
    ]
    assert saved.passenger_number == 2
    assert saved.details.in_office_of_president is True
    assert saved.details.cost_responsibilities == ["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง"]
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    for shown in ("FD 3201", "14:35", "นภา รักดี", "081-000-1111", "ปราณี มีสุข", "ผู้ช่วยอธิการบดี"):
        assert shown in html


def test_airport_form_shows_its_own_title_and_only_its_own_fields(world):
    page = world.client_for(world.requester).get(
        f"{BASE}/new?organization_id={world.org.id}&type=airport"
    )

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่" in html
    assert 'name="flight_number"' in html
    assert 'name="passengers-4-name"' in html
    assert 'name="vehicle_kind"' not in html
    assert 'name="province_scope"' not in html


def test_airport_request_without_any_passenger_is_refused(world):
    data = world.request_data("airport")
    data["passengers-0-name"] = ""
    data["passengers-0-phone"] = ""

    response = post_new(world, data, request_type="airport")

    assert response.status_code == 200
    assert "ต้องระบุผู้โดยสารอย่างน้อย 1 คน" in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_airport_passenger_row_needs_both_name_and_phone_and_extra_rows_are_ignored(
    world,
):
    data = world.request_data("airport")
    data["passengers-1-name"] = "มีชื่อไม่มีเบอร์"

    response = post_new(world, data, request_type="airport")

    assert response.status_code == 200
    assert "ผู้โดยสารแต่ละคนต้องระบุทั้งชื่อและเบอร์โทร" in response.get_data(as_text=True)

    data["passengers-1-phone"] = "080-000-0000"
    for extra in range(2, 7):
        data[f"passengers-{extra}-name"] = f"คนที่ {extra}"
        data[f"passengers-{extra}-phone"] = "080-111-1111"
    assert post_new(world, data, request_type="airport").status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.passenger_number == 5


def test_airport_request_needs_the_eligibility_confirmation(world):
    data = world.request_data("airport")
    del data["eligibility_confirmed"]

    response = post_new(world, data, request_type="airport")

    assert response.status_code == 200
    assert "ข้าพเจ้าเป็นผู้บริหารหรือบุคลากรในสำนักงานอธิการบดี" in response.get_data(
        as_text=True
    )
    assert "กรุณายืนยันสิทธิ์การขอใช้รถ" in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_welfare_request_is_saved_with_its_form_fields_and_shown_on_detail(world):
    data = world.request_data("welfare")
    data.update(
        employee_type="ลูกจ้างประจำ",
        affiliation="งานยานพาหนะ",
        vehicle_kind="บัส",
        event_type="ฌาปนกิจศพ",
        host_name="นางบุญมี ศรีสุข",
        house="99",
        subdistrict="ทุ่งตำเสา",
        district="หาดใหญ่",
        province="สงขลา",
    )

    response = post_new(world, data, request_type="welfare")

    assert response.status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.requester_unit == "งานยานพาหนะ"
    assert saved.details.employee_type == "ลูกจ้างประจำ"
    assert saved.details.affiliation == "งานยานพาหนะ"
    assert saved.details.vehicle_kind == "บัส"
    assert saved.details.event_type == "ฌาปนกิจศพ"
    assert saved.details.host_name == "นางบุญมี ศรีสุข"
    assert (saved.details.house, saved.details.subdistrict) == ("99", "ทุ่งตำเสา")
    assert (saved.details.district, saved.details.province) == ("หาดใหญ่", "สงขลา")
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    for shown in ("ลูกจ้างประจำ", "ฌาปนกิจศพ", "นางบุญมี ศรีสุข", "ทุ่งตำเสา", "บัส"):
        assert shown in html


@pytest.mark.parametrize("vehicle_kind", ["เก๋ง", "มินิบัส"])
def test_welfare_request_accepts_only_bus_or_van(world, vehicle_kind):
    data = world.request_data("welfare")
    data["vehicle_kind"] = vehicle_kind

    response = post_new(world, data, request_type="welfare")

    assert response.status_code == 200
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_welfare_request_needs_the_self_or_direct_relative_confirmation(world):
    data = world.request_data("welfare")
    del data["direct_relative_confirmed"]

    response = post_new(world, data, request_type="welfare")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ขอใช้สำหรับตนเองหรือญาติสายตรงเท่านั้น" in html
    assert "กรุณายืนยันว่าขอใช้สำหรับตนเองหรือญาติสายตรงเท่านั้น" in html
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_abroad_request_is_saved_with_its_form_fields_and_shown_on_detail(world):
    data = world.request_data("abroad")
    data.update(
        section="สำนักวิชาการ",
        document_number="ที่ อว 0521/777",
        vehicle_kind="บัส",
        vehicle_count="2",
        city_state="รัฐเประ",
        country="มาเลเซีย",
        request_reason="ศึกษาดูงานเครือข่ายมหาวิทยาลัย",
        coordinator_name="นางสาวประสาน ดีมาก",
        coordinator_phone="082-333-4444",
        requester_position="รองคณบดี",
    )

    response = post_new(world, data, request_type="abroad")

    assert response.status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    assert saved.details.section == "สำนักวิชาการ"
    assert saved.details.document_number == "ที่ อว 0521/777"
    assert (saved.details.vehicle_kind, saved.details.vehicle_count) == ("บัส", 2)
    assert (saved.details.city_state, saved.details.country) == ("รัฐเประ", "มาเลเซีย")
    assert saved.request_reason == "ศึกษาดูงานเครือข่ายมหาวิทยาลัย"
    assert saved.details.coordinator_name == "นางสาวประสาน ดีมาก"
    assert saved.details.coordinator_phone == "082-333-4444"
    assert saved.details.requester_position == "รองคณบดี"
    assert saved.project_file.filename == "project.pdf"
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    for shown in ("สำนักวิชาการ", "ที่ อว 0521/777", "รัฐเประ", "นางสาวประสาน ดีมาก", "project.pdf"):
        assert shown in html


def test_abroad_request_without_the_project_file_is_refused(world):
    data = world.request_data("abroad")
    del data["project_file"]

    response = post_new(world, data, request_type="abroad")

    assert response.status_code == 200
    assert "กรุณาแนบเอกสารโครงการ" in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


@pytest.mark.parametrize(
    "upload",
    [
        project_file(b"MZ", "virus.exe"),
        project_file(b"x" * (10 * 1024 * 1024 + 1), "big.pdf"),
    ],
    ids=["extension", "size"],
)
def test_abroad_project_file_must_be_an_allowed_type_within_10mb(world, upload):
    data = world.request_data("abroad")
    data["project_file"] = upload

    response = post_new(world, data, request_type="abroad")

    assert response.status_code == 200
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_project_file_is_downloadable_only_by_members_of_the_requests_org(
    world, create_org, create_user, assign_user_to_org
):
    assert post_new(
        world,
        world.request_data("abroad"),
        request_type="abroad",
    ).status_code == 302
    saved = models.CarReservation.objects(creator=world.requester).first()
    download = f"{BASE}/{saved.id}/project_file?organization_id={world.org.id}"

    for member in (world.requester, world.stranger):
        response = world.client_for(member).get(download)
        assert response.status_code == 200
        assert response.get_data() == b"%PDF-1.4 project"
    page = world.client_for(world.requester).get(detail_url(world, saved))
    assert f"/requests/{saved.id}/project_file" in page.get_data(as_text=True)

    other_org = create_org("Other Reservation Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    outsider = create_user("Outsider", "Nine")
    assign_user_to_org(outsider, other_org, roles=["staff"])
    refused = world.client_for(outsider).get(
        f"{BASE}/{saved.id}/project_file?organization_id={other_org.id}"
    )
    assert refused.status_code == 404


@pytest.mark.parametrize(
    "request_type, province_scope",
    [("domestic", "out_of_province"), ("abroad", "in_province")],
)
def test_dispatcher_records_extra_travelers_for_out_of_province_domestic_and_abroad(
    world, request_type, province_scope
):
    car_application = world.submit_request(request_type, province_scope)
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )

    form_page = world.client_for(world.dispatcher).get(detail_url(world, car_application))
    assert 'name="extra_travelers"' in form_page.get_data(as_text=True)
    data = step_data(world, "dispatcher")
    data["extra_travelers"] = "นายสมหวัง ขับดี และนางสาวใจเย็น"
    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=data
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.extra_travelers == "นายสมหวัง ขับดี และนางสาวใจเย็น"
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "นายสมหวัง ขับดี และนางสาวใจเย็น" in page.get_data(as_text=True)


def test_dispatcher_has_no_extra_travelers_field_for_an_in_province_domestic_and_ignores_it(
    world,
):
    car_application = world.submit_request("domestic", "in_province")
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )

    form_page = world.client_for(world.dispatcher).get(detail_url(world, car_application))
    assert 'name="extra_travelers"' not in form_page.get_data(as_text=True)
    data = step_data(world, "dispatcher")
    data["extra_travelers"] = "นายสมหวัง ขับดี"
    world.client_for(world.dispatcher).post(approve_url(world, car_application), data=data)

    car_application.reload()
    assert car_application.current_step == 2
    assert car_application.extra_travelers == ""


def test_dispatcher_extra_travelers_field_is_labelled_with_the_form_item_3_wording(world):
    car_application = world.submit_request("domestic", "out_of_province")
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    assert "ขออนุมัติให้ผู้ร่วมเดินทางไปปฏิบัติงานต่างจังหวัด" in html
    assert "ตามช่อง (3) ของใบขอใช้รถ เช่น ชื่อพนักงานขับรถ หรือผู้ช่วย คั่นด้วยจุลภาค" in html


def test_dispatcher_form_has_an_overtime_checkbox_and_a_car_dropdown(world):
    car_application = request_at_dispatcher(world)

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    doc = lxml_html.fromstring(html)
    (form,) = doc.xpath("//form[.//*[@name='car']]")
    (overtime,) = form.xpath(".//input[@type='checkbox'][@name='is_overtime']")
    assert "checkbox" in overtime.get("class").split()
    (car,) = form.xpath(".//select[@name='car']")
    assert "กก 1234" in car.text_content()


def test_dispatcher_form_orders_driver_table_then_car_then_overtime_then_extra_travelers_then_comment(
    world,
):
    car_application = request_at_dispatcher(world, province_scope="out_of_province")

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    positions = [
        html.index('data-role="driver-workload"'),
        html.index('name="car"'),
        html.index('id="is_overtime"'),
        html.index('name="extra_travelers"'),
        html.index('name="comment"'),
    ]
    assert positions == sorted(positions)


@pytest.mark.parametrize("request_type", ["airport", "welfare"])
def test_dispatcher_has_no_extra_travelers_field_for_airport_and_welfare(
    world, request_type
):
    car_application = world.submit_request(request_type)
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )

    form_page = world.client_for(world.dispatcher).get(detail_url(world, car_application))

    assert 'name="comment"' in form_page.get_data(as_text=True)
    assert 'name="extra_travelers"' not in form_page.get_data(as_text=True)


def upcoming(weekday, at_least_days=10):
    """วันถัดไปที่เป็น weekday (จันทร์=0 ... อาทิตย์=6) และห่างจากวันนี้อย่างน้อย at_least_days"""
    day = datetime.date.today() + datetime.timedelta(days=at_least_days)
    while day.weekday() != weekday:
        day += datetime.timedelta(days=1)
    return day


def trip_on(data, first_day, last_day):
    data["departure_date"] = first_day.isoformat()
    data["return_date"] = last_day.isoformat()
    return data


SEDAN_WEEKDAY_ERROR = "รถเก๋ง/มินิบัสให้บริการเฉพาะวันเสาร์-อาทิตย์และวันหยุดนักขัตฤกษ์"


@pytest.mark.parametrize("vehicle_kind", ["เก๋ง", "มินิบัส"])
def test_sedan_or_minibus_is_refused_when_the_trip_includes_a_weekday(
    world, vehicle_kind
):
    saturday = upcoming(5)
    data = trip_on(
        world.request_data("domestic"), saturday, saturday + datetime.timedelta(days=2)
    )
    data["vehicle_kind"] = vehicle_kind

    response = post_new(world, data)

    assert response.status_code == 200
    assert SEDAN_WEEKDAY_ERROR in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_sedan_is_accepted_on_a_weekend_trip(world):
    saturday = upcoming(5)
    data = trip_on(
        world.request_data("domestic"), saturday, saturday + datetime.timedelta(days=1)
    )
    data["vehicle_kind"] = "เก๋ง"

    assert post_new(world, data).status_code == 302


def test_sedan_is_accepted_when_the_weekday_of_the_trip_is_an_org_holiday(world):
    monday = upcoming(0)
    models.CarHoliday(organization=world.org, date=monday, name="วันหยุดพิเศษ").save()
    data = trip_on(world.request_data("domestic"), monday, monday)
    data["vehicle_kind"] = "มินิบัส"

    assert post_new(world, data).status_code == 302


def test_submitting_stores_the_requesters_division_on_the_request(world):
    car_application = world.submit_domestic_request()

    assert car_application.division == world.division


def test_supervisor_approval_moves_request_to_dispatcher(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": "เห็นชอบ"}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "pending"
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "รอผู้จัดรถ" in page.get_data(as_text=True)


def test_only_a_head_of_the_requesters_division_approves_the_supervisor_step(
    world, create_user
):
    colleague_head = create_user("ColleagueHead", "Six")
    world.assign_in_division(colleague_head, ["head"], world.division)
    colleague_staff = create_user("ColleagueStaff", "Seven")
    world.assign_in_division(colleague_staff, ["staff"], world.division)
    car_application = world.submit_domestic_request()

    for outsider in (world.other_head, colleague_staff):
        world.client_for(outsider).post(
            approve_url(world, car_application), data={"comment": ""}
        )
        car_application.reload()
        assert car_application.current_step == 0

    response = world.client_for(colleague_head).post(
        approve_url(world, car_application), data={"comment": "เห็นชอบ"}
    )
    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1


def test_a_head_who_is_the_only_head_submits_and_approves_their_own_request(world):
    # ชั่วคราว (ยังเป็นคำถามเปิด): หัวหน้าฝ่ายอนุมัติขั้นผู้บังคับบัญชาของคำขอตัวเองได้
    response = world.client_for(world.supervisor).post(
        f"{BASE}/new?organization_id={world.org.id}&type=domestic",
        data=world.request_data(),
    )
    assert response.status_code == 302
    car_application = models.CarReservation.objects(
        creator=world.supervisor
    ).first()

    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.current_step == 1
    assert car_application.step_approvals[0].decided_by == world.supervisor


def test_submission_is_refused_when_the_division_has_no_head(world, create_user):
    headless = models.Division(name="ฝ่ายไม่มีหัวหน้า", organization=world.org)
    headless.save()
    lonely = create_user("Lonely", "Eight")
    world.assign_in_division(lonely, ["staff"], headless)

    response = world.client_for(lonely).post(
        f"{BASE}/new?organization_id={world.org.id}&type=domestic",
        data=world.request_data(),
    )

    assert response.status_code == 200
    assert "ฝ่ายของคุณยังไม่มีหัวหน้าฝ่าย กรุณาติดต่อผู้ดูแลระบบ" in response.get_data(
        as_text=True
    )
    assert (
        models.CarReservation.objects(creator=lonely).count() == 0
    )


def test_member_who_is_not_the_current_approver_cannot_approve(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.stranger).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    assert response.status_code in (302, 403)

    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "รอผู้บังคับบัญชา" in page.get_data(as_text=True)


# เส้นทางตามตารางในสเปก §3 (ชื่อขั้นที่หน้าคำขอแสดงเป็น "รอ<ชื่อขั้น>")
SUPERVISOR = ("supervisor", "ผู้บังคับบัญชา")
DISPATCHER = ("dispatcher", "ผู้จัดรถ")
VEHICLE_UNIT_HEAD = ("vehicle_unit_head", "หัวหน้าหน่วยยานพาหนะ")
STRATEGY_HEAD = ("strategy_head", "หัวหน้างานยุทธศาสตร์และบริการกลาง")
PHYSICAL_DIRECTOR = ("physical_director", "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม")
VICE_PRESIDENT = ("vice_president_hatyai", "รองอธิการบดีวิทยาเขตหาดใหญ่")
PRESIDENT = ("president", "อธิการบดี")

ROUTE_CASES = [
    pytest.param(
        "domestic",
        "in_province",
        [SUPERVISOR, DISPATCHER, VEHICLE_UNIT_HEAD, STRATEGY_HEAD],
        id="domestic-in-province",
    ),
    pytest.param(
        "domestic",
        "out_of_province",
        [SUPERVISOR, DISPATCHER, VEHICLE_UNIT_HEAD, STRATEGY_HEAD, PHYSICAL_DIRECTOR],
        id="domestic-out-of-province",
    ),
    pytest.param(
        "airport",
        None,
        [SUPERVISOR, DISPATCHER, VEHICLE_UNIT_HEAD, STRATEGY_HEAD],
        id="airport",
    ),
    pytest.param(
        "welfare",
        None,
        [SUPERVISOR, DISPATCHER, VEHICLE_UNIT_HEAD, STRATEGY_HEAD, PHYSICAL_DIRECTOR],
        id="welfare",
    ),
    pytest.param(
        "abroad",
        None,
        [
            SUPERVISOR,
            DISPATCHER,
            VEHICLE_UNIT_HEAD,
            STRATEGY_HEAD,
            PHYSICAL_DIRECTOR,
            VICE_PRESIDENT,
            PRESIDENT,
        ],
        id="abroad",
    ),
]


@pytest.mark.parametrize("request_type, province_scope, expected_route", ROUTE_CASES)
def test_each_request_type_walks_its_own_route_to_active(
    world, request_type, province_scope, expected_route
):
    car_application = world.submit_request(request_type, province_scope)

    for index, (key, label) in enumerate(expected_route):
        page = world.client_for(world.requester).get(detail_url(world, car_application))
        assert f"รอ{label}" in page.get_data(as_text=True)

        # มีแต่เจ้าของขั้นปัจจุบันที่อนุมัติได้ ขั้นถัดไปมาอนุมัติก่อนไม่ได้
        if index + 1 < len(expected_route):
            next_key, _ = expected_route[index + 1]
            early = world.client_for(world.holders[next_key]).post(
                approve_url(world, car_application), data={"comment": ""}
            )
            # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือขั้นไม่ขยับ
            assert early.status_code in (302, 403)
            car_application.reload()
            assert car_application.current_step == index

        response = world.client_for(world.holders[key]).post(
            approve_url(world, car_application), data=step_data(world, key)
        )
        assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "active"
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert 'data-status="active"' in page.get_data(as_text=True)


def test_second_member_with_the_same_role_can_approve_and_audit_log_names_them(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["president"])

    car_application = world.submit_request("abroad")
    for key in [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
        "vice_president_hatyai",
    ]:
        world.client_for(world.holders[key]).post(
            approve_url(world, car_application), data=step_data(world, key)
        )

    response = world.client_for(secretary).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "active"
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "Secretary Assistant" in page.get_data(as_text=True)


def test_global_admin_cannot_approve_a_step_they_do_not_hold(
    world, create_user, assign_user_to_org
):
    admin = create_user("Admin", "Global", roles=["admin"])
    assign_user_to_org(admin, world.org, roles=["admin"])
    car_application = world.submit_request("domestic")

    world.client_for(admin).post(
        approve_url(world, car_application), data={"comment": ""}
    )

    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0
    assert len(car_application.step_approvals) == 0


def test_removed_member_and_global_admin_without_the_role_cannot_approve_a_role_step(
    world, create_user, assign_user_to_org
):
    admin = create_user("Admin", "Global", roles=["admin"])
    assign_user_to_org(admin, world.org, roles=["admin"])
    removed = create_user("Removed", "Dispatcher")
    assign_user_to_org(removed, world.org, roles=["dispatcher"], status="disactive")
    car_application = world.submit_request("domestic")
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )

    for outsider in (admin, removed):
        world.client_for(outsider).post(
            approve_url(world, car_application), data={"comment": ""}
        )

    car_application.reload()
    assert car_application.current_step == 1
    assert len(car_application.step_approvals) == 1


def deny_url(world, car_application):
    return f"{BASE}/{car_application.id}/deny?organization_id={world.org.id}"


def test_current_approver_can_deny_with_a_reason_and_the_request_stops(world):
    car_application = world.submit_request("domestic")
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )

    response = world.client_for(world.dispatcher).post(
        deny_url(world, car_application), data={"comment": "ไม่มีรถว่างในช่วงเวลานี้"}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "denied"
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    html = page.get_data(as_text=True)
    assert 'data-status="denied"' in html
    assert "ไม่อนุมัติ" in html
    assert "ไม่มีรถว่างในช่วงเวลานี้" in html
    assert 'data-state="denied"' in html

    # ปฏิเสธแล้ว ไม่มีใครอนุมัติต่อได้
    world.client_for(world.holders["vehicle_unit_head"]).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.status == "denied"
    assert len(car_application.step_approvals) == 2


def test_member_who_is_not_the_current_approver_cannot_deny(world):
    car_application = world.submit_request("domestic")

    world.client_for(world.stranger).post(
        deny_url(world, car_application), data={"comment": "ขอปฏิเสธ"}
    )
    world.client_for(world.dispatcher).post(
        deny_url(world, car_application), data={"comment": "ยังไม่ถึงคิว"}
    )

    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0


def test_denying_without_a_reason_is_refused(world):
    car_application = world.submit_request("domestic")

    response = world.client_for(world.supervisor).post(
        deny_url(world, car_application),
        data={"comment": ""},
        follow_redirects=True,
    )

    assert "กรุณาระบุเหตุผลที่ไม่อนุมัติ" in response.get_data(as_text=True)
    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0


def test_organization_without_the_car_reservation_module_gets_404(
    app, create_org, create_user, assign_user_to_org, login_as
):
    org = create_org("Car Only Org")
    org.enabled_modules = ["car"]
    org.save()
    user = create_user("Car", "Member")
    assign_user_to_org(user, org, roles=["staff"])
    client = login_as(app.test_client(), user)

    for path in (f"{BASE}/new?type=domestic", f"{BASE}/"):
        response = client.get(f"{path}&organization_id={org.id}" if "?" in path else f"{path}?organization_id={org.id}")
        assert response.status_code == 404


def test_requests_home_lists_only_the_requesters_own_requests(world):
    other = world.stranger
    world.assign_in_division(other, ["staff"], world.division)
    other_data = world.request_data()
    other_data["request_reason"] = "งานของคนอื่น"
    world.client_for(other).post(
        f"{BASE}/new?organization_id={world.org.id}&type=domestic", data=other_data
    )
    world.submit_domestic_request()

    page = world.client_for(world.requester).get(f"{BASE}/?organization_id={world.org.id}")

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "ประชุมวิชาการ" in html
    assert "รออนุมัติ" in html
    assert "งานของคนอื่น" not in html



def post_new(world, data, request_type="domestic", user=None):
    return world.client_for(user or world.requester).post(
        f"{BASE}/new?organization_id={world.org.id}&type={request_type}", data=data
    )


def test_request_departing_more_than_30_days_ahead_is_refused(world):
    response = post_new(world, world.request_data(days_ahead=40))

    assert response.status_code == 200
    assert "ขอใช้รถล่วงหน้าได้ไม่เกิน 30 วัน" in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_request_departing_in_under_3_business_days_asks_for_urgent_confirmation(
    world,
):
    response = post_new(world, world.request_data(days_ahead=1))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ขอรถล่วงหน้าน้อยกว่า 3 วันทำการ" in html
    assert models.CarReservation.objects(creator=world.requester).count() == 0
    # popup แจ้งเตือนเปิดเองทันที กด "รับทราบ" = ยืนยันแบบเร่งด่วนและยื่นฟอร์มเดิม
    doc = lxml_html.fromstring(html)
    (dialog,) = doc.xpath('//dialog[@data-role="short-notice"]')
    assert dialog.get("open") is not None
    (ack,) = dialog.xpath('.//button[@name="confirm_urgent"]')
    assert ack.get("type") == "submit" and ack.get("value") == "y"
    assert "รับทราบ" in ack.text_content()
    form_id = ack.get("form") or dialog.xpath("ancestor::form/@id")[0]
    assert doc.xpath(f'//form[@id="{form_id}"]')


def test_confirmed_short_notice_request_is_saved_as_urgent_and_shows_badge(world):
    data = world.request_data(days_ahead=1)
    data["confirm_urgent"] = "y"

    response = post_new(world, data)

    assert response.status_code == 302
    car_application = models.CarReservation.objects(creator=world.requester).first()
    assert car_application.is_urgent is True
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "เร่งด่วน" in page.get_data(as_text=True)


def test_request_with_enough_lead_time_is_saved_without_urgent_flag_or_warning(world):
    response = post_new(world, world.request_data(days_ahead=20))

    assert response.status_code == 302
    car_application = models.CarReservation.objects(creator=world.requester).first()
    assert car_application.is_urgent is False
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "เร่งด่วน" not in page.get_data(as_text=True)


def test_abroad_request_needs_10_business_days_while_domestic_needs_3(world):
    data = world.request_data("abroad", days_ahead=5)

    response = post_new(world, data, request_type="abroad")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ขอรถล่วงหน้าน้อยกว่า 10 วันทำการ" in html
    assert models.CarReservation.objects(creator=world.requester).count() == 0

    enough = world.request_data("abroad", days_ahead=20)
    assert post_new(world, enough, request_type="abroad").status_code == 302


def test_request_returning_before_departure_is_refused(world):
    data = world.request_data()
    data["return_date"] = (
        datetime.date.today() + datetime.timedelta(days=19)
    ).isoformat()

    response = post_new(world, data)

    assert response.status_code == 200
    assert "วันกลับต้องไม่ก่อนวันออกเดินทาง" in response.get_data(as_text=True)
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def inbox_url(world):
    return f"{BASE}/inbox?organization_id={world.org.id}"


def inbox_shows(world, user, car_application):
    page = world.client_for(user).get(inbox_url(world))
    assert page.status_code == 200
    return f"{BASE}/{car_application.id}?" in page.get_data(as_text=True)


def test_inbox_shows_request_at_supervisor_step_only_to_the_requesters_division_head(
    world,
):
    car_application = world.submit_domestic_request()

    assert inbox_shows(world, world.supervisor, car_application)
    assert not inbox_shows(world, world.other_head, car_application)
    assert not inbox_shows(world, world.dispatcher, car_application)


def test_after_supervisor_approves_inbox_moves_to_every_member_with_the_dispatcher_role(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["dispatcher"])
    car_application = world.submit_domestic_request()
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )

    assert inbox_shows(world, world.dispatcher, car_application)
    assert inbox_shows(world, secretary, car_application)
    assert not inbox_shows(world, world.supervisor, car_application)


def test_denied_and_active_requests_appear_in_nobodys_inbox(world):
    denied = world.submit_domestic_request()
    world.client_for(world.supervisor).post(
        f"{BASE}/{denied.id}/deny?organization_id={world.org.id}",
        data={"comment": "ไม่เหมาะสม"},
    )
    active = world.submit_domestic_request()
    for key in ["supervisor", "dispatcher", "vehicle_unit_head", "strategy_head"]:
        world.client_for(world.holders[key]).post(
            approve_url(world, active), data=step_data(world, key)
        )
    active.reload()
    assert active.status == "active"

    everyone = [world.requester, world.stranger, *world.holders.values()]
    for user in everyone:
        assert not inbox_shows(world, user, denied)
        assert not inbox_shows(world, user, active)


def test_sidebar_shows_inbox_link_to_approvers_with_count_badge_only_when_waiting(world):
    index_url = f"{BASE}/?organization_id={world.org.id}"

    quiet = world.client_for(world.supervisor).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" in quiet
    assert 'data-testid="inbox-count"' not in quiet

    world.submit_domestic_request()
    world.submit_domestic_request()

    busy = world.client_for(world.supervisor).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" in busy
    assert 'data-testid="inbox-count">2<' in busy
    assert f"{BASE}/inbox?organization_id={world.org.id}" in busy
    stranger = world.client_for(world.stranger).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" not in stranger


def test_sidebar_inbox_link_is_visible_to_every_approval_role_member_even_when_empty(
    world, create_user, assign_user_to_org
):
    index_url = f"{BASE}/?organization_id={world.org.id}"
    delegate = create_user("Delegate", "Ten")
    assign_user_to_org(delegate, world.org, roles=["president"])

    approvers = [delegate, *world.holders.values()]
    for approver in approvers:
        html = world.client_for(approver).get(index_url).get_data(as_text=True)
        assert "รายการรออนุมัติ" in html
        assert 'data-testid="inbox-count"' not in html
    for outsider in (world.requester, world.stranger):
        html = world.client_for(outsider).get(index_url).get_data(as_text=True)
        assert "รายการรออนุมัติ" not in html


def test_inbox_never_lists_requests_of_another_organization(
    world, create_org, assign_user_to_org
):
    other_org = create_org("Other Reservation Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    other_org.enabled_roles = ["dispatcher"]
    other_org.save()
    assign_user_to_org(world.dispatcher, other_org, roles=["dispatcher"])
    foreign = models.CarReservation(
        organization=other_org,
        creator=world.requester,
        request_type="domestic",
        province_scope="in_province",
        location="เชียงใหม่",
        request_reason="งานองค์กรอื่น",
        status="pending",
        route_snapshot=["supervisor", "dispatcher"],
        current_step=1,
    )
    foreign.save()
    own = world.submit_domestic_request()
    world.client_for(world.supervisor).post(
        approve_url(world, own), data={"comment": ""}
    )

    page = world.client_for(world.dispatcher).get(inbox_url(world))
    html = page.get_data(as_text=True)

    assert f"{BASE}/{own.id}?" in html
    assert str(foreign.id) not in html


def dispatch_data(car, driver, comment=""):
    return {"comment": comment, "car": str(car.id), "driver": str(driver.id)}


def request_at_dispatcher(world, **submit_args):
    car_application = world.submit_request(**submit_args)
    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    assert response.status_code == 302
    return car_application


def test_dispatcher_step_logs_the_assignment_as_changes_and_skips_what_stayed_the_same(
    world,
):
    car_application = request_at_dispatcher(world)

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application),
        data=dispatch_data(world.car, world.driver),
    )

    car_application.reload()
    assert changes_of(car_application.audit_logs[-1]) == {
        "รถ": ("-", "กก 1234"),
        "พนักงานขับรถ": ("-", "Driver One"),
    }


def test_dispatcher_step_logs_overtime_and_extra_travelers_when_set(world):
    car_application = request_at_dispatcher(world, province_scope="out_of_province")

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application),
        data={
            **dispatch_data(world.car, world.driver),
            "is_overtime": "y",
            "extra_travelers": "นายสมชาย",
        },
    )

    car_application.reload()
    changes = changes_of(car_application.audit_logs[-1])
    assert changes["งานนอกเวลา (OT)"] == ("ไม่ใช่", "ใช่")
    assert changes["ขออนุมัติให้ผู้ร่วมเดินทางไปปฏิบัติงานต่างจังหวัด"] == ("-", "นายสมชาย")


def test_dispatcher_assigns_car_and_driver_then_everyone_sees_them_on_the_detail(world):
    car_application = request_at_dispatcher(world)

    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.car == world.car
    assert car_application.driver == world.driver
    assert car_application.current_step == 2
    page = world.client_for(world.requester).get(detail_url(world, car_application))
    html = page.get_data(as_text=True)
    assert "กก 1234" in html
    assert "Driver One" in html


def test_dispatcher_ticks_overtime_at_the_dispatcher_step_and_the_detail_shows_it(
    world,
):
    car_application = request_at_dispatcher(world)

    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application),
        data={**dispatch_data(world.car, world.driver), "is_overtime": "y"},
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.is_overtime is True
    html = (
        world.client_for(world.requester)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )
    assert 'data-role="overtime-badge"' in html


def test_dispatch_without_ticking_overtime_is_an_in_hours_job(world):
    car_application = request_at_dispatcher(world)

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )

    car_application.reload()
    assert car_application.is_overtime is False
    html = (
        world.client_for(world.requester)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )
    assert 'data-role="overtime-badge"' not in html


@pytest.mark.parametrize("missing", ["car", "driver", "both"])
def test_dispatcher_cannot_approve_without_choosing_car_and_driver(world, missing):
    car_application = request_at_dispatcher(world)
    data = dispatch_data(world.car, world.driver)
    if missing in ("car", "both"):
        data["car"] = ""
    if missing in ("driver", "both"):
        data["driver"] = ""

    client = world.client_for(world.dispatcher)
    response = client.post(approve_url(world, car_application), data=data)

    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1
    assert car_application.car is None
    assert car_application.driver is None
    assert len(car_application.step_approvals) == 1
    page = client.get(detail_url(world, car_application))
    assert "กรุณาเลือกรถและพนักงานขับรถ" in page.get_data(as_text=True)


def test_dispatcher_can_only_assign_active_cars_and_drivers_of_the_same_org(
    world, create_org, create_car, create_user, assign_user_to_org
):
    other_org = create_org("Other Fleet Org")
    foreign_car = create_car(other_org, "ขข 9999")
    inactive_car = create_car(world.org, "คค 1111", status="disactive")
    staff_member = world.add_driver("Staffer", "Only", roles=("staff",))
    left_driver = world.add_driver("Former", "Driver")
    member = models.OrganizationUserRole.objects(
        organization=world.org, user=left_driver
    ).first()
    member.status = "disactive"
    member.save()
    foreign_driver = create_user("Foreign", "Driver")
    assign_user_to_org(foreign_driver, other_org, roles=["driver"])
    car_application = request_at_dispatcher(world)

    refused = [
        (foreign_car, world.driver),
        (inactive_car, world.driver),
        (world.car, staff_member),
        (world.car, left_driver),
        (world.car, foreign_driver),
    ]
    for car, driver in refused:
        response = world.client_for(world.dispatcher).post(
            approve_url(world, car_application), data=dispatch_data(car, driver)
        )
        assert response.status_code == 302
        car_application.reload()
        assert car_application.current_step == 1, (car.license_plate, driver.first_name)
        assert car_application.car is None
        assert car_application.driver is None

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )
    car_application.reload()
    assert car_application.current_step == 2


def at_dispatcher_with_times(world, departure, return_):
    car_application = request_at_dispatcher(world)
    car_application.departure_datetime = departure
    car_application.return_datetime = return_
    car_application.save()
    return car_application


def assigned_request(world, departure, return_, status="active", car=None, driver=None):
    return models.CarReservation(
        organization=world.org,
        creator=world.requester,
        request_type="domestic",
        province_scope="in_province",
        location="ที่อื่น",
        request_reason="งานเดิม",
        departure_datetime=departure,
        return_datetime=return_,
        status=status,
        route_snapshot=["supervisor", "dispatcher", "vehicle_unit_head"],
        current_step=2,
        car=car,
        driver=driver,
    ).save()


DAY = datetime.datetime.combine(
    datetime.date.today() + datetime.timedelta(days=20), datetime.time(8, 0)
)


@pytest.mark.parametrize("blocking_status", ["pending", "active", "cancel_requested"])
def test_a_car_already_booked_in_an_overlapping_time_is_refused(world, blocking_status):
    other_driver = world.add_driver("Other", "Driver")
    assigned_request(
        world,
        DAY + datetime.timedelta(hours=2),
        DAY + datetime.timedelta(hours=6),
        status=blocking_status,
        car=world.car,
        driver=other_driver,
    )
    car_application = at_dispatcher_with_times(
        world, DAY, DAY + datetime.timedelta(hours=9)
    )

    client = world.client_for(world.dispatcher)
    response = client.post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1
    assert car_application.car is None
    html = client.get(detail_url(world, car_application)).get_data(as_text=True)
    assert "รถ กก 1234 มีงานช่วงเวลานี้แล้ว" in html


def test_a_driver_with_an_overlapping_job_can_still_be_assigned_another_car(world):
    other_car = models.vehicles.Car(
        organization=world.org, license_plate="งง 2222", status="active"
    ).save()
    assigned_request(
        world,
        DAY + datetime.timedelta(hours=2),
        DAY + datetime.timedelta(hours=6),
        status="active",
        car=other_car,
        driver=world.driver,
    )
    car_application = at_dispatcher_with_times(
        world, DAY, DAY + datetime.timedelta(hours=9)
    )

    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 2
    assert car_application.driver == world.driver


@pytest.mark.parametrize(
    "start_hours, end_hours, status",
    [
        pytest.param(10, 14, "active", id="later-same-day"),
        pytest.param(-5, 0, "active", id="ends-exactly-at-departure"),
        pytest.param(2, 6, "cancelled", id="cancelled"),
        pytest.param(2, 6, "denied", id="denied"),
        pytest.param(2, 6, "completed", id="completed"),
    ],
)
def test_bookings_that_do_not_overlap_or_are_not_live_do_not_block_assignment(
    world, start_hours, end_hours, status
):
    assigned_request(
        world,
        DAY + datetime.timedelta(hours=start_hours),
        DAY + datetime.timedelta(hours=end_hours),
        status=status,
        car=world.car,
        driver=world.driver,
    )
    car_application = at_dispatcher_with_times(
        world, DAY, DAY + datetime.timedelta(hours=9)
    )

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )

    car_application.reload()
    assert car_application.current_step == 2
    assert car_application.car == world.car


def test_assignment_is_recorded_in_the_audit_log_with_plate_and_driver(world):
    car_application = request_at_dispatcher(world)

    world.client_for(world.dispatcher).post(
        approve_url(world, car_application),
        data=dispatch_data(world.car, world.driver, comment="เรียบร้อย"),
    )

    page = world.client_for(world.requester).get(detail_url(world, car_application))
    assert "จัดรถ กก 1234 พนักงานขับรถ Driver One" in page.get_data(as_text=True)


def test_car_and_driver_are_ignored_outside_the_dispatcher_step(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application),
        data=dispatch_data(world.car, world.driver, comment="เห็นชอบ"),
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1
    assert car_application.car is None
    assert car_application.driver is None
    page = world.client_for(world.supervisor).get(detail_url(world, car_application))
    # ฟอร์มของผู้อนุมัติขั้นนี้ไม่มีช่องเลือกรถ/พนักงานขับรถ
    assert 'name="car"' not in page.get_data(as_text=True)


def test_dispatcher_detail_offers_only_assignable_cars_and_drivers_in_the_approve_form(
    world, create_org, create_car
):
    create_car(world.org, "คค 1111", status="disactive")
    create_car(create_org("Other Fleet Org"), "ขข 9999")
    world.add_driver("Staffer", "Only", roles=("staff",))
    car_application = request_at_dispatcher(world)

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    assert 'name="car"' in html and 'name="driver"' in html
    assert "กก 1234 (เก๋ง)" in html
    assert "Driver One" in html
    assert "คค 1111" not in html
    assert "ขข 9999" not in html
    assert "Staffer Only" not in html


def test_dispatcher_car_choice_label_includes_the_seat_count_when_the_car_has_one(
    world,
):
    world.car.seat_count = 4
    world.car.save()
    car_application = request_at_dispatcher(world)

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    assert "กก 1234 (เก๋ง, 4 ที่นั่ง)" in html


def cancel_url(world, car_application):
    return f"{BASE}/{car_application.id}/cancel?organization_id={world.org.id}"


def test_requester_cancels_before_a_car_is_assigned_and_the_request_leaves_inboxes(
    world,
):
    car_application = world.submit_domestic_request()
    assert inbox_shows(world, world.supervisor, car_application)

    response = world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": "เปลี่ยนแผน"}
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.status == "cancelled"
    assert car_application.audit_logs[-1].action == "cancelled"
    assert car_application.audit_logs[-1].actor == world.requester
    assert car_application.audit_logs[-1].comment == "เปลี่ยนแผน"
    assert not inbox_shows(world, world.supervisor, car_application)


def request_with_car_assigned(world):
    car_application = request_at_dispatcher(world)
    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application), data=dispatch_data(world.car, world.driver)
    )
    assert response.status_code == 302
    car_application.reload()
    assert car_application.car == world.car
    return car_application


def overtime_url(world, car_application):
    return f"{BASE}/{car_application.id}/overtime?organization_id={world.org.id}"


def test_dispatcher_toggles_overtime_on_an_active_reservation_and_it_is_audit_logged(
    world,
):
    car_application = assigned_request(
        world, DAY, DAY + datetime.timedelta(hours=4), car=world.car, driver=world.driver
    )
    assert car_application.is_overtime is False
    client = world.client_for(world.dispatcher)

    response = client.post(overtime_url(world, car_application), data={"is_overtime": "y"})

    assert response.status_code == 302
    car_application.reload()
    assert car_application.is_overtime is True
    assert car_application.audit_logs[-1].action == "overtime_changed"
    assert car_application.audit_logs[-1].actor == world.dispatcher
    assert car_application.audit_logs[-1].comment == "ตั้งเป็นงานนอกเวลา (OT)"

    client.post(overtime_url(world, car_application), data={})

    car_application.reload()
    assert car_application.is_overtime is False
    assert car_application.audit_logs[-1].comment == "ตั้งเป็นงานในเวลา"


def test_overtime_toggle_is_the_wtforms_checkbox_and_reflects_the_saved_state(world):
    car_application = assigned_request(
        world, DAY, DAY + datetime.timedelta(hours=4), car=world.car, driver=world.driver
    )
    client = world.client_for(world.dispatcher)

    def checkbox():
        html = client.get(detail_url(world, car_application)).get_data(as_text=True)
        doc = lxml_html.fromstring(html)
        (box,) = doc.xpath("//form[@data-role='overtime-form']//input[@type='checkbox']")
        return doc, box

    doc, box = checkbox()
    assert (box.get("id"), box.get("name"), box.get("checked")) == ("is_overtime", "is_overtime", None)
    assert doc.xpath("//form[@data-role='overtime-form']//label[@for='is_overtime']")

    client.post(overtime_url(world, car_application), data={"is_overtime": "y"})

    assert checkbox()[1].get("checked") is not None


def test_toggling_overtime_logs_the_old_and_new_value(world):
    car_application = assigned_request(
        world, DAY, DAY + datetime.timedelta(hours=4), car=world.car, driver=world.driver
    )
    client = world.client_for(world.dispatcher)

    client.post(overtime_url(world, car_application), data={"is_overtime": "y"})
    client.post(overtime_url(world, car_application), data={})

    car_application.reload()
    on, off = car_application.audit_logs[-2:]
    assert changes_of(on) == {"งานนอกเวลา (OT)": ("ไม่ใช่", "ใช่")}
    assert changes_of(off) == {"งานนอกเวลา (OT)": ("ใช่", "ไม่ใช่")}


def test_only_a_dispatcher_can_toggle_overtime(world):
    car_application = assigned_request(
        world, DAY, DAY + datetime.timedelta(hours=4), car=world.car, driver=world.driver
    )

    for user in (world.requester, world.supervisor, world.driver):
        response = world.client_for(user).post(
            overtime_url(world, car_application), data={"is_overtime": "y"}
        )
        # 403 บางกรณีถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือค่าไม่เปลี่ยน
        assert response.status_code in (302, 403)

    car_application.reload()
    assert car_application.is_overtime is False


def test_cancelling_after_a_car_is_assigned_asks_the_dispatcher_to_acknowledge(world):
    car_application = request_with_car_assigned(world)

    response = world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": "งานเลื่อน"}
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.status == "cancel_requested"
    html = (
        world.client_for(world.requester)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )
    assert "ขอยกเลิก — รอผู้จัดรถรับทราบ" in html


def test_cancel_request_appears_in_the_inbox_of_dispatcher_role_members_only(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["dispatcher"])
    car_application = request_with_car_assigned(world)
    world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": ""}
    )

    assert inbox_shows(world, world.dispatcher, car_application)
    assert inbox_shows(world, secretary, car_application)
    for outsider in (world.requester, world.supervisor, world.stranger):
        assert not inbox_shows(world, outsider, car_application)


def confirm_cancel_url(world, car_application):
    return f"{BASE}/{car_application.id}/cancel/confirm?organization_id={world.org.id}"


def request_cancel_requested(world):
    car_application = request_with_car_assigned(world)
    response = world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": ""}
    )
    assert response.status_code == 302
    car_application.reload()
    assert car_application.status == "cancel_requested"
    return car_application


def test_second_dispatcher_confirms_cancel_and_audit_log_names_them(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["dispatcher"])
    car_application = request_cancel_requested(world)

    response = world.client_for(secretary).post(
        confirm_cancel_url(world, car_application)
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.status == "cancelled"
    assert car_application.audit_logs[-1].action == "cancel_confirmed"
    assert car_application.audit_logs[-1].actor == secretary
    html = (
        world.client_for(world.requester)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )
    assert "Secretary Assistant" in html
    assert not inbox_shows(world, world.dispatcher, car_application)


@pytest.mark.parametrize("final_status", ["denied", "completed", "cancelled"])
def test_a_finished_request_cannot_be_cancelled(world, final_status):
    car_application = world.submit_domestic_request()
    car_application.status = final_status
    car_application.save()
    logs_before = len(car_application.audit_logs)

    world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": ""}
    )

    car_application.reload()
    assert car_application.status == final_status
    assert len(car_application.audit_logs) == logs_before


def test_a_request_already_awaiting_cancel_acknowledgement_cannot_be_cancelled_again(
    world,
):
    car_application = request_cancel_requested(world)
    logs_before = len(car_application.audit_logs)

    world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": "อีกครั้ง"}
    )

    car_application.reload()
    assert car_application.status == "cancel_requested"
    assert len(car_application.audit_logs) == logs_before


def test_car_and_driver_are_blocked_until_the_cancel_is_confirmed_then_released(world):
    cancelling = request_cancel_requested(world)
    waiting = request_at_dispatcher(world)

    world.client_for(world.dispatcher).post(
        approve_url(world, waiting), data=dispatch_data(world.car, world.driver)
    )
    waiting.reload()
    assert waiting.current_step == 1

    world.client_for(world.dispatcher).post(confirm_cancel_url(world, cancelling))
    world.client_for(world.dispatcher).post(
        approve_url(world, waiting), data=dispatch_data(world.car, world.driver)
    )

    waiting.reload()
    assert waiting.current_step == 2
    assert waiting.car == world.car


def test_only_a_dispatcher_role_member_can_confirm_a_cancel(world):
    car_application = request_cancel_requested(world)

    for outsider in (world.requester, world.stranger, world.supervisor):
        response = world.client_for(outsider).post(
            confirm_cancel_url(world, car_application)
        )
        # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือสถานะไม่เปลี่ยน
        assert response.status_code in (302, 403)
        car_application.reload()
        assert car_application.status == "cancel_requested"


def test_confirming_is_refused_unless_the_request_is_awaiting_cancel_acknowledgement(
    world,
):
    car_application = request_with_car_assigned(world)

    world.client_for(world.dispatcher).post(confirm_cancel_url(world, car_application))

    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.audit_logs[-1].action == "approved"


def detail_html(world, user, car_application):
    page = world.client_for(user).get(detail_url(world, car_application))
    assert page.status_code == 200
    return page.get_data(as_text=True)


def test_cancel_button_shows_only_to_the_creator_while_the_request_is_cancellable(world):
    car_application = world.submit_domestic_request()

    assert "ยกเลิกคำขอ" in detail_html(world, world.requester, car_application)
    for outsider in (world.supervisor, world.dispatcher, world.stranger):
        assert "ยกเลิกคำขอ" not in detail_html(world, outsider, car_application)

    for status in ("denied", "completed", "cancelled", "cancel_requested"):
        car_application.status = status
        car_application.save()
        assert "ยกเลิกคำขอ" not in detail_html(world, world.requester, car_application)


def test_acknowledge_button_shows_only_to_the_dispatcher_while_cancel_is_requested(
    world,
):
    car_application = request_cancel_requested(world)

    assert "รับทราบการยกเลิก" in detail_html(world, world.dispatcher, car_application)
    for outsider in (world.requester, world.supervisor, world.stranger):
        assert "รับทราบการยกเลิก" not in detail_html(world, outsider, car_application)


@pytest.mark.parametrize(
    "status, tone", [("cancel_requested", "badge-warning"), ("cancelled", "badge-ghost")]
)
def test_status_badge_shows_cancel_states_in_their_own_tone(world, status, tone):
    car_application = world.submit_domestic_request()
    car_application.status = status
    car_application.save()

    html = detail_html(world, world.requester, car_application)

    badge = html[html.index(f'data-status="{status}"') - 200 :]
    assert tone in badge.split("</span>")[0]


def test_only_the_creator_can_cancel_a_request(world):
    before_car = world.submit_domestic_request()
    after_car = request_with_car_assigned(world)

    for car_application in (before_car, after_car):
        status = car_application.status
        for outsider in (world.stranger, world.supervisor, world.dispatcher):
            response = world.client_for(outsider).post(
                cancel_url(world, car_application), data={"reason": ""}
            )
            # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือสถานะไม่เปลี่ยน
            assert response.status_code in (302, 403)
            car_application.reload()
            assert car_application.status == status


def test_submitting_notifies_the_division_head_but_not_the_requester(
    world, mock_redis_queue
):
    car_application = world.submit_domestic_request()

    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, host_url = jobs[0]
    assert (request_id, event) == (str(car_application.id), "submitted")
    assert recipients == [world.supervisor.email]
    assert host_url.startswith("http")


def test_supervisor_approval_notifies_every_member_with_the_dispatcher_role(
    world, create_user, assign_user_to_org, mock_redis_queue
):
    delegate = create_user("Delegate", "Dispatcher")
    assign_user_to_org(delegate, world.org, roles=["dispatcher"])
    car_application = world.submit_domestic_request()
    mock_redis_queue.reset_mock()

    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": "เห็นชอบ"}
    )

    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, _ = jobs[0]
    assert (request_id, event) == (str(car_application.id), "approved")
    assert sorted(recipients) == sorted([world.dispatcher.email, delegate.email])


def test_final_approval_tells_the_requester_and_the_driver_the_request_is_active(
    world, mock_redis_queue
):
    car_application = world.submit_domestic_request()
    for key in car_application.route_snapshot[:-1]:
        world.client_for(world.holders[key]).post(
            approve_url(world, car_application), data=step_data(world, key)
        )
    mock_redis_queue.reset_mock()

    last = car_application.route_snapshot[-1]
    world.client_for(world.holders[last]).post(
        approve_url(world, car_application), data=step_data(world, last)
    )

    car_application.reload()
    assert car_application.status == "active"
    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, _ = jobs[0]
    assert (request_id, event) == (str(car_application.id), "active")
    assert sorted(recipients) == sorted([world.requester.email, world.driver.email])


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

        def send_email(
            self, receiver, subject, body, html=False, steps=None, app_name=None
        ):
            sent.append(
                {"receiver": receiver, "subject": subject, "body": body, "html": html}
            )
            return True

    monkeypatch.setattr(utils.email_utils, "PSUSMTP", FakeSMTP)
    return sent


def test_email_job_sends_subject_and_body_with_trip_details_and_link(
    app, world, sent_emails
):
    car_application = world.submit_domestic_request()

    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(car_application.id),
            "submitted",
            [world.supervisor.email],
            "https://staging.example.test",
        )

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert email["receiver"] == world.supervisor.email
    assert "ระบบจองรถออนไลน์" in email["subject"]
    assert "กรุงเทพฯ" in email["body"]
    assert (
        f"https://staging.example.test/car_reservation/requests/{car_application.id}"
        f"?organization_id={world.org.id}"
    ) in email["body"]
    assert email["html"] is True


def test_active_email_names_requester_trip_times_car_and_driver_to_every_recipient(
    app, world, sent_emails
):
    car_application = request_with_car_assigned(world)
    car_application.departure_datetime = datetime.datetime(2026, 12, 25, 8, 30)
    car_application.return_datetime = datetime.datetime(2026, 12, 26, 17, 0)
    car_application.status = "active"
    car_application.save()

    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(car_application.id),
            "active",
            [world.requester.email, world.driver.email],
            "https://staging.example.test",
        )

    assert [email["receiver"] for email in sent_emails] == [
        world.requester.email,
        world.driver.email,
    ]
    body = sent_emails[0]["body"]
    assert "Requester One" in body
    assert "25 ธ.ค. 2569 08:30 น." in body
    assert "26 ธ.ค. 2569 17:00 น." in body
    assert "อนุมัติแล้ว" in body
    assert "กก 1234" in body
    assert "Driver One" in body
    assert "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ" in body


def test_denying_notifies_only_the_requester(world, mock_redis_queue):
    car_application = world.submit_domestic_request()
    mock_redis_queue.reset_mock()

    world.client_for(world.supervisor).post(
        deny_url(world, car_application), data={"comment": "ไม่จำเป็นต้องเดินทาง"}
    )

    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, _ = jobs[0]
    assert (request_id, event) == (str(car_application.id), "denied")
    assert recipients == [world.requester.email]


def test_submitting_saves_the_status_contact_and_shows_it_on_the_detail_page(world):
    data = world.request_data("domestic")
    data.update(contact_name="สมศรี ผู้ประสานงาน", contact_email="somsri@example.com")

    assert post_new(world, data).status_code == 302

    saved = models.CarReservation.objects(creator=world.requester).first()
    html = world.client_for(world.requester).get(detail_url(world, saved)).get_data(
        as_text=True
    )
    assert "สมศรี ผู้ประสานงาน" in html
    assert "somsri@example.com" in html


def test_submitting_without_a_contact_email_shows_the_form_again_and_saves_nothing(
    world,
):
    data = world.request_data("domestic")
    data["contact_email"] = ""

    response = post_new(world, data)

    assert response.status_code == 200
    assert models.CarReservation.objects(creator=world.requester).count() == 0


def test_new_request_form_is_prefilled_with_the_requesters_name_and_email(world):
    html = (
        world.client_for(world.requester)
        .get(f"{BASE}/new?organization_id={world.org.id}&type=domestic")
        .get_data(as_text=True)
    )

    assert re.search(
        rf'name="contact_email"[^>]*value="{re.escape(world.requester.email)}"', html
    )
    assert re.search(
        rf'name="contact_name"[^>]*value="{re.escape(world.requester.get_name())}"',
        html,
    )


def deny_after_submitting_with_contact(world, contact_email):
    data = world.request_data("domestic")
    data["contact_email"] = contact_email
    post_new(world, data)
    car_application = models.CarReservation.objects(creator=world.requester).first()
    world.client_for(world.supervisor).post(
        deny_url(world, car_application), data={"comment": "ไม่จำเป็นต้องเดินทาง"}
    )


def test_denying_also_emails_the_status_contact(world, mock_redis_queue):
    deny_after_submitting_with_contact(world, "secretary@example.com")

    recipients = email_jobs(mock_redis_queue, "denied")[0][2]
    assert recipients == [world.requester.email, "secretary@example.com"]


def test_contact_email_equal_to_the_requesters_is_emailed_only_once(
    world, mock_redis_queue
):
    deny_after_submitting_with_contact(world, world.requester.email)

    recipients = email_jobs(mock_redis_queue, "denied")[0][2]
    assert recipients == [world.requester.email]


def test_cancelling_after_assignment_notifies_the_dispatcher_to_acknowledge(
    world, mock_redis_queue
):
    car_application = request_with_car_assigned(world)
    mock_redis_queue.reset_mock()

    world.client_for(world.requester).post(
        cancel_url(world, car_application), data={"reason": "งานเลื่อน"}
    )

    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, _ = jobs[0]
    assert (request_id, event) == (str(car_application.id), "cancel_requested")
    assert recipients == [world.dispatcher.email]


def test_direct_cancel_notifies_the_requester_and_confirmed_cancel_adds_the_driver(
    world, mock_redis_queue
):
    before_car = world.submit_domestic_request()
    world.client_for(world.requester).post(
        cancel_url(world, before_car), data={"reason": "เปลี่ยนแผน"}
    )

    jobs = email_jobs(mock_redis_queue, "cancelled")
    assert [(job[0], job[2]) for job in jobs] == [
        (str(before_car.id), [world.requester.email])
    ]

    after_car = request_with_car_assigned(world)
    world.client_for(world.requester).post(
        cancel_url(world, after_car), data={"reason": "งานเลื่อน"}
    )
    mock_redis_queue.reset_mock()
    world.client_for(world.dispatcher).post(confirm_cancel_url(world, after_car))

    jobs = email_jobs(mock_redis_queue)
    assert len(jobs) == 1
    request_id, event, recipients, _ = jobs[0]
    assert (request_id, event) == (str(after_car.id), "cancelled")
    assert sorted(recipients) == sorted([world.requester.email, world.driver.email])


def save_default_template(world, event, subject, body):
    return models.EmailTemplate(
        name=f"car reservation {event}",
        subject=subject,
        body=body,
        type=f"car_reservation_{event}",
        organization=world.org,
        is_default=True,
    ).save()


def send_job(app, world, car_application, event, recipients):
    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(car_application.id),
            event,
            recipients,
            "https://staging.example.test",
        )


def test_email_job_renders_the_org_default_template_with_documented_variables(
    app, world, sent_emails
):
    car_application = world.submit_domestic_request()
    save_default_template(
        world,
        "submitted",
        "ขออนุมัติรถ {{ requester_name }}",
        "เรียน หัวหน้า\nปลายทาง: {{ destination }} ({{ organization_name }})\n{{ request_url }}",
    )

    send_job(app, world, car_application, "submitted", [world.supervisor.email])

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert email["subject"] == "ขออนุมัติรถ Requester One"
    assert "ปลายทาง: กรุงเทพฯ (Reservation Org)" in email["body"]
    assert f"/car_reservation/requests/{car_application.id}" in email["body"]
    assert "ระบบจองรถออนไลน์" not in email["subject"]


def test_email_job_falls_back_to_system_text_without_a_default_template_of_that_event(
    app, world, sent_emails
):
    car_application = world.submit_domestic_request()
    save_default_template(world, "denied", "หัวข้อของเหตุการณ์อื่น", "เนื้อหาอื่น")
    models.EmailTemplate(
        name="ร่าง",
        subject="หัวข้อร่าง",
        body="เนื้อหาร่าง",
        type="car_reservation_submitted",
        organization=world.org,
        is_default=False,
    ).save()

    send_job(app, world, car_application, "submitted", [world.supervisor.email])

    assert [email["subject"] for email in sent_emails] == [
        "ระบบจองรถออนไลน์: มีใบขอใช้รถรอการพิจารณาจากท่าน"
    ]


def test_email_template_cannot_reach_python_internals_and_the_email_still_goes_out(
    app, world, sent_emails
):
    car_application = world.submit_domestic_request()
    save_default_template(
        world,
        "submitted",
        "{{ ''.__class__.__mro__ }}",
        "{{ requester_name.__class__.__mro__[1].__subclasses__() }}",
    )

    send_job(app, world, car_application, "submitted", [world.supervisor.email])

    assert len(sent_emails) == 1
    email = sent_emails[0]
    assert "class" not in email["subject"] and "class" not in email["body"]
    assert email["subject"] == "ระบบจองรถออนไลน์: มีใบขอใช้รถรอการพิจารณาจากท่าน"


@pytest.fixture
def smtp_html(monkeypatch):
    """ดักที่ขอบ smtplib จริง เพื่อให้ PSUSMTP และ layout อีเมลทำงานจริง: คืน HTML ของแต่ละฉบับที่ส่ง"""
    import email as email_lib
    import smtplib

    pages = []

    class FakeServer:
        def __init__(self, host, port):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def quit(self):
            pass

        def sendmail(self, sender, receivers, raw):
            message = email_lib.message_from_string(raw)
            for part in message.walk():
                if part.get_content_type() == "text/html":
                    pages.append(part.get_payload(decode=True).decode("utf-8"))

    monkeypatch.setattr(smtplib, "SMTP", FakeServer)
    return pages


def test_reservation_emails_carry_the_car_reservation_app_name_not_diis(
    app, world, smtp_html
):
    car_application = world.submit_domestic_request()

    send_job(app, world, car_application, "submitted", [world.supervisor.email])

    assert len(smtp_html) == 1
    assert ">ระบบจองรถ</div>" in smtp_html[0]
    assert "DIIS INVENTORY" not in smtp_html[0]


def test_other_systems_emails_keep_the_default_app_name(app, smtp_html):
    with app.app_context():
        smtp = utils.email_utils.PSUSMTP(app.config)
        smtp.login()
        smtp.send_email("someone@test.com", "หัวข้อ", "เนื้อหา", html=True)

    assert len(smtp_html) == 1
    assert "DIIS INVENTORY" in smtp_html[0]


def edit_url(world, car_application):
    return f"{BASE}/{car_application.id}/edit?organization_id={world.org.id}"


def test_requester_edits_own_request_while_it_waits_at_the_first_step(world):
    car_application = world.submit_domestic_request()
    data = world.request_data()
    data.update(
        location="เชียงใหม่",
        request_reason="อบรมเชิงปฏิบัติการ",
        departure_time="09:30",
    )

    response = world.client_for(world.requester).post(
        edit_url(world, car_application), data=data
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.location == "เชียงใหม่"
    assert car_application.request_reason == "อบรมเชิงปฏิบัติการ"
    assert car_application.departure_datetime.strftime("%H:%M") == "09:30"
    assert car_application.status == "pending"
    assert car_application.current_step == 0
    assert [log.action for log in car_application.audit_logs] == [
        "submitted",
        "edited",
    ]
    assert car_application.audit_logs[-1].actor == world.requester


def changes_of(log):
    """รายการแก้ไขของ log หนึ่งรายการเป็น {ชื่อข้อมูล: (เดิม, ใหม่)}"""
    return {change.label: (change.old, change.new) for change in log.changes}


def test_edit_log_records_exactly_the_fields_that_changed(world):
    car_application = world.submit_domestic_request()
    data = world.request_data()
    data.update(
        location="เชียงใหม่",
        request_reason="อบรมเชิงปฏิบัติการ",
        departure_time="09:30",
    )

    world.client_for(world.requester).post(edit_url(world, car_application), data=data)

    car_application.reload()
    assert changes_of(car_application.audit_logs[-1]) == {
        "สถานที่ปฏิบัติงาน": ("กรุงเทพฯ", "เชียงใหม่"),
        "วัตถุประสงค์การเดินทาง": ("ประชุมวิชาการ", "อบรมเชิงปฏิบัติการ"),
        "เวลาออกเดินทาง": ("08:00", "09:30"),
    }


def test_editing_without_any_change_logs_an_edit_with_no_changes(world):
    car_application = world.submit_domestic_request()

    world.client_for(world.requester).post(
        edit_url(world, car_application), data=world.request_data()
    )

    car_application.reload()
    last = car_application.audit_logs[-1]
    assert last.action == "edited"
    assert last.comment == "ไม่มีการเปลี่ยนแปลง"
    assert list(last.changes) == []


def test_edit_log_shows_airport_passengers_dates_and_choices_as_readable_text(world):
    car_application = world.submit_request("airport")
    data = world.request_data("airport")
    new_flight_date = datetime.date.today() + datetime.timedelta(days=22)
    data.update(
        transfer="dropoff",
        flight_date=new_flight_date.isoformat(),
        in_office_of_president="y",
        cost_responsibilities=["เบี้ยเลี้ยง", "ค่าน้ำมันเชื้อเพลิง"],
        **{
            "passengers-1-name": "สมหญิง รักดี",
            "passengers-1-phone": "089-333-4444",
        },
    )

    world.client_for(world.requester).post(edit_url(world, car_application), data=data)

    car_application.reload()
    assert changes_of(car_application.audit_logs[-1]) == {
        "ต้องการให้รถไป": ("รับ", "ส่ง"),
        "วันที่": (
            (datetime.date.today() + datetime.timedelta(days=20)).strftime("%d/%m/%Y"),
            new_flight_date.strftime("%d/%m/%Y"),
        ),
        "รายชื่อผู้โดยสาร": (
            "สมชาย ใจดี (089-111-2222)",
            "สมชาย ใจดี (089-111-2222), สมหญิง รักดี (089-333-4444)",
        ),
        "หน่วยงานในสำนักงานอธิการบดี": ("ไม่ใช่", "ใช่"),
        "ยินดีรับผิดชอบ": ("-", "ค่าน้ำมันเชื้อเพลิง, เบี้ยเลี้ยง"),
    }


def test_edit_log_names_the_attached_project_file_of_an_abroad_request(world):
    car_application = world.submit_request("abroad")
    data = world.request_data("abroad")
    data["project_file"] = project_file(b"%PDF-1.4 v2", "project_v2.pdf")

    world.client_for(world.requester).post(edit_url(world, car_application), data=data)

    car_application.reload()
    assert changes_of(car_application.audit_logs[-1]) == {
        "เอกสารโครงการ": ("project.pdf", "project_v2.pdf")
    }


def test_requester_cannot_edit_once_the_supervisor_has_approved(world):
    car_application = world.submit_domestic_request()
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    data = world.request_data()
    data["location"] = "เชียงใหม่"

    response = world.client_for(world.requester).post(
        edit_url(world, car_application), data=data
    )

    # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือข้อมูลไม่เปลี่ยน
    assert response.status_code in (302, 403)
    assert not response.headers.get("Location", "").startswith(BASE)
    car_application.reload()
    assert car_application.location == "กรุงเทพฯ"
    assert "edited" not in [log.action for log in car_application.audit_logs]


def test_nobody_but_the_requester_can_edit_the_request(world):
    car_application = world.submit_domestic_request()
    data = world.request_data()
    data["location"] = "เชียงใหม่"

    for other in (world.supervisor, world.dispatcher, world.stranger):
        client = world.client_for(other)
        # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือไม่ได้ไปหน้าฟอร์มและข้อมูลไม่เปลี่ยน
        got = client.get(edit_url(world, car_application))
        assert got.status_code in (302, 403)
        assert "name=\"phone\"" not in got.get_data(as_text=True)
        posted = client.post(edit_url(world, car_application), data=data)
        assert posted.status_code in (302, 403)
        assert not posted.headers.get("Location", "").startswith(BASE)

    car_application.reload()
    assert car_application.location == "กรุงเทพฯ"


@pytest.mark.parametrize("request_type", ["domestic", "airport", "welfare", "abroad"])
def test_edit_form_of_every_request_type_opens_with_the_saved_values(
    world, request_type
):
    car_application = world.submit_request(request_type)

    page = world.client_for(world.requester).get(edit_url(world, car_application))

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert 'value="081-234-5678"' in html
    assert 'value="08:00"' in html
    assert "บันทึกการแก้ไข" in html


def test_abroad_request_is_edited_without_attaching_the_project_file_again(world):
    car_application = world.submit_request("abroad")
    data = world.request_data("abroad")
    del data["project_file"]
    data["country"] = "สิงคโปร์"

    response = world.client_for(world.requester).post(
        edit_url(world, car_application), data=data
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.details.country == "สิงคโปร์"
    assert car_application.project_file.read() == b"%PDF-1.4 project"


def test_editing_the_province_scope_re_snapshots_the_route(world):
    car_application = world.submit_domestic_request()
    data = world.request_data(province_scope="out_of_province")

    response = world.client_for(world.requester).post(
        edit_url(world, car_application), data=data
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.route_snapshot[-1] == "physical_director"


def test_detail_shows_the_edit_button_only_to_the_requester_before_approval(world):
    car_application = world.submit_domestic_request()

    def shows_edit(user):
        page = world.client_for(user).get(detail_url(world, car_application))
        return 'data-role="edit-request"' in page.get_data(as_text=True)

    assert shows_edit(world.requester)
    assert not shows_edit(world.supervisor)

    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    assert not shows_edit(world.requester)


WORKLOAD_NOW = datetime.datetime(2030, 6, 15, 12, 0)


def workload_job(world, driver, departure, hours, status="completed", **extra):
    """งานของ driver ที่ออกเดินทาง departure และกลับหลังจากนั้น hours ชั่วโมง"""
    job = assigned_request(
        world,
        departure,
        departure + datetime.timedelta(hours=hours),
        status=status,
        car=world.car,
        driver=driver,
    )
    for name, value in extra.items():
        setattr(job, name, value)
    return job.save()


def workload_rows(world, window_start=None, window_end=None):
    window_start = window_start or WORKLOAD_NOW + datetime.timedelta(days=30)
    window_end = window_end or window_start + datetime.timedelta(hours=4)
    return {
        row.driver.get_name(): row
        for row in flow.driver_workload(
            world.org,
            now=WORKLOAD_NOW,
            window_start=window_start,
            window_end=window_end,
        )
    }


def test_driver_workload_counts_in_hours_ot_jobs_and_hours_of_the_last_30_days(world):
    day = datetime.timedelta(days=1)
    # 3 ชม. (ตามเวลากลับตามใบขอ เพราะยังไม่มี completed_at) ในเวลา
    workload_job(world, world.driver, WORKLOAD_NOW - 5 * day, 3)
    # 5 ชม. ตามเวลาเริ่ม/ปิดงานจริง (ไม่ใช่ตามใบขอ) และเป็น OT
    workload_job(
        world,
        world.driver,
        WORKLOAD_NOW - 3 * day,
        1,
        is_overtime=True,
        started_at=WORKLOAD_NOW - 3 * day + datetime.timedelta(hours=1),
        completed_at=WORKLOAD_NOW - 3 * day + datetime.timedelta(hours=6),
    )
    # ไม่นับ: เกิน 30 วัน, ไม่อนุมัติ, ยกเลิก
    workload_job(world, world.driver, WORKLOAD_NOW - 31 * day, 9)
    workload_job(world, world.driver, WORKLOAD_NOW - 2 * day, 9, status="denied")
    workload_job(world, world.driver, WORKLOAD_NOW - 2 * day, 9, status="cancelled")
    idle = world.add_driver("Idle", "Driver")

    rows = workload_rows(world)

    one = rows["Driver One"]
    assert (one.in_hours_jobs, one.ot_jobs, one.hours) == (1, 1, 8.0)
    assert (one.upcoming, one.busy) == (0, False)
    zero = rows[idle.get_name()]
    assert (zero.in_hours_jobs, zero.ot_jobs, zero.hours) == (0, 0, 0.0)



def test_driver_workload_counts_upcoming_jobs_flags_a_clash_and_sorts_least_loaded_first(
    world,
):
    day = datetime.timedelta(days=1)
    window_start = WORKLOAD_NOW + 10 * day
    window_end = window_start + datetime.timedelta(hours=4)
    # Driver One: 2 งานล่าสุด 2 ชม. + 2 ชม. = 4 ชม. และมีงานข้างหน้า 2 งาน (เฉพาะ active)
    workload_job(world, world.driver, WORKLOAD_NOW - 4 * day, 2)
    workload_job(world, world.driver, WORKLOAD_NOW - 2 * day, 2)
    workload_job(world, world.driver, WORKLOAD_NOW + 3 * day, 2, status="active")
    workload_job(world, world.driver, WORKLOAD_NOW + 4 * day, 2, status="active")
    workload_job(world, world.driver, WORKLOAD_NOW + 5 * day, 2, status="denied")
    # Light: 1 งานล่าสุด 1 ชม. และงานข้างหน้าที่ชนช่วงเวลาที่กำลังจัด
    light = world.add_driver("Light", "Driver")
    workload_job(world, light, WORKLOAD_NOW - 1 * day, 1)
    workload_job(
        world, light, window_start + datetime.timedelta(hours=2), 3, status="active"
    )
    # Lighter: 1 งานล่าสุด 0.5 ชม. (งานเท่ากับ Light แต่ชั่วโมงน้อยกว่า)
    lighter = world.add_driver("Lighter", "Driver")
    workload_job(world, lighter, WORKLOAD_NOW - 1 * day, 0.5)
    # Idle: ไม่มีงานเลย
    world.add_driver("Idle", "Driver")

    rows = flow.driver_workload(
        world.org, now=WORKLOAD_NOW, window_start=window_start, window_end=window_end
    )

    assert [
        (row.driver.get_name(), row.upcoming, row.busy, row.hours) for row in rows
    ] == [
        ("Idle Driver", 0, False, 0.0),
        ("Lighter Driver", 0, False, 0.5),
        ("Light Driver", 1, True, 1.0),
        ("Driver One", 2, False, 4.0),
    ]


def test_dispatcher_detail_lists_drivers_least_loaded_first_and_marks_the_busy_one(
    world,
):
    now = datetime.datetime.now().replace(microsecond=0)
    day = datetime.timedelta(days=1)
    idle = world.add_driver("Idle", "Driver")
    busy = world.add_driver("Busy", "Driver")
    car_application = request_at_dispatcher(world)
    # Driver One งานล่าสุด 2 งาน, Busy 1 งาน ส่วน Idle ไม่มี
    workload_job(world, world.driver, now - 4 * day, 2)
    workload_job(world, world.driver, now - 2 * day, 2)
    workload_job(world, busy, now - 3 * day, 1)
    workload_job(
        world,
        busy,
        car_application.departure_datetime + datetime.timedelta(hours=1),
        2,
        status="active",
    )

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    rows = re.findall(r'data-role="driver-row" data-driver-id="(\w+)" data-busy="(\w+)"', html)
    assert rows == [
        (str(idle.id), "false"),
        (str(busy.id), "true"),
        (str(world.driver.id), "false"),
    ]
    assert html.count('data-role="busy-badge"') == 1
    assert 'data-role="workload-dashboard-link"' in html


def test_dispatcher_driver_radios_are_rendered_by_the_wtforms_radio_field_in_workload_order(
    world,
):
    idle = world.add_driver("Idle", "Driver")
    car_application = request_at_dispatcher(world)

    html = (
        world.client_for(world.dispatcher)
        .get(detail_url(world, car_application))
        .get_data(as_text=True)
    )

    doc = lxml_html.fromstring(html)
    rows = doc.xpath("//tr[@data-role='driver-row']")
    radios = [row.xpath(".//input[@type='radio']")[0] for row in rows]
    # id ของ RadioField คือ driver-<ลำดับ> และ value เป็น id ของ พขร. ในแถวนั้น (เรียงตามภาระงาน)
    assert [(r.get("id"), r.get("name"), r.get("value")) for r in radios] == [
        (f"driver-{index}", "driver", row.get("data-driver-id"))
        for index, row in enumerate(rows)
    ]
    assert {r.get("value") for r in radios} == {str(idle.id), str(world.driver.id)}
    for radio in radios:
        assert doc.xpath(f"//label[@for='{radio.get('id')}']")
        assert "radio-primary" in radio.get("class")


def test_dispatch_approve_without_a_driver_choice_is_refused_and_nothing_advances(
    world,
):
    car_application = request_at_dispatcher(world)

    response = world.client_for(world.dispatcher).post(
        approve_url(world, car_application),
        data={"car": str(world.car.id), "driver": "not-a-driver-id"},
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1
    assert car_application.driver is None


URGENT_URL = f"{BASE}/urgent"


def urgent_url(world):
    return f"{URGENT_URL}?organization_id={world.org.id}"


def urgent_data(world, days_ahead=1, **overrides):
    """ฟอร์มคำขอเร่งด่วนของผู้จัดรถ: ฟิลด์ domestic + ผู้ใช้รถจริง + เลือกรถ/พขร."""
    data = world.request_data("domestic", days_ahead=days_ahead)
    data.update(
        contact_name="ผู้ใช้รถ ตัวจริง",
        contact_email="actual.user@example.com",
        car=str(world.car.id),
        driver=str(world.driver.id),
    )
    data.update(overrides)
    return data


def test_dispatcher_creates_an_urgent_request_that_skips_to_the_physical_director(
    world,
):
    response = world.client_for(world.dispatcher).post(
        urgent_url(world), data=urgent_data(world, is_overtime="y")
    )
    assert response.status_code == 302, response.get_data(as_text=True)

    reservation = models.CarReservation.objects(organization=world.org).first()
    assert reservation.is_urgent is True
    assert reservation.creator == world.dispatcher
    assert reservation.request_type == "domestic"
    assert reservation.route_snapshot == ["dispatcher", "physical_director"]
    assert reservation.current_step == 1
    assert reservation.status == "pending"
    assert reservation.car == world.car
    assert reservation.driver == world.driver
    assert reservation.is_overtime is True
    assert reservation.contact_email == "actual.user@example.com"
    [dispatch] = reservation.step_approvals
    assert (dispatch.step_key, dispatch.decision, dispatch.decided_by) == (
        "dispatcher",
        "approved",
        world.dispatcher,
    )
    approved = [log for log in reservation.audit_logs if log.action == "approved"]
    assert "กก 1234" in approved[0].comment
    assert world.driver.get_name() in approved[0].comment


def create_urgent_request(world, **overrides):
    response = world.client_for(world.dispatcher).post(
        urgent_url(world), data=urgent_data(world, **overrides)
    )
    assert response.status_code == 302, response.get_data(as_text=True)
    return models.CarReservation.objects(organization=world.org).order_by("-id").first()


def test_physical_director_approves_an_urgent_request_and_the_contact_is_emailed(
    world, mock_redis_queue
):
    reservation = create_urgent_request(world)
    director = world.holders["physical_director"]
    assert inbox_shows(world, director, reservation)
    assert email_jobs(mock_redis_queue, "approved")[-1][2] == [director.email]

    response = world.client_for(director).post(
        approve_url(world, reservation), data={"comment": ""}
    )

    assert response.status_code == 302
    reservation.reload()
    assert reservation.status == "active"
    [active] = email_jobs(mock_redis_queue, "active")
    assert "actual.user@example.com" in active[2]


@pytest.mark.parametrize("who", ["requester", "supervisor", "stranger"])
def test_only_a_dispatcher_can_open_or_submit_the_urgent_form(world, who):
    client = world.client_for(getattr(world, who))

    got = client.get(urgent_url(world))
    posted = client.post(urgent_url(world), data=urgent_data(world))

    assert got.status_code in (302, 403)
    assert posted.status_code in (302, 403)
    assert models.CarReservation.objects.count() == 0


def test_the_urgent_form_is_domestic_only(world):
    client = world.client_for(world.dispatcher)

    assert client.get(urgent_url(world) + "&type=airport").status_code == 404
    page = client.get(urgent_url(world)).get_data(as_text=True)
    assert 'name="province_scope"' in page
    assert 'name="transfer"' not in page


def test_urgent_request_is_not_blocked_by_the_holiday_only_vehicle_rule(world):
    weekday = upcoming(0)  # วันจันทร์
    data = urgent_data(world, vehicle_kind="เก๋ง")
    data.update(trip_on(data, weekday, weekday))

    response = world.client_for(world.dispatcher).post(urgent_url(world), data=data)

    assert response.status_code == 302


def test_urgent_request_for_a_car_that_is_already_booked_is_refused(world):
    first = create_urgent_request(world)

    clash = world.client_for(world.dispatcher).post(
        urgent_url(world), data=urgent_data(world)
    )

    assert clash.status_code == 200
    assert "กก 1234" in clash.get_data(as_text=True)
    assert models.CarReservation.objects.count() == 1
    assert models.CarReservation.objects.first() == first


def test_urgent_request_returning_before_departure_is_refused(world):
    data = urgent_data(world)
    data["return_date"] = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()

    response = world.client_for(world.dispatcher).post(urgent_url(world), data=data)

    assert response.status_code == 200
    assert "วันกลับต้องไม่ก่อนวันออกเดินทาง" in response.get_data(as_text=True)
    assert models.CarReservation.objects.count() == 0


def test_sidebar_offers_the_urgent_request_link_only_to_dispatchers(world):
    def sidebar_of(user):
        page = world.client_for(user).get(f"{BASE}/?organization_id={world.org.id}")
        assert page.status_code == 200
        return page.get_data(as_text=True)

    assert f'href="{URGENT_URL}?organization_id={world.org.id}"' in sidebar_of(
        world.dispatcher
    )
    assert "ขอใช้รถเร่งด่วน" in sidebar_of(world.dispatcher)
    assert "ขอใช้รถเร่งด่วน" not in sidebar_of(world.requester)


SETTINGS_URL = "/car_reservation/settings"


def settings_url(world):
    return f"{SETTINGS_URL}?organization_id={world.org.id}"


@pytest.fixture
def org_admin(world, create_user, assign_user_to_org):
    admin = create_user("OrgAdmin", "Six")
    assign_user_to_org(admin, world.org, roles=["admin"])
    return admin


def short_notice_page(world):
    response = post_new(world, world.request_data(days_ahead=1))
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_short_notice_confirmation_shows_the_phone_org_admins_configured(
    world, org_admin
):
    saved = world.client_for(org_admin).post(
        settings_url(world), data={"car_reservation_contact_phone": "074-123456"}
    )
    assert saved.status_code == 302

    html = short_notice_page(world)

    assert "ขอรถล่วงหน้าน้อยกว่า 3 วันทำการ" in html
    assert 'href="tel:074-123456"' in html


def test_short_notice_confirmation_has_no_phone_line_until_one_is_configured(world):
    html = short_notice_page(world)

    assert "ขอรถล่วงหน้าน้อยกว่า 3 วันทำการ" in html
    assert "tel:" not in html


@pytest.mark.parametrize("who", ["requester", "dispatcher", "stranger"])
def test_only_org_admins_can_open_or_change_the_car_reservation_settings(world, who):
    client = world.client_for(getattr(world, who))

    got = client.get(settings_url(world))
    posted = client.post(
        settings_url(world), data={"car_reservation_contact_phone": "074-999999"}
    )

    assert got.status_code in (302, 403)
    assert posted.status_code in (302, 403)
    world.org.reload()
    assert not world.org.car_reservation_contact_phone


def test_sidebar_offers_the_settings_link_only_to_org_admins(world, org_admin):
    def sidebar_of(user):
        page = world.client_for(user).get(f"{BASE}/?organization_id={world.org.id}")
        return page.get_data(as_text=True)

    assert f'href="{SETTINGS_URL}?organization_id={world.org.id}"' in sidebar_of(
        org_admin
    )
    assert f'href="{SETTINGS_URL}?' not in sidebar_of(world.requester)


INSERT_URL = f"{BASE}/insert"


def insert_url(world):
    return f"{INSERT_URL}?organization_id={world.org.id}"


@pytest.fixture
def insert_world(world):
    """พขร. world.driver มีงาน active ของวัน DAY (08:00-17:00) แล้ว และมีรถคันที่สองไว้ใช้กับงานแทรก"""
    world.second_car = models.vehicles.Car(
        license_plate="ขข 5678", organization=world.org, status="active"
    ).save()
    world.main_job = assigned_request(
        world,
        DAY,
        DAY + datetime.timedelta(hours=9),
        car=world.car,
        driver=world.driver,
    )
    return world


def insert_data(world, **overrides):
    day = DAY.date().isoformat()
    data = {
        "driver": str(world.driver.id),
        "car": str(world.second_car.id),
        "departure_date": day,
        "departure_time": "10:00",
        "return_date": day,
        "return_time": "11:30",
        "location": "สนามบินหาดใหญ่",
        "request_reason": "ไปรับพัสดุด่วน",
        "insert_scope": "in_province",
        "contact_name": "ผู้ใช้รถ ตัวจริง",
        "contact_email": "actual.user@example.com",
    }
    data.update(overrides)
    return data


def post_insert(world, **overrides):
    return world.client_for(world.dispatcher).post(
        insert_url(world), data=insert_data(world, **overrides)
    )


def insert_jobs(world):
    return models.CarReservation.objects(organization=world.org, is_insert=True)


def test_dispatcher_adds_an_insert_job_that_is_active_at_once_and_logged(insert_world):
    response = post_insert(insert_world, is_overtime="y")
    assert response.status_code == 302, response.get_data(as_text=True)

    [job] = insert_jobs(insert_world)
    assert job.status == "active"
    assert job.request_type == "domestic"
    assert job.province_scope == "in_province"
    assert job.insert_scope == "in_province"
    assert job.creator == insert_world.dispatcher
    assert job.car == insert_world.second_car
    assert job.driver == insert_world.driver
    assert job.is_overtime is True
    assert job.location == "สนามบินหาดใหญ่"
    assert job.contact_email == "actual.user@example.com"
    assert job.departure_datetime == DAY + datetime.timedelta(hours=2)
    assert job.return_datetime == DAY + datetime.timedelta(hours=3, minutes=30)
    assert [(log.action, log.comment) for log in job.audit_logs] == [
        ("submitted", "งานแทรก")
    ]


TASKS_BASE = "/car_reservation/tasks"


def drivers_task_list(world):
    page = world.client_for(world.driver).get(
        f"{TASKS_BASE}/?organization_id={world.org.id}"
    )
    assert page.status_code == 200
    return page.get_data(as_text=True)


def test_insert_job_shows_up_in_the_drivers_task_list_with_an_insert_badge(
    insert_world,
):
    post_insert(insert_world, location="สนามบินหาดใหญ่")

    html = drivers_task_list(insert_world)

    cards = html.split('data-role="task-card"')[1:]
    [insert_card] = [card for card in cards if "สนามบินหาดใหญ่" in card]
    assert 'data-role="insert-badge"' in insert_card
    assert "งานแทรก" in insert_card
    assert "งานแทรก" not in [card for card in cards if "ที่อื่น" in card][0]


def test_driver_starts_and_closes_an_insert_job_with_its_own_mileage(insert_world):
    post_insert(insert_world)
    [job] = insert_jobs(insert_world)
    client = insert_world.client_for(insert_world.driver)

    started = client.post(
        f"{TASKS_BASE}/{job.id}/start?organization_id={insert_world.org.id}"
    )
    closed = client.post(
        f"{TASKS_BASE}/{job.id}/close?organization_id={insert_world.org.id}",
        data={
            "mileage_out": "500",
            "mileage_in": "512",
            "expense_case": "fleet_card",
            "mileage_photo_out": (io.BytesIO(PNG_BYTES), "out.png"),
            "mileage_photo_in": (io.BytesIO(PNG_BYTES), "in.png"),
        },
    )

    assert started.status_code == 302
    assert closed.status_code == 302, closed.get_data(as_text=True)
    job.reload()
    assert job.status == "completed"
    assert job.started_at is not None
    assert job.distance_km == 12
    insert_world.main_job.reload()
    assert insert_world.main_job.status == "active"
    assert insert_world.main_job.last_mileage is None


@pytest.mark.parametrize("scope", ["out_of_province", "abroad", ""])
def test_insert_job_scope_must_be_in_campus_or_in_province(insert_world, scope):
    response = post_insert(insert_world, insert_scope=scope)

    assert response.status_code == 200
    assert insert_jobs(insert_world).count() == 0


def test_insert_job_in_campus_scope_is_accepted(insert_world):
    assert post_insert(insert_world, insert_scope="in_campus").status_code == 302

    [job] = insert_jobs(insert_world)
    assert job.insert_scope == "in_campus"
    assert job.province_scope == "in_province"


def test_insert_job_must_end_after_it_starts(insert_world):
    response = post_insert(insert_world, return_time="10:00")

    assert response.status_code == 200
    assert "เวลาสิ้นสุดต้องหลังเวลาเริ่ม" in response.get_data(as_text=True)
    assert insert_jobs(insert_world).count() == 0


def test_insert_job_is_refused_for_a_driver_with_no_other_job_that_day(insert_world):
    next_day = (DAY.date() + datetime.timedelta(days=1)).isoformat()

    response = post_insert(
        insert_world, departure_date=next_day, return_date=next_day
    )

    assert response.status_code == 200
    assert "พนักงานขับรถไม่มีงานในวันนี้" in response.get_data(as_text=True)
    assert insert_jobs(insert_world).count() == 0


@pytest.mark.parametrize("status", ["pending", "completed", "denied", "cancelled"])
def test_only_an_active_job_of_the_driver_counts_as_a_job_that_day(
    insert_world, status
):
    insert_world.main_job.status = status
    insert_world.main_job.save()

    response = post_insert(insert_world)

    assert response.status_code == 200
    assert "พนักงานขับรถไม่มีงานในวันนี้" in response.get_data(as_text=True)
    assert insert_jobs(insert_world).count() == 0


def test_another_drivers_job_does_not_count_for_the_chosen_driver(insert_world):
    idle = insert_world.add_driver("Idle", "Driver")

    response = post_insert(insert_world, driver=str(idle.id))

    assert response.status_code == 200
    assert "พนักงานขับรถไม่มีงานในวันนี้" in response.get_data(as_text=True)


def test_insert_job_for_a_car_that_is_already_booked_is_refused(insert_world):
    # รถคันที่สองถูกจองไว้ในช่วงเวลาเดียวกันโดย พขร. อีกคน
    assigned_request(
        insert_world,
        DAY + datetime.timedelta(hours=1),
        DAY + datetime.timedelta(hours=4),
        car=insert_world.second_car,
        driver=insert_world.add_driver("Other", "Driver"),
    )

    response = post_insert(insert_world)

    assert response.status_code == 200
    assert "ขข 5678" in response.get_data(as_text=True)
    assert insert_jobs(insert_world).count() == 0


@pytest.mark.parametrize("who", ["requester", "supervisor", "stranger"])
def test_only_a_dispatcher_can_open_or_submit_the_insert_form(insert_world, who):
    client = insert_world.client_for(getattr(insert_world, who))

    got = client.get(insert_url(insert_world))
    posted = client.post(insert_url(insert_world), data=insert_data(insert_world))

    assert got.status_code in (302, 403)
    assert posted.status_code in (302, 403)
    assert insert_jobs(insert_world).count() == 0


def test_insert_job_page_shows_the_insert_badge_on_the_detail(insert_world):
    post_insert(insert_world)
    [job] = insert_jobs(insert_world)

    page = insert_world.client_for(insert_world.dispatcher).get(
        detail_url(insert_world, job)
    )

    assert 'data-role="insert-badge"' in page.get_data(as_text=True)


def test_sidebar_offers_the_insert_job_link_only_to_dispatchers(world):
    def sidebar_of(user):
        page = world.client_for(user).get(f"{BASE}/?organization_id={world.org.id}")
        assert page.status_code == 200
        return page.get_data(as_text=True)

    assert f'href="{INSERT_URL}?organization_id={world.org.id}"' in sidebar_of(
        world.dispatcher
    )
    assert "เพิ่มงานแทรก" in sidebar_of(world.dispatcher)
    assert "เพิ่มงานแทรก" not in sidebar_of(world.requester)


CLOSED_AT = datetime.datetime(2030, 3, 10, 17, 0)


@pytest.mark.parametrize(
    "now, expected",
    [
        (CLOSED_AT + datetime.timedelta(hours=1), "pending"),
        (CLOSED_AT + datetime.timedelta(days=2), "pending"),
        (CLOSED_AT + datetime.timedelta(days=4), "auto_confirmed"),
    ],
    ids=["same day", "2 days", "4 days"],
)
def test_close_confirmation_turns_into_auto_confirmed_after_3_days_without_a_reply(
    now, expected
):
    reservation = models.CarReservation(completed_at=CLOSED_AT)

    assert reservation.close_confirmation_status(now) == expected


@pytest.mark.parametrize("answer", ["confirmed", "disputed"])
def test_an_answered_close_confirmation_stays_as_answered_after_3_days(answer):
    reservation = models.CarReservation(
        completed_at=CLOSED_AT, close_confirmation=answer
    )

    assert (
        reservation.close_confirmation_status(CLOSED_AT + datetime.timedelta(days=4))
        == answer
    )


def test_a_trip_that_is_not_closed_has_no_close_confirmation_status():
    reservation = models.CarReservation()

    assert reservation.close_confirmation_status(CLOSED_AT) is None


CONFIRM_ENDED_AT = datetime.datetime.now().replace(second=0, microsecond=0)


def closed_trip(world, closed_ago=datetime.timedelta(days=1), **extra):
    """งานที่ พขร. ปิดแล้วเมื่อ closed_ago ที่แล้ว (เริ่มงานก่อนปิด 3 ชม.) ผู้ขอคือ world.requester"""
    completed = CONFIRM_ENDED_AT - closed_ago
    job = assigned_request(
        world,
        DAY,
        DAY + datetime.timedelta(hours=9),
        status="completed",
        car=world.car,
        driver=world.driver,
    )
    job.started_at = completed - datetime.timedelta(hours=3)
    job.completed_at = completed
    for name, value in extra.items():
        setattr(job, name, value)
    return job.save()


def confirmation_url(world, reservation):
    return f"{BASE}/{reservation.id}/close_confirmation?organization_id={world.org.id}"


def confirmation_section(world, reservation, user=None):
    page = world.client_for(user or world.requester).get(detail_url(world, reservation))
    html = page.get_data(as_text=True)
    if 'data-role="close-confirmation"' not in html:
        return ""
    return html.split('data-role="close-confirmation"')[1].split("</section>")[0]


def test_requester_sees_the_recorded_trip_times_and_the_two_answer_buttons(world):
    job = closed_trip(world)

    section = confirmation_section(world, job)

    assert job.started_at.strftime("%d/%m/%Y %H:%M") in section
    assert job.completed_at.strftime("%d/%m/%Y %H:%M") in section
    assert 'value="correct"' in section
    assert 'value="incorrect"' in section
    assert 'name="actual_end_date"' in section
    assert 'name="actual_end_time"' in section


def test_requester_confirms_the_recorded_times_are_correct(world):
    job = closed_trip(world)

    response = world.client_for(world.requester).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )

    assert response.status_code == 302, response.get_data(as_text=True)
    job.reload()
    assert job.close_confirmation == "confirmed"
    assert job.close_confirmed_by == world.requester
    assert job.close_confirmed_at is not None
    assert job.audit_logs[-1].action == "close_confirmed"
    assert job.audit_logs[-1].actor == world.requester
    assert 'data-status="confirmed"' in confirmation_section(world, job)


def dispute(world, job, user=None, **overrides):
    data = {
        "decision": "incorrect",
        "actual_end_date": CONFIRM_ENDED_AT.date().isoformat(),
        "actual_end_time": "20:30",
        "note": "พขร. กดปิดงานช้า",
    }
    data.update(overrides)
    return world.client_for(user or world.requester).post(
        confirmation_url(world, job), data=data
    )


def test_requester_disputes_the_closing_time_and_dispatchers_are_emailed(
    world, mock_redis_queue
):
    job = closed_trip(world)

    response = dispute(world, job)

    assert response.status_code == 302, response.get_data(as_text=True)
    job.reload()
    assert job.close_confirmation == "disputed"
    assert job.close_confirmed_by == world.requester
    assert job.close_reported_end == CONFIRM_ENDED_AT.replace(hour=20, minute=30)
    assert job.close_dispute_note == "พขร. กดปิดงานช้า"
    assert job.audit_logs[-1].action == "close_disputed"
    assert "20:30" in job.audit_logs[-1].comment
    assert 'data-status="disputed"' in confirmation_section(world, job)
    assert "20:30" in confirmation_section(world, job)
    [email] = email_jobs(mock_redis_queue, "close_disputed")
    assert email[0] == str(job.id)
    assert email[2] == [world.dispatcher.email]


def test_disputing_without_the_actual_end_time_is_refused(world, mock_redis_queue):
    job = closed_trip(world)

    response = dispute(world, job, actual_end_date="", actual_end_time="")

    assert response.status_code == 302
    job.reload()
    assert job.close_confirmation is None
    assert email_jobs(mock_redis_queue, "close_disputed") == []


def test_close_disputed_email_tells_the_dispatcher_what_the_requester_reported(
    app, world, sent_emails
):
    job = closed_trip(world)
    dispute(world, job)

    with app.app_context():
        utils.car_reservation_email.send_car_reservation_email(
            str(job.id), "close_disputed", [world.dispatcher.email], "https://x.test"
        )

    [email] = sent_emails
    assert "เวลาปิดงาน" in email["subject"]
    assert "พขร. กดปิดงานช้า" in email["body"]
    assert "20:30" in email["body"]
    assert f"/car_reservation/requests/{job.id}" in email["body"]


def test_the_requester_can_answer_only_once(world):
    job = closed_trip(world)
    assert dispute(world, job).status_code == 302

    again = world.client_for(world.requester).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )

    assert again.status_code in (302, 403)
    job.reload()
    assert job.close_confirmation == "disputed"
    assert [log.action for log in job.audit_logs] == ["close_disputed"]
    assert 'value="correct"' not in confirmation_section(world, job)


def test_after_3_days_without_an_answer_the_close_is_auto_confirmed_and_closed_to_answers(
    world, mock_redis_queue
):
    job = closed_trip(world, closed_ago=datetime.timedelta(days=4))

    section = confirmation_section(world, job)
    response = dispute(world, job)

    assert 'data-status="auto_confirmed"' in section
    assert "ยืนยันอัตโนมัติ" in section
    assert 'value="correct"' not in section
    assert response.status_code in (302, 403)
    job.reload()
    assert job.close_confirmation is None
    assert email_jobs(mock_redis_queue, "close_disputed") == []


def test_a_trip_closed_less_than_3_days_ago_waits_for_the_requester(world):
    job = closed_trip(world, closed_ago=datetime.timedelta(days=2))

    assert 'data-status="pending"' in confirmation_section(world, job)


@pytest.mark.parametrize("who", ["stranger", "supervisor", "dispatcher", "driver"])
def test_only_the_creator_can_answer_the_close_confirmation(world, who):
    job = closed_trip(world)

    response = dispute(world, job, user=getattr(world, who))

    assert response.status_code in (302, 403)
    job.reload()
    assert job.close_confirmation is None
    assert 'value="correct"' not in confirmation_section(
        world, job, user=getattr(world, who)
    )


@pytest.mark.parametrize("status", ["active", "pending", "cancelled"])
def test_only_a_closed_trip_can_be_answered(world, status):
    job = closed_trip(world, status=status)

    response = world.client_for(world.requester).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )

    assert response.status_code in (302, 403)
    job.reload()
    assert job.close_confirmation is None


def test_when_the_creator_is_the_dispatcher_only_an_admin_can_answer(
    world, org_admin, create_user
):
    job = closed_trip(world, creator=world.dispatcher)

    refused = world.client_for(world.dispatcher).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )
    other = world.client_for(world.requester).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )
    assert refused.status_code in (302, 403)
    assert other.status_code in (302, 403)
    job.reload()
    assert job.close_confirmation is None

    answered = world.client_for(org_admin).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )

    assert answered.status_code == 302
    job.reload()
    assert job.close_confirmation == "confirmed"
    assert job.close_confirmed_by == org_admin


def test_a_system_admin_can_answer_for_a_trip_created_by_the_dispatcher(
    world, create_user
):
    system_admin = create_user("Root", "Admin", roles=["admin"])
    job = closed_trip(world, creator=world.dispatcher)

    answered = world.client_for(system_admin).post(
        confirmation_url(world, job), data={"decision": "correct"}
    )

    assert answered.status_code == 302
    job.reload()
    assert job.close_confirmation == "confirmed"


def inbox_rows(world, user):
    page = world.client_for(user).get(inbox_url(world))
    assert page.status_code == 200
    doc = lxml_html.fromstring(page.get_data(as_text=True))
    return doc.xpath("//table[contains(@class, 'table')]/tbody/tr")


def test_inbox_row_at_a_plain_step_offers_quick_approve_and_deny_that_return_to_the_inbox(
    world,
):
    car_application = world.submit_domestic_request()

    (row,) = inbox_rows(world, world.supervisor)

    approve_form = row.xpath(f".//form[@action='{approve_url(world, car_application)}']")
    deny_form = row.xpath(f".//form[@action='{deny_url(world, car_application)}']")
    assert len(approve_form) == 1 and len(deny_form) == 1
    for form in (approve_form[0], deny_form[0]):
        assert form.get("method") == "post"
        assert form.xpath(".//input[@name='next']/@value") == [inbox_url(world)]
    assert row.xpath(".//button[@data-role='quick-approve']")
    assert row.xpath(".//button[@data-role='quick-deny']")
    assert deny_form[0].xpath(".//textarea[@name='comment'][@required]")
    assert not row.xpath(".//*[@data-role='dispatch-link']")


def test_quick_decision_fields_are_wtforms_fields_with_unique_ids_and_matching_labels(
    world,
):
    world.submit_domestic_request()
    world.submit_domestic_request()
    page = world.client_for(world.supervisor).get(inbox_url(world))
    doc = lxml_html.fromstring(page.get_data(as_text=True))

    dialogs = doc.xpath("//dialog[starts-with(@id, 'quick-')]")
    # 2 คำขอ x (ตาราง + การ์ดมือถือ) x (อนุมัติ + ไม่อนุมัติ)
    assert len(dialogs) == 8
    textareas = doc.xpath("//dialog//textarea[@name='comment']")
    nexts = doc.xpath("//dialog//input[@name='next']")
    assert len(textareas) == len(nexts) == 8
    for field in textareas + nexts:
        assert field.get("id")
    ids = [field.get("id") for field in textareas + nexts]
    assert len(set(ids)) == len(ids)
    for textarea in textareas:
        assert textarea.xpath(f"ancestor::form//label[@for='{textarea.get('id')}']")
        assert textarea.get("maxlength") == "516"
    deny_boxes = doc.xpath("//dialog[starts-with(@id, 'quick-deny-')]//textarea")
    assert len(deny_boxes) == 4 and all(t.get("required") is not None for t in deny_boxes)
    approve_boxes = doc.xpath("//dialog[starts-with(@id, 'quick-approve-')]//textarea")
    assert len(approve_boxes) == 4 and all(t.get("required") is None for t in approve_boxes)


def test_inbox_row_at_the_dispatcher_step_links_to_the_detail_to_dispatch_instead_of_quick_approve(
    world,
):
    car_application = world.submit_domestic_request()
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )

    (row,) = inbox_rows(world, world.dispatcher)

    (link,) = row.xpath(".//a[@data-role='dispatch-link']")
    assert link.get("href") == detail_url(world, car_application)
    assert "จัดรถ" in link.text_content()
    assert not row.xpath(".//*[@data-role='quick-approve']")
    assert not row.xpath(".//form[contains(@action, '/approve')]")


def test_approve_with_next_set_to_the_inbox_returns_there_and_still_advances(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application),
        data={"comment": "", "next": inbox_url(world)},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == inbox_url(world)
    car_application.reload()
    assert car_application.current_step == 1


def test_deny_with_next_set_to_the_inbox_returns_there_and_denies(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        deny_url(world, car_application),
        data={"comment": "ไม่เหมาะสม", "next": inbox_url(world)},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == inbox_url(world)
    car_application.reload()
    assert car_application.status == "denied"


@pytest.mark.parametrize(
    "next_url",
    [
        "https://evil.example",
        "//evil.example/car_reservation/requests/inbox",
        "/car_reservation/requests/inbox?organization_id=000000000000000000000000",
    ],
)
@pytest.mark.parametrize("action", ["approve", "deny"])
def test_next_that_is_not_this_orgs_inbox_is_ignored_and_the_detail_is_shown(
    world, action, next_url
):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        f"{BASE}/{car_application.id}/{action}?organization_id={world.org.id}",
        data={"comment": "เหตุผล", "next": next_url},
    )

    assert response.status_code == 302
    assert response.headers["Location"] == detail_url(world, car_application)


def test_denying_with_next_but_without_a_reason_is_still_refused(world):
    car_application = world.submit_domestic_request()

    response = world.client_for(world.supervisor).post(
        deny_url(world, car_application),
        data={"comment": "", "next": inbox_url(world)},
    )

    assert response.status_code == 302
    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0
