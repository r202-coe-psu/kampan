import datetime

from kampan import models, utils


def _states(progress):
    return [(step["label"], step["state"]) for step in progress]


def test_legacy_general_request_waiting_on_header(app, create_org, create_car, create_car_application):
    org = create_org()
    application = create_car_application(org, create_car(org), status="pending on header")

    assert _states(utils.car_form_flow.step_progress(application)) == [
        ("หัวหน้าฝ่าย", "current"),
        ("เจ้าหน้าที่พัสดุ", "waiting"),
    ]


def test_legacy_out_of_town_request_approved_by_admin_waits_on_director(
    app, create_org, create_user, create_car, create_car_application
):
    org = create_org()
    admin = create_user("Admin", "User")
    application = create_car_application(org, create_car(org), status="pending on director")
    application.using_type = "out of town"
    application.header_approval = models.vehicle_applications.CarApplicationApproval(
        approved_at=datetime.datetime(2026, 1, 10, 9, 0)
    )
    application.admin_approval = models.vehicle_applications.CarApplicationApproval(
        approved_by=admin, approved_at=datetime.datetime(2026, 1, 11, 9, 0)
    )
    application.save()

    progress = utils.car_form_flow.step_progress(application)

    assert _states(progress) == [
        ("หัวหน้าฝ่าย", "done"),
        ("เจ้าหน้าที่พัสดุ", "done"),
        ("ผู้อำนวยการ", "current"),
    ]
    assert progress[1]["decided_by"] == admin.get_resources_fullname_th()


def test_legacy_request_denied_by_header_skips_the_rest(app, create_org, create_car, create_car_application):
    org = create_org()
    application = create_car_application(org, create_car(org), status="denied by header")

    assert _states(utils.car_form_flow.step_progress(application)) == [
        ("หัวหน้าฝ่าย", "denied"),
        ("เจ้าหน้าที่พัสดุ", "skipped"),
    ]


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


def test_event_modal_shows_stepper(
    app, create_org, create_user, assign_user_to_org, create_car, create_car_application, login_as
):
    org = create_org()
    staff = create_user("Staff", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    application = create_car_application(org, create_car(org), status="pending on header")
    client = app.test_client()
    login_as(client, staff)

    res = client.get(f"/vehicle_lending/car_applications/{application.id}/modal?organization_id={org.id}")

    html = res.get_data(as_text=True)
    assert "data-stepper" in html
    assert "หัวหน้าฝ่าย" in html


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
