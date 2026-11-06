"""ผู้ดูแลระบบส่วนกลางตั้งค่าโมดูลที่เปิดใช้และรูปแบบการอนุมัติรถของแต่ละองค์กร"""

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


def test_global_admin_saves_enabled_modules_and_car_flow(app, login_as, setup):
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
            "car_flow": "snor",
        },
    )

    assert response.status_code == 302
    org.reload()
    assert org.name == "Module Org Renamed"
    assert org.description == "new desc"
    assert sorted(org.enabled_modules) == ["car", "inventory"]
    assert org.car_flow == "snor"
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
    assert created.car_flow == "diis"
    assert not created.has_module("car")


def test_changing_car_flow_is_refused_while_car_requests_are_open(
    app, login_as, create_car, create_car_application, setup
):
    org = setup["org"]
    car = create_car(org)
    create_car_application(org, car, status="pending on header")
    create_car_application(org, car, status="active")
    create_car_application(org, car, status="completed")

    response = _post(
        app,
        login_as,
        setup["global_admin"],
        _edit_url(app, org),
        {
            "name": "Module Org",
            "description": "",
            "enabled_modules": ["car"],
            "car_flow": "snor",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ใบขอใช้รถที่ยังไม่เสร็จสิ้น 2 ใบ" in html
    org.reload()
    assert org.car_flow == "diis"
    assert org.enabled_modules is None


def test_other_fields_still_save_when_car_flow_is_unchanged_with_open_requests(
    app, login_as, create_car, create_car_application, setup
):
    org = setup["org"]
    car = create_car(org)
    create_car_application(org, car, status="pending on director")

    response = _post(
        app,
        login_as,
        setup["global_admin"],
        _edit_url(app, org),
        {
            "name": "Module Org Renamed",
            "description": "",
            "enabled_modules": ["car"],
            "car_flow": "diis",
        },
    )

    assert response.status_code == 302
    org.reload()
    assert org.name == "Module Org Renamed"
    assert org.enabled_modules == ["car"]


def test_closed_requests_do_not_block_changing_car_flow(
    app, login_as, create_car, create_car_application, setup
):
    org = setup["org"]
    car = create_car(org)
    for status in ["completed", "disactive", "denied by header", "denied by admin"]:
        create_car_application(org, car, status=status)

    response = _post(
        app,
        login_as,
        setup["global_admin"],
        _edit_url(app, org),
        {"name": "Module Org", "description": "", "car_flow": "snor"},
    )

    assert response.status_code == 302
    org.reload()
    assert org.car_flow == "snor"


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
            "car_flow": "snor",
        },
    )

    assert response.status_code in (302, 403)
    org.reload()
    assert org.name == "Module Org"
    assert org.enabled_modules is None
    assert org.car_flow == "diis"


def test_edit_page_shows_module_checkboxes_and_car_flow_choices(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.get(_edit_url(app, setup["org"]))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "ระบบขอใช้รถยนต์" in html
    assert 'name="enabled_modules"' in html
    assert 'name="car_flow"' in html


def test_edit_page_of_unconfigured_organization_shows_all_modules_ticked(
    app, login_as, setup
):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        html = client.get(_edit_url(app, setup["org"])).get_data(as_text=True)

    module_inputs = re.findall(r"<input[^>]*name=\"enabled_modules\"[^>]*>", html)
    assert len(module_inputs) == 4
    assert all("checked" in tag for tag in module_inputs)


def test_new_organization_page_starts_with_no_module_ticked(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        html = client.get(_new_url(app)).get_data(as_text=True)

    module_inputs = re.findall(r"<input[^>]*name=\"enabled_modules\"[^>]*>", html)
    assert len(module_inputs) == 4
    assert not any("checked" in tag for tag in module_inputs)
