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


def _result_setup(org, user, car_application):
    user.email = "requester@example.test"
    user.save()
    car_application.creator = user
    car_application.status = "denied by header"
    car_application.denied_reason = "ไม่มีงบ"
    car_application.save()


def test_requester_email_skipped_without_template(app, create_org, create_user, create_car_application):
    with app.app_context():
        org = create_org()
        user = create_user()
        car_application = create_car_application(org, None)
        _result_setup(org, user, car_application)

        assert email_utils.send_email_car_application_to_requester(car_application, user, {}) is False


def test_requester_email_sent_to_creator_as_html(
    app, monkeypatch, create_org, create_user, create_car_application
):
    sent = []

    class FakeSMTP:
        def __init__(self, setting):
            pass

        def login(self):
            return True

        def quit(self):
            pass

        def send_email(self, receiver, subject, body, html=False):
            sent.append((receiver, subject, body, html))
            return True

    monkeypatch.setattr(email_utils, "PSUSMTP", FakeSMTP)
    with app.app_context():
        org = create_org()
        user = create_user()
        car_application = create_car_application(org, None)
        _result_setup(org, user, car_application)
        models.EmailTemplate(
            name="ผลการขอใช้รถ",
            subject="ผลการขอใช้รถ: {{ status_label }}",
            body="เหตุผล: {{ denied_reason }}\nLink: {{ application_url }}",
            type="car_application_result",
            organization=org,
            is_default=True,
        ).save()

        assert email_utils.send_email_car_application_to_requester(
            car_application, user, {"KAMPAN_HOST_URL": "https://staging.example.test"}
        )

    receiver, subject, body, html = sent[0]
    assert receiver == "requester@example.test"
    assert subject == "ผลการขอใช้รถ: ปฏิเสธ"
    assert "เหตุผล: ไม่มีงบ" in body
    assert f"https://staging.example.test/vehicle_lending/car_applications?organization_id={org.id}" in body
    assert html is True

