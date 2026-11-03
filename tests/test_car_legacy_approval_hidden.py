import pytest


@pytest.fixture
def legacy_disabled(app):
    previous = app.config.get("CAR_LEGACY_APPROVAL_ENABLED")
    app.config["CAR_LEGACY_APPROVAL_ENABLED"] = False
    yield
    app.config["CAR_LEGACY_APPROVAL_ENABLED"] = previous


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
