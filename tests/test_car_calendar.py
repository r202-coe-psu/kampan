import datetime

from kampan import models, utils


def test_calendar_lists_pending_form_requests(
    app, create_org, create_user, assign_user_to_org, create_car, create_car_application, login_as
):
    org = create_org()
    staff = create_user("Staff", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    pending = create_car_application(org, create_car(org), status="pending")
    client = app.test_client()
    login_as(client, staff)

    res = client.get(f"/vehicle_lending/car_applications/get_car_applications?organization_id={org.id}")

    assert str(pending.id) in [event["id"] for event in res.get_json()["car_applications"]]
