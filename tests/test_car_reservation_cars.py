"""ผู้ดูแลองค์กรจัดการรถของระบบจองรถ (เพิ่ม/แก้ไข/ปิดใช้งาน) และสมาชิกทุกคนดูข้อมูลรถ
และพนักงานขับรถได้ รถเป็นของ org ใครของมัน"""

import io
import re

import pytest
from PIL import Image

from kampan import models, utils

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


def test_brand_and_model_are_optional_saved_and_shown_in_the_list_and_directory(world):
    world.admin_client.post(world.create_url, data=car_data(brand=" Toyota ", car_model="Commuter"))
    world.admin_client.post(world.create_url, data=car_data(license_plate="ขค 5678"))

    car = models.vehicles.Car.objects(license_plate="กข 1234").first()
    plain = models.vehicles.Car.objects(license_plate="ขค 5678").first()
    assert (car.brand, car.car_model) == ("Toyota", "Commuter")
    assert (plain.brand, plain.car_model) == ("", "")
    for url in (world.list_url, world.directory_url):
        html = world.admin_client.get(url).get_data(as_text=True)
        assert html.count('data-role="car-brand-model"') == 1
        assert "Toyota Commuter" in html
    form = world.admin_client.get(world.edit_url(car)).get_data(as_text=True)
    assert 'value="Toyota"' in form and 'value="Commuter"' in form


@pytest.mark.parametrize(
    "missing", [{"license_plate": ""}, {"seat_count": ""}, {"seat_count": "0"}]
)
def test_car_without_plate_or_with_missing_seat_count_is_refused(world, missing):
    response = world.admin_client.post(world.create_url, data=car_data(**missing))

    assert response.status_code == 200
    assert models.vehicles.Car.objects(organization=world.org).count() == 0


def upload_car(world, photo, filename="car.png", content_type="image/png", url=None):
    data = car_data()
    data["upload_image"] = (io.BytesIO(photo), filename, content_type)
    return world.admin_client.post(
        url or world.create_url, data=data, content_type="multipart/form-data"
    )


def test_car_photo_is_served_to_any_org_member_as_an_image(world):
    upload_car(world, png_bytes())
    car = models.vehicles.Car.objects(organization=world.org).first()

    served = world.staff_client.get(world.image_url(car))

    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_non_image_or_oversized_car_photo_is_refused_with_thai_error(world):
    fake = upload_car(world, b"not an image at all")
    big = upload_car(world, png_bytes() + b"\0" * (2 * 1024 * 1024 + 1))

    assert fake.status_code == 200
    assert "ไฟล์ที่เลือกไม่ใช่รูปภาพ" in fake.get_data(as_text=True)
    assert big.status_code == 200
    assert "ไม่เกิน 2 MB" in big.get_data(as_text=True)
    assert models.vehicles.Car.objects(organization=world.org).count() == 0


def test_list_shows_the_photo_thumbnail_only_for_cars_that_have_one(world):
    upload_car(world, png_bytes())
    world.admin_client.post(world.create_url, data=car_data(license_plate="ขค 5678"))
    with_photo = models.vehicles.Car.objects(license_plate="กข 1234").first()
    without = models.vehicles.Car.objects(license_plate="ขค 5678").first()

    html = world.admin_client.get(world.list_url).get_data(as_text=True)

    assert f"/car_reservation/cars/{with_photo.id}/image" in html
    assert f"/car_reservation/cars/{without.id}/image" not in html


def test_org_admin_edits_a_car_and_a_success_toast_confirms_it(world, create_car):
    car = create_car(world.org, "กก 1111", vehicle_type="เก๋ง")
    car.seat_count = 4
    car.save()

    response = world.admin_client.post(
        world.edit_url(car),
        data=car_data(
            license_plate="กก 9999", vehicle_type="มินิบัส", seat_count="20", status="disactive"
        ),
    )
    listing = world.admin_client.get(response.headers["Location"])

    html = listing.get_data(as_text=True)
    car.reload()
    assert response.status_code == 302
    assert (car.license_plate, car.vehicle_type, car.seat_count, car.status) == (
        "กก 9999",
        "มินิบัส",
        20,
        "disactive",
    )
    assert "data-toast" in html
    assert "บันทึกรถ กก 9999 แล้ว" in html


def test_deactivating_a_car_removes_it_from_the_dispatchers_assignable_cars(
    world, create_car
):
    keep = create_car(world.org, "กก 1111")
    drop = create_car(world.org, "กก 2222")

    response = world.admin_client.post(world.deactivate_url(drop))
    listing = world.admin_client.get(response.headers["Location"])

    drop.reload()
    assert response.status_code == 302
    assert drop.status == "disactive"
    assert list(utils.car_reservation_flow.assignable_cars(world.org)) == [keep]
    assert "ปิดใช้งานรถ กก 2222 แล้ว" in listing.get_data(as_text=True)


def test_deactivate_only_accepts_post(world, create_car):
    car = create_car(world.org)

    assert world.admin_client.get(world.deactivate_url(car)).status_code == 405
    car.reload()
    assert car.status == "active"


def test_the_license_plate_never_lands_inside_the_deactivate_confirm_script(world, create_car):
    create_car(world.org, "x');alert(1);//")

    html = world.admin_client.get(world.list_url).get_data(as_text=True)

    (onsubmit,) = re.findall(r'onsubmit="([^"]*)"', html)
    assert "alert" not in onsubmit
    assert "this.dataset.plate" in onsubmit


def test_staff_cannot_open_list_create_edit_or_deactivate(world, create_car):
    car = create_car(world.org)
    client = world.staff_client

    responses = [
        client.get(world.list_url),
        client.get(world.create_url),
        client.post(world.create_url, data=car_data()),
        client.get(world.edit_url(car)),
        client.post(world.edit_url(car), data=car_data(license_plate="แก้ไข")),
        client.post(world.deactivate_url(car)),
    ]

    assert all(response.status_code in (302, 403) for response in responses)
    car.reload()
    assert (car.license_plate, car.status) == ("กก 1111", "active")
    assert models.vehicles.Car.objects(organization=world.org).count() == 1


def test_cars_of_another_org_cannot_be_edited_deactivated_or_viewed(
    world, create_org, create_car
):
    other_car = create_car(create_org("Other Org"), "ขข 7777")

    responses = [
        world.admin_client.get(world.edit_url(other_car)),
        world.admin_client.post(world.edit_url(other_car), data=car_data()),
        world.admin_client.post(world.deactivate_url(other_car)),
        world.staff_client.get(world.image_url(other_car)),
    ]
    listing = world.admin_client.get(world.list_url).get_data(as_text=True)

    assert [response.status_code for response in responses] == [404] * 4
    other_car.reload()
    assert other_car.status == "active"
    assert "ขข 7777" not in listing


def test_empty_list_shows_an_empty_state_with_an_add_link(world):
    html = world.admin_client.get(world.list_url).get_data(as_text=True)

    assert "ยังไม่มีรถ" in html
    assert f"/car_reservation/cars/create?organization_id={world.org.id}" in html


def test_active_car_row_offers_a_deactivate_button_and_inactive_does_not(
    world, create_car
):
    active = create_car(world.org, "กก 1111")
    create_car(world.org, "กก 2222", status="disactive")

    html = world.admin_client.get(world.list_url).get_data(as_text=True)

    assert f"/car_reservation/cars/{active.id}/deactivate" in html
    assert html.count("/deactivate?") == 1  # การ์ดเดียวทุกขนาดจอ เฉพาะรถที่ active


def test_every_member_sees_active_cars_and_drivers_in_the_read_only_directory(
    world, create_car, create_user, assign_user_to_org, create_org
):
    van = create_car(world.org, "กก 1111", vehicle_type="ตู้")
    van.seat_count = 12
    van.save()
    create_car(world.org, "กก 2222", status="disactive")
    create_car(create_org("Other Org"), "ขข 7777")
    driver = create_user("Somchai", "Driver")
    assign_user_to_org(driver, world.org, roles=["driver"])
    assign_user_to_org(create_user("Bystander", "Member"), world.org, roles=["staff"])
    removed = create_user("Gone", "Driver")
    assign_user_to_org(removed, world.org, roles=["driver"], status="disactive")

    response = world.staff_client.get(world.directory_url)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ข้อมูลรถและพนักงานขับรถ" in html
    assert "กก 1111" in html and "รถตู้" in html and "12 ที่นั่ง" in html
    assert "กก 2222" not in html
    assert "ขข 7777" not in html
    assert "Somchai Driver" in html
    assert "Gone Driver" not in html
    assert "Bystander Member" not in html
    assert "/edit" not in html and "/deactivate" not in html


def test_directory_shows_a_driver_profile_picture_only_when_they_have_one(
    app, world, create_user, assign_user_to_org, login_as
):
    with_pic = create_user("Pic", "Driver")
    without = create_user("Nopic", "Driver")
    for driver in (with_pic, without):
        assign_user_to_org(driver, world.org, roles=["driver"])
    login_as(app.test_client(), with_pic).post(
        "/accounts/picture",
        data={"picture": (io.BytesIO(png_bytes()), "me.png", "image/png")},
        content_type="multipart/form-data",
    )

    html = world.staff_client.get(world.directory_url).get_data(as_text=True)

    assert f"/accounts/{with_pic.id}/picture" in html
    assert f"/accounts/{without.id}/picture" not in html


def test_directory_shows_empty_states_when_there_are_no_cars_or_drivers(world):
    html = world.staff_client.get(world.directory_url).get_data(as_text=True)

    assert "ยังไม่มีรถ" in html
    assert "ยังไม่มีพนักงานขับรถ" in html


def test_sidebar_links_to_car_management_for_admins_and_directory_for_everyone(world):
    home = f"/car_reservation/requests/?organization_id={world.org.id}"
    manage_href = f'href="{CARS_PATH}/?organization_id={world.org.id}"'
    directory_href = f'href="{CARS_PATH}/directory?organization_id={world.org.id}"'

    admin_html = world.admin_client.get(home).get_data(as_text=True)
    staff_html = world.staff_client.get(home).get_data(as_text=True)

    assert manage_href in admin_html and "จัดการรถ" in admin_html
    assert manage_href not in staff_html
    assert directory_href in admin_html
    assert directory_href in staff_html


def test_car_without_photo_has_no_image_route(world):
    world.admin_client.post(world.create_url, data=car_data())
    car = models.vehicles.Car.objects(organization=world.org).first()

    assert world.staff_client.get(world.image_url(car)).status_code == 404
