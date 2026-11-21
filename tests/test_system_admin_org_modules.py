"""ผู้ดูแลระบบส่วนกลางตั้งค่าโมดูลที่เปิดใช้ของแต่ละองค์กร"""

import re

import pytest
from flask import url_for

from kampan import models


@pytest.fixture
def setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("Module Org")
    global_admin = create_user("Globaladmin", "Mod", roles=["admin"])
    org_admin = create_user("Orgadmin", "Mod")
    assign_user_to_org(org_admin, org, roles=["admin"])
    return {"org": org, "global_admin": global_admin, "org_admin": org_admin}


def _edit_url(app, org):
    with app.test_request_context():
        return url_for(
            "organizations.system_organizations.create_or_edit", organization_id=org.id
        )


def _new_url(app):
    with app.test_request_context():
        return url_for("organizations.system_organizations.create_or_edit")


def _post(app, login_as, user, url, data):
    with app.test_client() as client:
        login_as(client, user)
        return client.post(url, data=data)


def test_global_admin_saves_enabled_modules(app, login_as, setup):
    org = setup["org"]
    response = _post(
        app,
        login_as,
        setup["global_admin"],
        _edit_url(app, org),
        {
            "name": "Module Org Renamed",
            "description": "new desc",
            "enabled_modules": ["car", "inventory"],
        },
    )

    assert response.status_code == 302
    org.reload()
    assert org.name == "Module Org Renamed"
    assert org.description == "new desc"
    assert sorted(org.enabled_modules) == ["car", "inventory"]
    assert org.has_module("car")
    assert not org.has_module("procurement")


def test_new_organization_without_ticked_modules_starts_with_everything_off(
    app, login_as, setup
):
    response = _post(
        app,
        login_as,
        setup["global_admin"],
        _new_url(app),
        {"name": "Fresh Org", "description": "d"},
    )

    assert response.status_code == 302
    created = models.Organization.objects(name="Fresh Org").first()
    assert created.enabled_modules == []
    assert not created.has_module("car")


def test_org_admin_cannot_edit_organization_modules(app, login_as, setup):
    org = setup["org"]
    response = _post(
        app,
        login_as,
        setup["org_admin"],
        _edit_url(app, org),
        {
            "name": "Hijacked Org",
            "description": "",
            "enabled_modules": ["car"],
        },
    )

    assert response.status_code in (302, 403)
    org.reload()
    assert org.name == "Module Org"
    assert org.enabled_modules is None


def test_edit_page_shows_module_checkboxes(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.get(_edit_url(app, setup["org"]))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ระบบขอใช้รถยนต์" in html
    assert 'name="enabled_modules"' in html


def test_edit_page_of_unconfigured_organization_ticks_the_default_modules(
    app, login_as, setup
):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        html = client.get(_edit_url(app, setup["org"])).get_data(as_text=True)

    module_inputs = re.findall(r"<input[^>]*name=\"enabled_modules\"[^>]*>", html)
    assert len(module_inputs) == 5
    ticked = {re.search(r'value="([^"]+)"', tag).group(1) for tag in module_inputs if "checked" in tag}
    assert ticked == set(models.organizations.DEFAULT_MODULE_KEYS)


def test_new_organization_page_starts_with_no_module_ticked(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        html = client.get(_new_url(app)).get_data(as_text=True)

    module_inputs = re.findall(r"<input[^>]*name=\"enabled_modules\"[^>]*>", html)
    assert len(module_inputs) == 5
    assert not any("checked" in tag for tag in module_inputs)
