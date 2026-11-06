"""องค์กรเปิด/ปิดโมดูลของตัวเองได้ (enabled_modules) หน้าของโมดูลที่ปิดต้องเข้าไม่ได้"""

import pytest

from kampan import models

CAR_CALENDAR = "/vehicle_lending/car_applications/calendar"
SNOR_CAR_HOME = "/snor_car/requests/"

# หน้าตัวแทนหนึ่งหน้าต่อ blueprint ของแต่ละโมดูล (GET ธรรมดา ส่ง organization_id ทาง query)
MODULE_PAGES = {
    "car": [
        CAR_CALENDAR,
        "/vehicle_lending/car_permissions/admin_page",
        "/vehicle_lending/cars",
        "/vehicle_lending/car_tasks",
        "/vehicle_lending/car_feedback",
        "/vehicle_lending/car_manuals",
        "/vehicle_lending/history_car_lending",
    ],
    "snor_car": [
        "/snor_car/requests/",
    ],
    "motorcycle": [
        "/vehicle_lending/motorcycle_applications/calendar",
        "/vehicle_lending/motorcycle_permissions/admin_page",
        "/vehicle_lending/motorcycles",
        "/vehicle_lending/motorcycle_manuals",
    ],
    "procurement": [
        "/procurement/requisitions",
        "/procurement/products",
        "/procurement/manuals",
        "/procurement/requisition_timeline",
        "/procurement/requisition_timeline_items/",
    ],
    "inventory": [
        "/items/",
        "/item_orders/",
        "/item_checkouts/",
        "/item-positions/",
        "/item_registers/",
        "/inventories/",
        "/warehouses/",
        "/categories/",
        "/suppliers/",
        "/lost_breaks/",
        "/approve_orders/admin",
        "/dashboard/summary",
        "/notifications/",
    ],
}
GATED_PAGES = [path for pages in MODULE_PAGES.values() for path in pages]

# หน้าที่ใช้ร่วมกันทุกโมดูล ต้องเปิดได้แม้องค์กรปิดโมดูลทั้งหมด
SHARED_PAGES = [
    "/select_system",
    "/accounts",
    "/organizations/{organization_id}/",
]


@pytest.fixture
def open_page(app, create_org, create_user, assign_user_to_org, login_as):
    def _open(path, enabled_modules=None):
        org = create_org("Module Org")
        if enabled_modules is not None:
            org.enabled_modules = enabled_modules
            org.save()
        member = create_user("Member", "Module")
        role = assign_user_to_org(member, org, roles=["admin"])
        role.division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
        role.save()

        client = app.test_client()
        login_as(client, member)
        url = path.format(organization_id=org.id)
        separator = "&" if "?" in url else "?"
        return client.get(f"{url}{separator}organization_id={org.id}")

    return _open


def test_organization_without_car_module_gets_404_on_car_pages(open_page):
    response = open_page(CAR_CALENDAR, enabled_modules=["inventory"])

    assert response.status_code == 404


def test_snor_car_pages_need_the_snor_car_module_not_the_car_module(open_page):
    without = open_page(SNOR_CAR_HOME, enabled_modules=["car"])
    with_module = open_page(SNOR_CAR_HOME, enabled_modules=["snor_car"])

    assert without.status_code == 404
    assert with_module.status_code != 404


def test_organization_that_never_set_modules_still_opens_car_pages(open_page):
    response = open_page(CAR_CALENDAR)

    assert response.status_code == 200


@pytest.mark.parametrize("path", GATED_PAGES)
def test_organization_with_all_modules_disabled_gets_404_on_module_pages(
    open_page, path
):
    response = open_page(path, enabled_modules=[])

    assert response.status_code == 404


@pytest.mark.parametrize("path", GATED_PAGES)
def test_organization_that_never_set_modules_does_not_get_404_on_module_pages(
    open_page, path
):
    response = open_page(path)

    assert response.status_code != 404


@pytest.mark.parametrize("path", SHARED_PAGES)
def test_shared_pages_stay_open_when_all_modules_are_disabled(open_page, path):
    response = open_page(path, enabled_modules=[])

    assert response.status_code != 404
