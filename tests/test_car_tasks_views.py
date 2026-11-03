import pytest

TASKS = "/vehicle_lending/car_tasks"


@pytest.fixture
def tasks_setup(create_org, create_user, assign_user_to_org, create_car, create_car_application):
    org = create_org("Org A")
    admin = create_user("Admin", "A")
    driver_a = create_user("DriverA", "A")
    driver_b = create_user("DriverB", "B")
    assign_user_to_org(admin, org, roles=["admin"])
    assign_user_to_org(driver_a, org, roles=["driver"])
    assign_user_to_org(driver_b, org, roles=["driver"])
    car_a = create_car(org, "กก 1111")
    car_b = create_car(org, "ขข 2222")
    task_a = create_car_application(org, car_a, location="งานของคนขับ-ก")
    task_a.driver = driver_a
    task_a.save()
    task_b = create_car_application(org, car_b, location="งานของคนขับ-ข")
    task_b.driver = driver_b
    task_b.save()
    return {"org": org, "admin": admin, "driver_a": driver_a, "task_a": task_a, "task_b": task_b}


def test_driver_sees_only_tasks_assigned_to_them(app, tasks_setup, login_as):
    s = tasks_setup
    html = login_as(app.test_client(), s["driver_a"]).get(
        f"{TASKS}?organization_id={s['org'].id}"
    ).get_data(as_text=True)

    assert "งานของคนขับ-ก" in html
    assert "งานของคนขับ-ข" not in html


def test_admin_sees_every_task(app, tasks_setup, login_as):
    s = tasks_setup
    html = login_as(app.test_client(), s["admin"]).get(
        f"{TASKS}?organization_id={s['org'].id}"
    ).get_data(as_text=True)

    assert "งานของคนขับ-ก" in html
    assert "งานของคนขับ-ข" in html


def test_driver_cannot_close_a_task_assigned_to_another_driver(app, tasks_setup, login_as):
    s = tasks_setup
    res = login_as(app.test_client(), s["driver_a"]).post(
        f"{TASKS}/submit_tasks/{s['task_b'].id}?organization_id={s['org'].id}",
        data={"last_mileage": 999},
    )
    s["task_b"].reload()

    # acl แปลง 403 เป็น redirect ไปหน้า login
    assert res.status_code in (302, 403)
    if res.status_code == 302:
        assert "/login" in res.headers["Location"]
    assert s["task_b"].status == "active"


def test_driver_can_close_their_own_task(app, tasks_setup, login_as):
    s = tasks_setup
    login_as(app.test_client(), s["driver_a"]).post(
        f"{TASKS}/submit_tasks/{s['task_a'].id}?organization_id={s['org'].id}",
        data={"last_mileage": 999},
    )
    s["task_a"].reload()

    assert s["task_a"].status == "completed"
