"""แบบประเมินความพึงพอใจของระบบจองรถ: ผู้ขอประเมินหลังปิดงาน และผู้ดูแลองค์กรดูผลสรุป"""

import datetime

import pytest

from kampan import models

BASE = "/car_reservation/feedback"

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
