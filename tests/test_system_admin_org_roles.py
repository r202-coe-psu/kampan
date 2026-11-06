"""ผู้ดูแลระบบส่วนกลางเลือก role ที่แต่ละองค์กรใช้ได้ (Organization.enabled_roles)"""

import re

import pytest
from flask import url_for

ORIGINAL_ROLE_KEYS = [
    "staff",
    "endorser",
    "head",
    "supervisor supplier",
    "admin",
    "driver",
    "director",
    "manager",
]


@pytest.fixture
def setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("Role Org")
    global_admin = create_user("Globaladmin", "Roles", roles=["admin"])
    org_admin = create_user("Orgadmin", "Roles")
    assign_user_to_org(org_admin, org, roles=["admin"])
    return {"org": org, "global_admin": global_admin, "org_admin": org_admin}


def _edit_url(app, org):
    with app.test_request_context():
        return url_for(
            "organizations.system_organizations.create_or_edit", organization_id=org.id
        )


def _role_inputs(html):
    return re.findall(r"<input[^>]*name=\"enabled_roles\"[^>]*>", html)


def test_global_admin_saves_enabled_roles(app, login_as, setup):
    org = setup["org"]
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.post(
            _edit_url(app, org),
            data={
                "name": "Role Org",
                "description": "",
                "enabled_roles": ["admin", "staff", "dispatcher"],
            },
        )

    assert response.status_code == 302
    org.reload()
    assert sorted(org.enabled_roles) == ["admin", "dispatcher", "staff"]
    assert [key for key, _ in org.available_roles()] == ["staff", "admin", "dispatcher"]


def test_edit_page_of_unconfigured_organization_ticks_exactly_the_original_roles(
    app, login_as, setup
):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        html = client.get(_edit_url(app, setup["org"])).get_data(as_text=True)

    inputs = _role_inputs(html)
    ticked = [
        re.search(r'value="([^"]*)"', tag).group(1) for tag in inputs if "checked" in tag
    ]
    assert len(inputs) == 14
    assert ticked == ORIGINAL_ROLE_KEYS
    assert "ผู้จัดรถ" in html
    assert "Role ที่เปิดใช้" in html


def test_saving_with_no_role_ticked_keeps_the_organization_on_default_roles(
    app, login_as, setup
):
    org = setup["org"]
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.post(
            _edit_url(app, org), data={"name": "Role Org", "description": ""}
        )

    assert response.status_code == 302
    org.reload()
    assert org.enabled_roles is None


def test_org_admin_cannot_change_enabled_roles(app, login_as, setup):
    org = setup["org"]
    with app.test_client() as client:
        login_as(client, setup["org_admin"])
        response = client.post(
            _edit_url(app, org),
            data={"name": "Role Org", "description": "", "enabled_roles": ["president"]},
        )

    assert response.status_code in (302, 403)
    org.reload()
    assert org.enabled_roles is None
