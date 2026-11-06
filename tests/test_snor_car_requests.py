"""คำขอใช้รถของ org แบบ snor: ผู้ขอยื่น -> ผู้อนุมัติแต่ละขั้นตามเส้นทางที่ตรึงไว้ตอนยื่น"""

import datetime

import pytest

from kampan import models

BASE = "/snor_car/requests"


@pytest.fixture
def snor(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Snor Org")
    org.enabled_modules = ["snor_car"]
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
    models.CarFlowPosition(
        organization=org, position_key="dispatcher", user=s.dispatcher
    ).save()

    # ผู้ดำรงตำแหน่งที่เหลือ (คนละคน) เพื่อเดินครบทุกเส้นทาง
    s.holders = {"supervisor": s.supervisor, "dispatcher": s.dispatcher}
    for key, _ in models.SNOR_POSITIONS:
        if key == "dispatcher":
            continue
        holder = create_user(f"Holder{key.title().replace('_', '')}", "Position")
        assign_user_to_org(holder, org, roles=["staff"])
        models.CarFlowPosition(organization=org, position_key=key, user=holder).save()
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
            models.SnorCarRequest.objects(creator=s.requester)
            .order_by("-id")
            .first()
        )

    s.submit_request = submit_request
    s.submit_domestic_request = submit_request
    return s


def detail_url(snor, car_application):
    return f"{BASE}/{car_application.id}?organization_id={snor.org.id}"


def approve_url(snor, car_application):
    return f"{BASE}/{car_application.id}/approve?organization_id={snor.org.id}"


def test_requester_submits_domestic_request_and_it_waits_for_supervisor(snor):
    car_application = snor.submit_domestic_request()

    assert car_application.status == "pending"
    assert car_application.route_snapshot == [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ]

    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert page.status_code == 200
    assert "รอผู้บังคับบัญชา" in page.get_data(as_text=True)


def test_submitting_stores_the_requesters_division_on_the_request(snor):
    car_application = snor.submit_domestic_request()

    assert car_application.division == snor.division


def test_supervisor_approval_moves_request_to_dispatcher(snor):
    car_application = snor.submit_domestic_request()

    response = snor.client_for(snor.supervisor).post(
        approve_url(snor, car_application), data={"comment": "เห็นชอบ"}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "pending"
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert "รอผู้จัดรถ" in page.get_data(as_text=True)


def test_only_a_head_of_the_requesters_division_approves_the_supervisor_step(
    snor, create_user
):
    colleague_head = create_user("ColleagueHead", "Six")
    snor.assign_in_division(colleague_head, ["head"], snor.division)
    colleague_staff = create_user("ColleagueStaff", "Seven")
    snor.assign_in_division(colleague_staff, ["staff"], snor.division)
    car_application = snor.submit_domestic_request()

    for outsider in (snor.other_head, colleague_staff):
        snor.client_for(outsider).post(
            approve_url(snor, car_application), data={"comment": ""}
        )
        car_application.reload()
        assert car_application.current_step == 0

    response = snor.client_for(colleague_head).post(
        approve_url(snor, car_application), data={"comment": "เห็นชอบ"}
    )
    assert response.status_code == 302
    car_application.reload()
    assert car_application.current_step == 1


def test_a_head_cannot_approve_their_own_request_but_another_head_can(
    snor, create_user
):
    colleague_head = create_user("ColleagueHead", "Six")
    snor.assign_in_division(colleague_head, ["head"], snor.division)

    response = snor.client_for(snor.supervisor).post(
        f"{BASE}/new?organization_id={snor.org.id}&type=domestic",
        data=snor.request_data(),
    )
    assert response.status_code == 302
    car_application = models.SnorCarRequest.objects(
        creator=snor.supervisor
    ).first()

    snor.client_for(snor.supervisor).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.current_step == 0

    snor.client_for(colleague_head).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.current_step == 1


def test_submission_is_refused_when_the_division_has_no_head(snor, create_user):
    headless = models.Division(name="ฝ่ายไม่มีหัวหน้า", organization=snor.org)
    headless.save()
    lonely = create_user("Lonely", "Eight")
    snor.assign_in_division(lonely, ["staff"], headless)

    response = snor.client_for(lonely).post(
        f"{BASE}/new?organization_id={snor.org.id}&type=domestic",
        data=snor.request_data(),
    )

    assert response.status_code == 200
    assert "ฝ่ายของคุณยังไม่มีหัวหน้าฝ่าย กรุณาติดต่อผู้ดูแลระบบ" in response.get_data(
        as_text=True
    )
    assert (
        models.SnorCarRequest.objects(creator=lonely).count() == 0
    )


def test_member_who_is_not_the_current_approver_cannot_approve(snor):
    car_application = snor.submit_domestic_request()

    response = snor.client_for(snor.stranger).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    assert response.status_code in (302, 403)

    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
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
    snor, request_type, province_scope, expected_route
):
    car_application = snor.submit_request(request_type, province_scope)

    for index, (key, label) in enumerate(expected_route):
        page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
        assert f"รอ{label}" in page.get_data(as_text=True)

        # มีแต่เจ้าของขั้นปัจจุบันที่อนุมัติได้ ขั้นถัดไปมาอนุมัติก่อนไม่ได้
        if index + 1 < len(expected_route):
            next_key, _ = expected_route[index + 1]
            early = snor.client_for(snor.holders[next_key]).post(
                approve_url(snor, car_application), data={"comment": ""}
            )
            # 403 ถูก acl แปลงเป็น redirect; สิ่งที่ยืนยันคือขั้นไม่ขยับ
            assert early.status_code in (302, 403)
            car_application.reload()
            assert car_application.current_step == index

        response = snor.client_for(snor.holders[key]).post(
            approve_url(snor, car_application), data={"comment": ""}
        )
        assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "active"
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert 'data-status="active"' in page.get_data(as_text=True)


def test_delegate_of_a_position_can_approve_for_it_and_audit_log_names_the_delegate(
    snor, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, snor.org, roles=["staff"])
    position = models.CarFlowPosition.objects(
        organization=snor.org, position_key="president"
    ).first()
    position.delegates = [secretary]
    position.save()

    car_application = snor.submit_request("abroad")
    for key in [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
        "vice_president_hatyai",
    ]:
        snor.client_for(snor.holders[key]).post(
            approve_url(snor, car_application), data={"comment": ""}
        )

    response = snor.client_for(secretary).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "active"
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert "Secretary Assistant" in page.get_data(as_text=True)


def test_global_admin_cannot_approve_a_step_they_do_not_hold(
    snor, create_user, assign_user_to_org
):
    admin = create_user("Admin", "Global", roles=["admin"])
    assign_user_to_org(admin, snor.org, roles=["admin"])
    car_application = snor.submit_request("domestic")

    snor.client_for(admin).post(
        approve_url(snor, car_application), data={"comment": ""}
    )

    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0
    assert len(car_application.step_approvals) == 0


def deny_url(snor, car_application):
    return f"{BASE}/{car_application.id}/deny?organization_id={snor.org.id}"


def test_current_approver_can_deny_with_a_reason_and_the_request_stops(snor):
    car_application = snor.submit_request("domestic")
    snor.client_for(snor.supervisor).post(
        approve_url(snor, car_application), data={"comment": ""}
    )

    response = snor.client_for(snor.dispatcher).post(
        deny_url(snor, car_application), data={"comment": "ไม่มีรถว่างในช่วงเวลานี้"}
    )
    assert response.status_code == 302

    car_application.reload()
    assert car_application.status == "denied"
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    html = page.get_data(as_text=True)
    assert 'data-status="denied"' in html
    assert "ไม่อนุมัติ" in html
    assert "ไม่มีรถว่างในช่วงเวลานี้" in html
    assert 'data-state="denied"' in html

    # ปฏิเสธแล้ว ไม่มีใครอนุมัติต่อได้
    snor.client_for(snor.holders["vehicle_unit_head"]).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    snor.client_for(snor.dispatcher).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    car_application.reload()
    assert car_application.status == "denied"
    assert len(car_application.step_approvals) == 2


def test_member_who_is_not_the_current_approver_cannot_deny(snor):
    car_application = snor.submit_request("domestic")

    snor.client_for(snor.stranger).post(
        deny_url(snor, car_application), data={"comment": "ขอปฏิเสธ"}
    )
    snor.client_for(snor.dispatcher).post(
        deny_url(snor, car_application), data={"comment": "ยังไม่ถึงคิว"}
    )

    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0


def test_denying_without_a_reason_is_refused(snor):
    car_application = snor.submit_request("domestic")

    response = snor.client_for(snor.supervisor).post(
        deny_url(snor, car_application),
        data={"comment": ""},
        follow_redirects=True,
    )

    assert "กรุณาระบุเหตุผลที่ไม่อนุมัติ" in response.get_data(as_text=True)
    car_application.reload()
    assert car_application.status == "pending"
    assert car_application.current_step == 0


def test_organization_without_the_snor_car_module_gets_404(
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


def test_requests_home_lists_only_the_requesters_own_requests(snor):
    other = snor.stranger
    snor.assign_in_division(other, ["staff"], snor.division)
    other_data = snor.request_data()
    other_data["request_reason"] = "งานของคนอื่น"
    snor.client_for(other).post(
        f"{BASE}/new?organization_id={snor.org.id}&type=domestic", data=other_data
    )
    snor.submit_domestic_request()

    page = snor.client_for(snor.requester).get(f"{BASE}/?organization_id={snor.org.id}")

    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "ประชุมวิชาการ" in html
    assert "รออนุมัติ" in html
    assert "งานของคนอื่น" not in html



def post_new(snor, data, request_type="domestic", user=None):
    return snor.client_for(user or snor.requester).post(
        f"{BASE}/new?organization_id={snor.org.id}&type={request_type}", data=data
    )


def test_request_departing_more_than_30_days_ahead_is_refused(snor):
    response = post_new(snor, snor.request_data(days_ahead=40))

    assert response.status_code == 200
    assert "ขอใช้รถล่วงหน้าได้ไม่เกิน 30 วัน" in response.get_data(as_text=True)
    assert models.SnorCarRequest.objects(creator=snor.requester).count() == 0


def test_request_departing_in_under_3_business_days_asks_for_urgent_confirmation(
    snor,
):
    response = post_new(snor, snor.request_data(days_ahead=1))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ขอรถล่วงหน้าน้อยกว่า 3 วันทำการ" in html
    assert 'name="confirm_urgent"' in html
    assert models.SnorCarRequest.objects(creator=snor.requester).count() == 0


def test_confirmed_short_notice_request_is_saved_as_urgent_and_shows_badge(snor):
    data = snor.request_data(days_ahead=1)
    data["confirm_urgent"] = "y"

    response = post_new(snor, data)

    assert response.status_code == 302
    car_application = models.SnorCarRequest.objects(creator=snor.requester).first()
    assert car_application.is_urgent is True
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert "เร่งด่วน" in page.get_data(as_text=True)


def test_request_with_enough_lead_time_is_saved_without_urgent_flag_or_warning(snor):
    response = post_new(snor, snor.request_data(days_ahead=20))

    assert response.status_code == 302
    car_application = models.SnorCarRequest.objects(creator=snor.requester).first()
    assert car_application.is_urgent is False
    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert "เร่งด่วน" not in page.get_data(as_text=True)


def test_abroad_request_needs_10_business_days_while_domestic_needs_3(snor):
    data = snor.request_data("abroad", days_ahead=5)

    response = post_new(snor, data, request_type="abroad")

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ขอรถล่วงหน้าน้อยกว่า 10 วันทำการ" in html
    assert models.SnorCarRequest.objects(creator=snor.requester).count() == 0

    enough = snor.request_data("abroad", days_ahead=20)
    assert post_new(snor, enough, request_type="abroad").status_code == 302


def test_request_returning_before_departure_is_refused(snor):
    data = snor.request_data()
    data["return_date"] = (
        datetime.date.today() + datetime.timedelta(days=19)
    ).isoformat()

    response = post_new(snor, data)

    assert response.status_code == 200
    assert "วันกลับต้องไม่ก่อนวันออกเดินทาง" in response.get_data(as_text=True)
    assert models.SnorCarRequest.objects(creator=snor.requester).count() == 0


def inbox_url(snor):
    return f"{BASE}/inbox?organization_id={snor.org.id}"


def inbox_shows(snor, user, car_application):
    page = snor.client_for(user).get(inbox_url(snor))
    assert page.status_code == 200
    return f"{BASE}/{car_application.id}?" in page.get_data(as_text=True)


def test_inbox_shows_request_at_supervisor_step_only_to_the_requesters_division_head(
    snor,
):
    car_application = snor.submit_domestic_request()

    assert inbox_shows(snor, snor.supervisor, car_application)
    assert not inbox_shows(snor, snor.other_head, car_application)
    assert not inbox_shows(snor, snor.dispatcher, car_application)


def test_after_supervisor_approves_inbox_moves_to_dispatcher_and_their_delegate(
    snor, create_user, assign_user_to_org
):
    secretary = create_user("Secretary", "Assistant")
    assign_user_to_org(secretary, snor.org, roles=["staff"])
    position = models.CarFlowPosition.objects(
        organization=snor.org, position_key="dispatcher"
    ).first()
    position.delegates = [secretary]
    position.save()
    car_application = snor.submit_domestic_request()
    snor.client_for(snor.supervisor).post(
        approve_url(snor, car_application), data={"comment": ""}
    )

    assert inbox_shows(snor, snor.dispatcher, car_application)
    assert inbox_shows(snor, secretary, car_application)
    assert not inbox_shows(snor, snor.supervisor, car_application)


def test_denied_and_active_requests_appear_in_nobodys_inbox(snor):
    denied = snor.submit_domestic_request()
    snor.client_for(snor.supervisor).post(
        f"{BASE}/{denied.id}/deny?organization_id={snor.org.id}",
        data={"comment": "ไม่เหมาะสม"},
    )
    active = snor.submit_domestic_request()
    for key in ["supervisor", "dispatcher", "vehicle_unit_head", "strategy_head"]:
        snor.client_for(snor.holders[key]).post(
            approve_url(snor, active), data={"comment": ""}
        )
    active.reload()
    assert active.status == "active"

    everyone = [snor.requester, snor.stranger, *snor.holders.values()]
    for user in everyone:
        assert not inbox_shows(snor, user, denied)
        assert not inbox_shows(snor, user, active)
