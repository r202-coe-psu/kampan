import pytest


@pytest.fixture
def legacy_disabled(app):
    previous = app.config.get("CAR_LEGACY_FLOW_ENABLED")
    app.config["CAR_LEGACY_FLOW_ENABLED"] = False
    yield
    app.config["CAR_LEGACY_FLOW_ENABLED"] = previous


@pytest.fixture
def admin_client(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org(name="DIIS")
    admin = create_user("Admin", "User")
    assign_user_to_org(admin, org, roles=["admin", "head", "director"])
    client = login_as(app.test_client(), admin)
    return client, org


@pytest.mark.parametrize("page", ["header_page", "director_page", "admin_page", "header_approve", "admin_approve", "director_denied"])
def test_legacy_approval_pages_are_hidden_when_disabled(legacy_disabled, admin_client, page):
    client, org = admin_client
    resp = client.get(f"/vehicle_lending/car_permissions/{page}?organization_id={org.id}")
    assert resp.status_code == 404


def test_sidebar_hides_legacy_approval_menus_when_disabled(legacy_disabled, admin_client):
    client, org = admin_client
    resp = client.get(f"/vehicle_lending/car_form_requests/new?organization_id={org.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "หัวหน้าฝ่ายอนุมัติขอใช้รถยนต์" not in html
    assert "ผอ. อนุมัติขอใช้รถยนต์" not in html
    assert "พัสดุอนุมัติขอใช้รถยนต์" not in html
    assert "รายการที่ต้องอนุมัติ" in html


@pytest.mark.parametrize(
    "path",
    ["", "/create", "/combine_paper", "/000000000000000000000000/edit", "/000000000000000000000000/paper", "/000000000000000000000000/delete"],
)
def test_legacy_request_pages_are_hidden_when_disabled(legacy_disabled, admin_client, path):
    client, org = admin_client
    resp = client.get(f"/vehicle_lending/car_applications{path}?organization_id={org.id}")
    assert resp.status_code == 404


def test_calendar_stays_and_its_new_request_button_goes_to_the_template_request_page(legacy_disabled, admin_client):
    client, org = admin_client
    resp = client.get(f"/vehicle_lending/car_applications/calendar?organization_id={org.id}")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "/vehicle_lending/car_applications/create" not in html
    assert f"/vehicle_lending/car_form_requests/new?organization_id={org.id}" in html
    assert 'const url = "/vehicle_lending/car_form_requests/new?' in html or "dateClick" not in html


def test_sidebar_hides_the_legacy_request_menu_but_keeps_the_calendar(legacy_disabled, admin_client):
    from kampan import models

    client, org = admin_client
    member = models.OrganizationUserRole.objects(organization=org).first()
    member.division = models.Division(name="ฝ่ายทดสอบ", organization=org).save()
    member.save()
    html = client.get(f"/vehicle_lending/car_form_requests/?organization_id={org.id}").get_data(as_text=True)

    assert f'href="/vehicle_lending/car_applications?organization_id={org.id}"' not in html
    assert "ph-hand-arrow-up" not in html
    assert "ปฏิทินการขอใช้รถยนต์" in html


@pytest.mark.parametrize(
    "roles, sees_inbox",
    [(["driver", "staff"], False), (["staff"], True), (["driver", "head"], True)],
)
def test_sidebar_shows_the_approval_inbox_only_to_people_who_can_approve(
    app, create_org, create_user, assign_user_to_org, login_as, roles, sees_inbox
):
    org = create_org(name="DIIS")
    user = create_user("Some", "One")
    assign_user_to_org(user, org, roles=roles)
    client = login_as(app.test_client(), user)

    html = client.get(f"/vehicle_lending/car_form_requests/?organization_id={org.id}").get_data(as_text=True)

    assert "คำขอใช้รถ" in html
    assert ("รายการที่ต้องอนุมัติ" in html) is sees_inbox
