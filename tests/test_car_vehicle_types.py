import pytest

from kampan import models


@pytest.fixture
def org_admin(create_org, create_user, assign_user_to_org):
    org = create_org(name="กองกายภาพ")
    admin = create_user("Admin", "User")
    assign_user_to_org(admin, org, roles=["admin"])
    return {"org": org, "admin": admin}


def test_org_admin_saves_a_car_with_a_vehicle_type_and_the_car_list_shows_it(
    app, org_admin, login_as
):
    """An org admin saves a car with a vehicle type and the car list shows it"""
    org_id = str(org_admin["org"].id)
    client = login_as(app.test_client(), org_admin["admin"])

    form_page = client.get(f"/vehicle_lending/cars/create?organization_id={org_id}")
    assert "ประเภทรถ" in form_page.get_data(as_text=True)

    res = client.post(
        f"/vehicle_lending/cars/create?organization_id={org_id}",
        data={"license_plate": "กข-1234", "last_mileage": "0", "vehicle_type": "ตู้"},
    )
    assert res.status_code == 302

    listing = client.get(f"/vehicle_lending/cars?organization_id={org_id}")
    html = listing.get_data(as_text=True)
    assert "กข-1234" in html
    assert "รถตู้" in html


def test_org_admin_saves_a_car_without_a_vehicle_type(app, org_admin, login_as):
    """Cars saved without choosing a vehicle type stay valid (existing cars have none)"""
    org_id = str(org_admin["org"].id)
    client = login_as(app.test_client(), org_admin["admin"])

    res = client.post(
        f"/vehicle_lending/cars/create?organization_id={org_id}",
        data={"license_plate": "กข-9999", "last_mileage": "0", "vehicle_type": ""},
    )

    assert res.status_code == 302
    car = models.vehicles.Car.objects(license_plate="กข-9999").first()
    assert car is not None
