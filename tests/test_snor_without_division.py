"""สมาชิกขององค์กรแบบ snor ไม่ต้องมีฝ่ายก็เข้าหน้าเลือกระบบและปฏิทินรถได้ ส่วนองค์กร DIIS ยังต้องมีฝ่ายเหมือนเดิม"""

import pytest
from flask import url_for

# หัวข้อหน้าก็ใช้ข้อความนี้ จึงจับคู่กับไอคอนของรายการเมนูใน sidebar เพื่อให้ตรวจเฉพาะเมนู
CALENDAR_MENU_ITEM = '<i class="ph ph-calendar-blank"></i> ปฏิทินการขอใช้รถยนต์'


@pytest.fixture
def open_as_member_without_division(
    app, create_org, create_user, assign_user_to_org, login_as
):
    def _open(car_flow, enabled_modules=None):
        org = create_org("Snor Org")
        org.car_flow = car_flow
        if enabled_modules is not None:
            org.enabled_modules = enabled_modules
        org.save()
        requester = create_user("Requester", "Outsider")
        assign_user_to_org(requester, org, roles=["staff"])

        client = app.test_client()
        login_as(client, requester)

        def get(endpoint, **kwargs):
            with app.test_request_context():
                url = url_for(endpoint, organization_id=org.id, **kwargs)
            return client.get(url)

        return org, get

    return _open


def _calendar_url(app, org):
    with app.test_request_context():
        return url_for("vehicle_lending.car_applications.calendar", organization_id=org.id)


def test_snor_member_without_division_sees_car_card_on_system_selection(
    app, open_as_member_without_division
):
    org, get = open_as_member_without_division(
        "snor", enabled_modules=["car", "inventory"]
    )

    response = get("site.select_system")

    assert response.status_code == 200
    assert f'href="{_calendar_url(app, org)}"' in response.get_data(as_text=True)


def test_snor_member_without_division_enters_car_calendar_with_its_menu(
    app, open_as_member_without_division
):
    org, get = open_as_member_without_division("snor", enabled_modules=["car"])

    selection = get("site.select_system")
    assert selection.status_code == 302
    assert selection.headers["Location"].endswith(_calendar_url(app, org))

    calendar = get("vehicle_lending.car_applications.calendar")
    assert calendar.status_code == 200
    assert CALENDAR_MENU_ITEM in calendar.get_data(as_text=True)


def test_diis_member_without_division_is_still_sent_to_account_page(
    app, open_as_member_without_division
):
    org, get = open_as_member_without_division("diis")

    response = get("site.select_system")

    assert response.status_code == 302
    assert "/accounts" in response.headers["Location"]
    assert "select_system" not in response.headers["Location"]
