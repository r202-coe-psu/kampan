"""Unit tests ของการสร้างข้อความอีเมลแจ้งผู้อนุมัติใบขอใช้รถ"""

from kampan import models
from kampan.utils import email_utils


def build_text_format(org, user, car_application):
    division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
    car_application.creator = user
    return email_utils.get_car_application_text_format(
        division, user, user, car_application, "https://example.test/approve"
    )


def test_text_format_without_assigned_car(app, create_org, create_user, create_car_application):
    """ก่อน admin จัดรถ ใบขอใช้รถยังไม่มี car แต่ต้องสร้างข้อความอีเมลได้"""
    with app.app_context():
        org = create_org()
        user = create_user()
        car_application = create_car_application(org, None, status="pending on admin")

        text_format = build_text_format(org, user, car_application)

        assert text_format["car"] == "รอเจ้าหน้าที่จัดรถ"


def test_text_format_with_assigned_car(app, create_org, create_user, create_car, create_car_application):
    with app.app_context():
        org = create_org()
        user = create_user()
        car_application = create_car_application(org, create_car(org, license_plate="กข 1234"))

        text_format = build_text_format(org, user, car_application)

        assert text_format["car"] == "กข 1234"
