"""ผลของการสร้าง/แก้ไข/ลบในระบบรถต้องแจ้งผู้ใช้ผ่าน flash เป็น toast แบบเดียวกับระบบจัดการองค์กร"""

import pytest

from kampan import models

from test_car_form_templates_views import valid_payload


@pytest.fixture
def setup(create_org, create_user, assign_user_to_org, create_car):
    org = create_org("Car Flash Org")
    admin = create_user("Admin", "Car")
    assign_user_to_org(admin, org, roles=["admin"])
    car = create_car(org, license_plate="ขข 2222")
    return {"org": org, "admin": admin, "car": car}


def _assert_toast(html, message, tone="alert-success"):
    toast = html[html.index('class="toast') :]
    assert message in toast
    assert "data-toast" in toast
    assert tone in toast


def test_delete_car_shows_toast(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["admin"])
        response = client.get(
            f"/vehicle_lending/cars/{setup['car'].id}/delete?organization_id={setup['org'].id}",
            follow_redirects=True,
        )

    assert response.status_code == 200
    _assert_toast(response.get_data(as_text=True), "ลบรถ ขข 2222 แล้ว")


def test_delete_feedback_template_shows_toast(app, login_as, setup, create_feedback_template):
    template = create_feedback_template(setup["org"], [setup["car"]], name="ประเมินรถตู้")
    with app.test_client() as client:
        login_as(client, setup["admin"])
        response = client.post(
            f"/vehicle_lending/car_feedback/{template.id}/delete?organization_id={setup['org'].id}",
            follow_redirects=True,
        )

    assert response.status_code == 200
    _assert_toast(response.get_data(as_text=True), "ลบแบบประเมิน ประเมินรถตู้ แล้ว")


def test_create_form_template_shows_toast(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["admin"])
        response = client.post(
            "/vehicle_lending/car_form_templates/create",
            data=valid_payload(setup["org"]),
            follow_redirects=True,
        )

    assert response.status_code == 200
    assert models.car_form_templates.CarFormTemplate.objects(organization=setup["org"]).count() == 1
    _assert_toast(response.get_data(as_text=True), "สร้างแบบฟอร์ม ใบขอใช้รถทั่วไป แล้ว")
