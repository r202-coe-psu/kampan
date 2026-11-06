"""คำขอใช้รถของ org แบบ snor: ผู้ขอยื่น -> ผู้อนุมัติแต่ละขั้นตามเส้นทางที่ตรึงไว้ตอนยื่น"""

import pytest

from kampan import models

BASE = "/vehicle_lending/snor_car_requests"


@pytest.fixture
def snor(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Snor Org")
    org.car_flow = "snor"
    org.enabled_modules = ["car"]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "One")
    s.supervisor = create_user("Supervisor", "Two")
    s.dispatcher = create_user("Dispatcher", "Three")
    s.stranger = create_user("Stranger", "Four")
    for user in (s.requester, s.supervisor, s.dispatcher, s.stranger):
        assign_user_to_org(user, org, roles=["staff"])
    models.CarFlowPosition(
        organization=org, position_key="dispatcher", user=s.dispatcher
    ).save()

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for

    def submit_domestic_request():
        response = client_for(s.requester).post(
            f"{BASE}/new?organization_id={org.id}&type=domestic",
            data={
                "requester_unit": "คณะวิศวกรรมศาสตร์",
                "phone": "081-234-5678",
                "supervisor": str(s.supervisor.id),
                "location": "กรุงเทพฯ",
                "request_reason": "ประชุมวิชาการ",
                "departure_date": "2099-01-05",
                "departure_time": "08:00",
                "return_date": "2099-01-06",
                "return_time": "17:00",
                "passenger_number": "3",
                "province_scope": "in_province",
            },
        )
        assert response.status_code == 302, response.get_data(as_text=True)
        return models.vehicle_applications.CarApplication.objects(creator=s.requester).first()

    s.submit_domestic_request = submit_domestic_request
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


def test_member_who_is_not_the_current_approver_cannot_approve(snor):
    car_application = snor.submit_domestic_request()

    response = snor.client_for(snor.stranger).post(
        approve_url(snor, car_application), data={"comment": ""}
    )
    assert response.status_code in (302, 403)

    page = snor.client_for(snor.requester).get(detail_url(snor, car_application))
    assert "รอผู้บังคับบัญชา" in page.get_data(as_text=True)


def test_diis_org_gets_404_on_snor_request_pages(
    app, create_org, create_user, assign_user_to_org, login_as
):
    org = create_org("Diis Org")
    user = create_user("Diis", "Member")
    assign_user_to_org(user, org, roles=["staff"])

    response = login_as(app.test_client(), user).get(
        f"{BASE}/new?organization_id={org.id}&type=domestic"
    )

    assert response.status_code == 404
