"""คำขอใช้รถของ org แบบ snor: ผู้ขอยื่น -> ผู้อนุมัติแต่ละขั้นตามเส้นทางที่ตรึงไว้ตอนยื่น"""

import pytest

from kampan import models

BASE = "/vehicle_lending/snor_car_requests"


@pytest.fixture
def snor(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Snor Org")
    org.enabled_modules = ["car"]
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

    def request_data(request_type="domestic", province_scope="in_province"):
        data = {
            "requester_unit": "คณะวิศวกรรมศาสตร์",
            "phone": "081-234-5678",
            "location": "กรุงเทพฯ",
            "request_reason": "ประชุมวิชาการ",
            "departure_date": "2099-01-05",
            "departure_time": "08:00",
            "return_date": "2099-01-06",
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
