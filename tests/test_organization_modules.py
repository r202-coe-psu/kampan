"""องค์กรเปิด/ปิดโมดูลของตัวเองได้ (enabled_modules) หน้าของโมดูลที่ปิดต้องเข้าไม่ได้"""

import pytest

from kampan import models

CAR_CALENDAR = "/vehicle_lending/car_applications/calendar?organization_id={}"


@pytest.fixture
def open_car_calendar(app, create_org, create_user, assign_user_to_org, login_as):
    def _open(enabled_modules=None):
        org = create_org("Module Org")
        if enabled_modules is not None:
            org.enabled_modules = enabled_modules
            org.save()
        staff = create_user("Staffer", "Module")
        role = assign_user_to_org(staff, org, roles=["staff"])
        role.division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
        role.save()

        client = app.test_client()
        login_as(client, staff)
        return client.get(CAR_CALENDAR.format(org.id))

    return _open


def test_organization_without_car_module_gets_404_on_car_pages(open_car_calendar):
    response = open_car_calendar(enabled_modules=["inventory"])

    assert response.status_code == 404


def test_organization_that_never_set_modules_still_opens_car_pages(open_car_calendar):
    response = open_car_calendar()

    assert response.status_code == 200
