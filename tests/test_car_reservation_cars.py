"""ผู้ดูแลองค์กรจัดการรถของระบบจองรถ (เพิ่ม/แก้ไข/ปิดใช้งาน) และสมาชิกทุกคนดูข้อมูลรถ
และพนักงานขับรถได้ รถเป็นของ org ใครของมัน"""

import io

import pytest
from PIL import Image

from kampan import models

CARS_PATH = "/car_reservation/cars"


def png_bytes(size=(40, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, (20, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Cars Org")
    org.enabled_modules = ["car_reservation"]
    org.save()
    admin = create_user("Admin", "Cars")
    assign_user_to_org(admin, org, roles=["admin"])
    staff = create_user("Plain", "Staff")
    assign_user_to_org(staff, org, roles=["staff"])

    class Setup:
        pass

    s = Setup()
    s.org, s.admin, s.staff = org, admin, staff
    s.admin_client = login_as(app.test_client(), admin)
    s.staff_client = login_as(app.test_client(), staff)
    s.list_url = f"{CARS_PATH}/?organization_id={org.id}"
    s.create_url = f"{CARS_PATH}/create?organization_id={org.id}"
    s.edit_url = lambda car: f"{CARS_PATH}/{car.id}/edit?organization_id={org.id}"
    s.deactivate_url = (
        lambda car: f"{CARS_PATH}/{car.id}/deactivate?organization_id={org.id}"
    )
    s.directory_url = f"{CARS_PATH}/directory?organization_id={org.id}"
    s.image_url = lambda car: f"{CARS_PATH}/{car.id}/image?organization_id={org.id}"
    return s


def car_data(**overrides):
    data = {
        "license_plate": "กข 1234",
        "vehicle_type": "ตู้",
        "seat_count": "12",
        "description": "รถตู้ประจำคณะ",
        "status": "active",
    }
    data.update(overrides)
    return data


def test_org_admin_adds_a_car_and_it_appears_in_the_list(world):
    response = world.admin_client.post(world.create_url, data=car_data())

    listing = world.admin_client.get(world.list_url)

    html = listing.get_data(as_text=True)
    assert response.status_code == 302
    assert listing.status_code == 200
    assert "กข 1234" in html
    assert "รถตู้" in html
    assert "12 ที่นั่ง" in html


@pytest.mark.parametrize(
    "missing", [{"license_plate": ""}, {"seat_count": ""}, {"seat_count": "0"}]
)
def test_car_without_plate_or_with_missing_seat_count_is_refused(world, missing):
    response = world.admin_client.post(world.create_url, data=car_data(**missing))

    assert response.status_code == 200
    assert models.vehicles.Car.objects(organization=world.org).count() == 0
