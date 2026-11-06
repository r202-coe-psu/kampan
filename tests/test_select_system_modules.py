"""หน้าเลือกระบบแสดงเฉพาะโมดูลที่องค์กรเปิดใช้ และข้ามไปเข้าโมดูลเลยถ้าเปิดอยู่โมดูลเดียว"""

import pytest
from flask import url_for

from kampan import models

EMPTY_MESSAGE = "หน่วยงานนี้ยังไม่ได้เปิดใช้ระบบใด กรุณาติดต่อผู้ดูแลระบบ"

MODULE_ENDPOINTS = {
    "procurement": "procurement.requisitions.renewal_requested",
    "inventory": "item_orders.index",
    "car": "vehicle_lending.car_applications.calendar",
    "car_reservation": "car_reservation.requests.index",
    "motorcycle": "vehicle_lending.motorcycle_applications.calendar",
}


def _module_url(app, module_key, org):
    with app.test_request_context():
        return url_for(MODULE_ENDPOINTS[module_key], organization_id=org.id)


@pytest.fixture
def open_select_system(app, create_org, create_user, assign_user_to_org, login_as):
    def _open(enabled_modules=None):
        org = create_org("Select Org")
        if enabled_modules is not None:
            org.enabled_modules = enabled_modules
            org.save()
        member = create_user("Member", "Select")
        role = assign_user_to_org(member, org, roles=["staff"])
        role.division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
        role.save()

        client = app.test_client()
        login_as(client, member)
        with app.test_request_context():
            url = url_for("site.select_system", organization_id=org.id)
        return org, client.get(url)

    return _open


def test_select_system_shows_cards_only_for_enabled_modules(app, open_select_system):
    org, response = open_select_system(enabled_modules=["car", "inventory"])
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'href="{_module_url(app, "car", org)}"' in html
    assert f'href="{_module_url(app, "inventory", org)}"' in html
    assert f'href="{_module_url(app, "procurement", org)}"' not in html
    assert f'href="{_module_url(app, "motorcycle", org)}"' not in html


def test_select_system_shows_the_car_reservation_card_when_the_module_is_enabled(
    app, open_select_system
):
    org, response = open_select_system(enabled_modules=["car_reservation", "inventory"])
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'href="{_module_url(app, "car_reservation", org)}"' in html
    assert f'href="{_module_url(app, "car", org)}"' not in html


def test_select_system_redirects_into_the_only_enabled_module(app, open_select_system):
    org, response = open_select_system(enabled_modules=["car"])

    assert response.status_code == 302
    assert response.headers["Location"].endswith(_module_url(app, "car", org))


def test_select_system_shows_all_modules_when_organization_never_set_modules(
    app, open_select_system
):
    org, response = open_select_system()
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for key in MODULE_ENDPOINTS:
        assert f'href="{_module_url(app, key, org)}"' in html
    assert EMPTY_MESSAGE not in html


def test_select_system_tells_member_when_no_module_is_enabled(app, open_select_system):
    org, response = open_select_system(enabled_modules=[])
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert EMPTY_MESSAGE in html
    for key in MODULE_ENDPOINTS:
        assert f'href="{_module_url(app, key, org)}"' not in html
