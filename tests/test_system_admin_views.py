"""หน้าผู้ดูแลระบบส่วนกลาง (ผู้ใช้/องค์กรทั้งหมด) ที่ย้ายมาอยู่ในระบบจัดการองค์กร
และปุ่มจัดการองค์กรข้าง organization switcher"""

import pytest
from flask import url_for

from kampan import models

SYSTEM_SECTION = "ผู้ดูแลระบบส่วนกลาง"
MANAGE_BUTTON = 'aria-label="จัดการองค์กร"'


@pytest.fixture
def setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("System Org")
    global_admin = create_user("Globaladmin", "Sys", roles=["admin"])
    org_admin = create_user("Orgadmin", "Sys")
    staff = create_user("Staffer", "Sys")
    assign_user_to_org(org_admin, org, roles=["admin"])
    staff_role = assign_user_to_org(staff, org, roles=["staff"], added_by=org_admin)
    return {
        "org": org,
        "global_admin": global_admin,
        "org_admin": org_admin,
        "staff": staff,
        "staff_role": staff_role,
    }


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _get(app, login_as, user, url):
    with app.test_client() as client:
        login_as(client, user)
        return client.get(url)


def test_global_admin_sees_system_section_in_organization_sidebar(app, login_as, setup):
    url = _url(app, "organizations.divisions.index", organization_id=setup["org"].id)
    html = _get(app, login_as, setup["global_admin"], url).get_data(as_text=True)

    assert SYSTEM_SECTION in html
    assert _url(app, "organizations.system_users.index") in html
    assert _url(app, "organizations.system_organizations.index") in html


def test_org_admin_does_not_see_system_section(app, login_as, setup):
    url = _url(app, "organizations.divisions.index", organization_id=setup["org"].id)
    response = _get(app, login_as, setup["org_admin"], url)

    assert response.status_code == 200
    assert SYSTEM_SECTION not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    "endpoint",
    ["organizations.system_users.index", "organizations.system_organizations.index"],
)
def test_org_admin_is_denied_system_pages(app, login_as, setup, endpoint):
    response = _get(app, login_as, setup["org_admin"], _url(app, endpoint))

    assert response.status_code in (302, 403)
    if response.status_code == 302:
        assert response.headers["Location"].startswith(_url(app, "accounts.login"))


@pytest.mark.parametrize(
    "endpoint,needs_org,needs_org_user",
    [
        ("organizations.system_users.index", False, False),
        ("organizations.system_organizations.index", False, False),
        ("organizations.system_organizations.create_or_edit", False, False),
        ("organizations.system_organizations.create_or_edit", True, False),
        ("organizations.system_organizations.detail", True, False),
        ("organizations.system_organizations.add_member", True, False),
        ("organizations.system_organizations.users", True, False),
        ("organizations.system_organizations.edit_roles", True, True),
    ],
)
def test_global_admin_can_open_system_pages(
    app, login_as, setup, endpoint, needs_org, needs_org_user
):
    kwargs = {}
    if needs_org:
        kwargs["organization_id"] = setup["org"].id
    if needs_org_user:
        kwargs["org_user_id"] = setup["staff_role"].id

    response = _get(app, login_as, setup["global_admin"], _url(app, endpoint, **kwargs))

    assert response.status_code == 200


def test_global_admin_creates_and_deletes_organization(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.post(
            _url(app, "organizations.system_organizations.create_or_edit"),
            data={"name": "Brand New Org", "description": "desc"},
        )
        assert response.status_code == 302
        created = models.Organization.objects(name="Brand New Org").first()
        assert created is not None

        response = client.get(
            _url(app, "organizations.system_organizations.delete", organization_id=created.id)
        )
        assert response.status_code == 302

    created.reload()
    assert created.status == "disactive"


def test_edit_roles_rejects_member_of_another_organization(
    app, login_as, create_org, setup
):
    other_org = create_org("Other Org")
    url = _url(
        app,
        "organizations.system_organizations.edit_roles",
        organization_id=other_org.id,
        org_user_id=setup["staff_role"].id,
    )

    assert _get(app, login_as, setup["global_admin"], url).status_code == 404


def test_old_admin_urls_redirect_to_organization_module(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        admin_index = client.get("/admin/")
        admin_orgs = client.get("/admin/organizations/")

    assert admin_index.headers["Location"] == _url(app, "organizations.system_users.index")
    assert admin_orgs.status_code == 301
    assert admin_orgs.headers["Location"] == _url(
        app, "organizations.system_organizations.index"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "item_orders.index",
        "procurement.requisitions.renewal_requested",
    ],
)
def test_org_admin_sees_manage_button_next_to_switcher(app, login_as, setup, endpoint):
    url = _url(app, endpoint, organization_id=setup["org"].id)
    response = _get(app, login_as, setup["org_admin"], url)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert MANAGE_BUTTON in html
    assert _url(app, "organizations.divisions.index", organization_id=setup["org"].id) in html


def test_staff_does_not_see_manage_button(app, login_as, setup):
    url = _url(app, "item_orders.index", organization_id=setup["org"].id)
    html = _get(app, login_as, setup["staff"], url).get_data(as_text=True)

    assert MANAGE_BUTTON not in html
    assert "จัดการองค์กร" not in html


def test_manage_button_hidden_inside_organization_module(app, login_as, setup):
    url = _url(app, "organizations.divisions.index", organization_id=setup["org"].id)
    html = _get(app, login_as, setup["org_admin"], url).get_data(as_text=True)

    assert MANAGE_BUTTON not in html


def test_select_system_links_org_management_from_organization_card(app, login_as, setup):
    url = _url(app, "site.select_system", organization_id=setup["org"].id)
    response = _get(app, login_as, setup["global_admin"], url)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "ระบบผู้ดูแลระบบ" not in html
    assert "ระบบจัดการองค์กร" not in html
    assert MANAGE_BUTTON in html
