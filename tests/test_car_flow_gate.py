"""ภายในโมดูลรถยนต์ องค์กรที่ใช้ flow "snor" เปิดหน้าของ flow DIIS ไม่ได้ (404)
ส่วนหน้าที่ใช้ร่วมกันสองแบบต้องเปิดได้ และองค์กร flow "diis" ต้องไม่เปลี่ยนไป"""

import pytest

from kampan import models

CAR_APPLICATIONS = "/vehicle_lending/car_applications"
CALENDAR = f"{CAR_APPLICATIONS}/calendar"
CREATE = f"{CAR_APPLICATIONS}/create"
HEADER_PAGE = "/vehicle_lending/car_permissions/header_page"

DIIS_ONLY_PAGES = [
    CAR_APPLICATIONS,
    CREATE,
    HEADER_PAGE,
    "/vehicle_lending/car_permissions/admin_page",
    "/vehicle_lending/car_permissions/director_page",
]

SHARED_PAGES = [
    CALENDAR,
    "/vehicle_lending/cars",
    "/vehicle_lending/car_tasks",
    "/vehicle_lending/car_feedback",
    "/vehicle_lending/car_manuals",
    "/vehicle_lending/history_car_lending",
]


@pytest.fixture
def open_page(app, create_org, create_user, assign_user_to_org, login_as):
    def _open(path, car_flow):
        org = create_org("Flow Org")
        org.car_flow = car_flow
        org.save()
        member = create_user("Member", "Flow")
        role = assign_user_to_org(member, org, roles=["admin"])
        role.division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
        role.save()

        client = app.test_client()
        login_as(client, member)
        separator = "&" if "?" in path else "?"
        return client.get(f"{path}{separator}organization_id={org.id}")

    return _open


@pytest.mark.parametrize("path", DIIS_ONLY_PAGES)
def test_snor_organization_gets_404_on_diis_only_car_pages(open_page, path):
    response = open_page(path, car_flow="snor")

    assert response.status_code == 404


@pytest.mark.parametrize("path", SHARED_PAGES)
def test_snor_organization_still_opens_pages_shared_by_both_flows(open_page, path):
    response = open_page(path, car_flow="snor")

    assert response.status_code != 404


@pytest.mark.parametrize("path", DIIS_ONLY_PAGES)
def test_diis_organization_still_opens_diis_car_pages(open_page, path):
    response = open_page(path, car_flow="diis")

    assert response.status_code != 404


def test_snor_calendar_hides_diis_menu_items_and_new_request_link(open_page):
    html = open_page(CALENDAR, car_flow="snor").get_data(as_text=True)

    assert f'href="{HEADER_PAGE}' not in html
    assert f'href="{CAR_APPLICATIONS}?' not in html
    assert f'href="{CREATE}' not in html


def test_diis_calendar_shows_diis_menu_items_and_new_request_link(open_page):
    html = open_page(CALENDAR, car_flow="diis").get_data(as_text=True)

    assert f'href="{HEADER_PAGE}' in html
    assert f'href="{CAR_APPLICATIONS}?' in html
    assert f'href="{CREATE}' in html
