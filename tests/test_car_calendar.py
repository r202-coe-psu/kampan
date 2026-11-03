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


def _calendar_event(app, org, staff, login_as, application):
    client = app.test_client()
    login_as(client, staff)
    res = client.get(f"/vehicle_lending/car_applications/get_car_applications?organization_id={org.id}")
    return next(e for e in res.get_json()["car_applications"] if e["id"] == str(application.id))


def test_form_request_spans_until_return_date(
    app, create_org, create_user, assign_user_to_org, create_car, create_car_application, login_as
):
    org = create_org()
    staff = create_user("Staff", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    application = create_car_application(org, create_car(org), status="pending")
    application.form_template = models.car_form_templates.CarFormTemplate(organization=org, name="แบบฟอร์ม").save(validate=False)
    application.departure_datetime = datetime.datetime(2026, 11, 4, 0, 29)
    application.return_datetime = datetime.datetime(2026, 11, 28, 0, 29)
    application.save()

    event = _calendar_event(app, org, staff, login_as, application)

    assert (event["start"], event["end"]) == ("2026-11-04", "2026-11-29")


def test_return_time_before_departure_shows_departure_day_only(
    app, create_org, create_user, assign_user_to_org, create_car, create_car_application, login_as
):
    org = create_org()
    staff = create_user("Staff", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    application = create_car_application(org, create_car(org), status="completed")
    application.form_template = models.car_form_templates.CarFormTemplate(organization=org, name="แบบฟอร์ม").save(validate=False)
    application.departure_datetime = datetime.datetime(2026, 11, 4, 22, 36)
    application.return_datetime = datetime.datetime(2026, 11, 3, 23, 52)
    application.save()

    event = _calendar_event(app, org, staff, login_as, application)

    assert (event["start"], event["end"]) == ("2026-11-04", "2026-11-05")
