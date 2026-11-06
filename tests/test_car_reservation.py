"""คำขอใช้รถของระบบจองรถ: ผู้ขอยื่น -> ผู้อนุมัติแต่ละขั้นตามเส้นทางที่ตรึงไว้ตอนยื่น"""

import datetime
from unittest.mock import MagicMock, patch

import pytest

from kampan import models, utils
from kampan.web import redis_rq

BASE = "/car_reservation/requests"


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


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Reservation Org")
    org.enabled_modules = ["car_reservation"]
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
    for user in (s.dispatcher, s.stranger):
        assign_user_to_org(user, org, roles=["staff"])
    models.CarReservationPosition(
        organization=org, position_key="dispatcher", user=s.dispatcher
    ).save()

    # ผู้ดำรงตำแหน่งที่เหลือ (คนละคน) เพื่อเดินครบทุกเส้นทาง
    s.holders = {"supervisor": s.supervisor, "dispatcher": s.dispatcher}
    for key, _ in models.RESERVATION_POSITIONS:
        if key == "dispatcher":
            continue
        holder = create_user(f"Holder{key.title().replace('_', '')}", "Position")
        assign_user_to_org(holder, org, roles=["staff"])
        models.CarReservationPosition(organization=org, position_key=key, user=holder).save()
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
            "location": "กรุงเทพฯ",
            "request_reason": "ประชุมวิชาการ",
            "departure_date": departure.isoformat(),
            "departure_time": "08:00",
            "return_date": (departure + datetime.timedelta(days=1)).isoformat(),
            "return_time": "17:00",
            "passenger_number": "3",
        }
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


def test_a_head_cannot_approve_their_own_request_but_another_head_can(
    world, create_user
):
    colleague_head = create_user("ColleagueHead", "Six")
    world.assign_in_division(colleague_head, ["head"], world.division)

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
    assert car_application.current_step == 0

    world.client_for(colleague_head).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.current_step == 1


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


def test_delegate_of_a_position_can_approve_for_it_and_audit_log_names_the_delegate(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["staff"])
    position = models.CarReservationPosition.objects(
        organization=world.org, position_key="president"
    ).first()
    position.delegates = [secretary]
    position.save()

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
    assert 'name="confirm_urgent"' in html
    assert models.CarReservation.objects(creator=world.requester).count() == 0


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


def test_after_supervisor_approves_inbox_moves_to_dispatcher_and_their_delegate(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["staff"])
    position = models.CarReservationPosition.objects(
        organization=world.org, position_key="dispatcher"
    ).first()
    position.delegates = [secretary]
    position.save()
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


def test_sidebar_shows_inbox_link_with_count_only_when_something_is_waiting(world):
    index_url = f"{BASE}/?organization_id={world.org.id}"

    quiet = world.client_for(world.supervisor).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" not in quiet

    world.submit_domestic_request()
    world.submit_domestic_request()

    busy = world.client_for(world.supervisor).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" in busy
    assert 'data-testid="inbox-count">2<' in busy
    assert f"{BASE}/inbox?organization_id={world.org.id}" in busy
    stranger = world.client_for(world.stranger).get(index_url).get_data(as_text=True)
    assert "รายการรออนุมัติ" not in stranger


def test_inbox_never_lists_requests_of_another_organization(
    world, create_org, assign_user_to_org
):
    other_org = create_org("Other Reservation Org")
    other_org.enabled_modules = ["car_reservation"]
    other_org.save()
    assign_user_to_org(world.dispatcher, other_org, roles=["staff"])
    models.CarReservationPosition(
        organization=other_org, position_key="dispatcher", user=world.dispatcher
    ).save()
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


def request_at_dispatcher(world):
    car_application = world.submit_domestic_request()
    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application), data={"comment": ""}
    )
    assert response.status_code == 302
    return car_application


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
@pytest.mark.parametrize("clash", ["car", "driver"])
def test_car_or_driver_already_booked_in_an_overlapping_time_is_refused(
    world, clash, blocking_status
):
    other_car = models.vehicles.Car(
        organization=world.org, license_plate="งง 2222", status="active"
    ).save()
    other_driver = world.add_driver("Other", "Driver")
    assigned_request(
        world,
        DAY + datetime.timedelta(hours=2),
        DAY + datetime.timedelta(hours=6),
        status=blocking_status,
        car=world.car if clash == "car" else other_car,
        driver=world.driver if clash == "driver" else other_driver,
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
    if clash == "car":
        assert "รถ กก 1234 มีงานช่วงเวลานี้แล้ว" in html
    else:
        assert "พนักงานขับรถ Driver One มีงานช่วงเวลานี้แล้ว" in html


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


def test_cancel_request_appears_in_the_inbox_of_the_dispatcher_and_delegate_only(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["staff"])
    position = models.CarReservationPosition.objects(
        organization=world.org, position_key="dispatcher"
    ).first()
    position.delegates = [secretary]
    position.save()
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


def test_delegate_dispatcher_confirms_cancel_and_audit_log_names_them(
    world, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, world.org, roles=["staff"])
    position = models.CarReservationPosition.objects(
        organization=world.org, position_key="dispatcher"
    ).first()
    position.delegates = [secretary]
    position.save()
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


def test_only_a_dispatcher_holder_or_delegate_can_confirm_a_cancel(world):
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


def test_a_submitted_request_has_no_edit_route(world):
    car_application = world.submit_domestic_request()

    for user in (world.requester, world.supervisor):
        for method in ("get", "post"):
            response = getattr(world.client_for(user), method)(
                f"{BASE}/{car_application.id}/edit?organization_id={world.org.id}"
            )
            assert response.status_code == 404


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


def test_supervisor_approval_notifies_the_dispatcher_holder_and_delegate(
    world, create_user, assign_user_to_org, mock_redis_queue
):
    delegate = create_user("Delegate", "Dispatcher")
    assign_user_to_org(delegate, world.org, roles=["staff"])
    position = models.CarReservationPosition.objects(
        organization=world.org, position_key="dispatcher"
    ).first()
    position.delegates = [delegate]
    position.save()
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

        def send_email(self, receiver, subject, body, html=False, steps=None):
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
