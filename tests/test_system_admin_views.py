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
    assert _url(app, "users.index") in html
    assert _url(app, "organizations.system_organizations.index") in html


def test_org_admin_does_not_see_system_section(app, login_as, setup):
    url = _url(app, "organizations.divisions.index", organization_id=setup["org"].id)
    response = _get(app, login_as, setup["org_admin"], url)

    assert response.status_code == 200
    assert SYSTEM_SECTION not in response.get_data(as_text=True)


CENTRAL_PAGES = [
    ("users.index", False),
    ("users.edit_roles", "user"),
    ("organizations.system_organizations.index", False),
    ("organizations.system_organizations.create_or_edit", False),
    ("organizations.system_organizations.create_or_edit", "org"),
]


def _central_url(app, setup, endpoint, needs):
    kwargs = {}
    if needs == "org":
        kwargs["organization_id"] = setup["org"].id
    if needs == "user":
        kwargs["user_id"] = setup["staff"].id
    return _url(app, endpoint, **kwargs)


@pytest.mark.parametrize("who", ["org_admin", "staff", "global_supervisor"])
@pytest.mark.parametrize("endpoint,needs", CENTRAL_PAGES)
def test_central_pages_are_only_for_system_admin(app, login_as, setup, create_user, who, endpoint, needs):
    # ระบบส่วนกลางใช้ได้เฉพาะ User.roles มี admin; admin ขององค์กรหรือ role ระบบอื่นเข้าไม่ได้
    user = create_user("Supervisor", "Sys", roles=["supervisor"]) if who == "global_supervisor" else setup[who]
    response = _get(app, login_as, user, _central_url(app, setup, endpoint, needs))

    assert response.status_code in (302, 403)
    if response.status_code == 302:
        assert response.headers["Location"].startswith(_url(app, "accounts.login"))


def test_central_actions_are_only_for_system_admin(app, login_as, setup):
    org = setup["org"]
    with app.test_client() as client:
        login_as(client, setup["org_admin"])
        client.post(_url(app, "organizations.system_organizations.create_or_edit"), data={"name": "Sneaky Org"})
        client.post(_url(app, "organizations.system_organizations.delete", organization_id=org.id))
        client.post(_url(app, "users.edit_roles", user_id=setup["org_admin"].id), data={"roles": ["admin"]})

    org.reload()
    setup["org_admin"].reload()
    assert models.Organization.objects(name="Sneaky Org").first() is None
    assert org.status == "active"
    assert "admin" not in setup["org_admin"].roles


def test_central_urls_are_short(app):
    assert _url(app, "organizations.system_organizations.index") == "/organizations/"
    assert _url(app, "organizations.system_organizations.create_or_edit") == "/organizations/new"
    assert _url(app, "users.index") == "/users/"


@pytest.mark.parametrize(
    "endpoint,needs_org,needs_org_user",
    [
        ("users.index", False, False),
        ("organizations.system_organizations.index", False, False),
        ("organizations.system_organizations.create_or_edit", False, False),
        ("organizations.system_organizations.create_or_edit", True, False),
        # สมาชิกขององค์กร global admin ใช้หน้าเดียวกับ admin ขององค์กร
        ("organizations.overview.index", True, False),
        ("organizations.members.index", True, False),
        ("organizations.members.add_member", True, False),
        ("organizations.members.edit_roles", True, True),
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

        response = client.post(
            _url(app, "organizations.system_organizations.delete", organization_id=created.id)
        )
        assert response.status_code == 302

    created.reload()
    assert created.status == "disactive"


def test_member_pages_reject_member_of_another_organization(
    app, login_as, create_org, assign_user_to_org, setup
):
    other_org = create_org("Other Org")
    assign_user_to_org(setup["org_admin"], other_org, roles=["admin"])
    edit_url = _url(
        app,
        "organizations.members.edit_roles",
        organization_id=other_org.id,
        org_user_id=setup["staff_role"].id,
    )
    remove_url = _url(
        app,
        "organizations.members.remove_org_user",
        organization_id=other_org.id,
        org_user_id=setup["staff_role"].id,
    )

    with app.test_client() as client:
        login_as(client, setup["org_admin"])
        assert client.get(edit_url).status_code == 404
        assert client.post(remove_url).status_code == 404

    setup["staff_role"].reload()
    assert setup["staff_role"].status == "active"


def test_old_system_urls_redirect(app, login_as, setup):
    org_id = setup["org"].id
    member_id = setup["staff_role"].id
    expected = {
        "/organizations/system/organizations/?q=x": "/organizations/?q=x",
        "/organizations/system/organizations/create": "/organizations/new",
        f"/organizations/system/organizations/{org_id}/detail": f"/organizations/{org_id}/",
        f"/organizations/system/organizations/{org_id}/users": f"/organizations/{org_id}/members/",
        f"/organizations/system/organizations/{org_id}/add-member": f"/organizations/{org_id}/members/add",
        f"/organizations/system/organizations/{org_id}/users/{member_id}/edit-roles": f"/organizations/{org_id}/members/{member_id}/edit_roles",
        "/organizations/system/users/": "/users/",
    }
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        for old, new in expected.items():
            response = client.get(old)
            assert response.status_code == 301, old
            assert response.headers["Location"] == new, old


def test_old_admin_urls_redirect_to_organization_module(app, login_as, setup):
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        admin_index = client.get("/admin/")
        admin_orgs = client.get("/admin/organizations/")

    assert admin_index.headers["Location"] == _url(app, "users.index")
    assert admin_orgs.status_code == 301
    assert admin_orgs.headers["Location"] == _url(
        app, "organizations.system_organizations.index"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "item_orders.index",
        "procurement.products.index",
    ],
)
def test_org_admin_sees_manage_button_next_to_switcher(app, login_as, setup, endpoint):
    url = _url(app, endpoint, organization_id=setup["org"].id)
    response = _get(app, login_as, setup["org_admin"], url)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert MANAGE_BUTTON in html
    assert _url(app, "organizations.overview.index", organization_id=setup["org"].id) in html


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


def test_global_admin_adds_member_with_roles_and_division(app, login_as, setup, create_user, create_org):
    org = setup["org"]
    admin = setup["global_admin"]
    newcomer = create_user("Newcomer", "Sys")
    outsider_pick = create_user("Otherpick", "Sys")
    division = models.Division(name="Finance", organization=org, created_by=admin, last_updated_by=admin).save()
    foreign_division = models.Division(
        name="Foreign", organization=create_org("Foreign Org"), created_by=admin, last_updated_by=admin
    ).save()
    url = _url(app, "organizations.members.add_member", organization_id=org.id)

    with app.test_client() as client:
        login_as(client, admin)
        page = client.get(url).get_data(as_text=True)
        response = client.post(
            url,
            data={
                "members": str(newcomer.id),
                "roles": ["staff", "head"],
                "division": str(division.id),
                "appointment": "นักวิชาการพัสดุ",
            },
        )
        client.post(
            url,
            data={
                "members": str(outsider_pick.id),
                "roles": ["staff"],
                "division": str(foreign_division.id),
            },
        )

    # หน้าเลือกผู้ใช้แสดงคนที่ยังไม่อยู่ในองค์กร พร้อมอีเมล และตำแหน่งเป็นการ์ดสีของ role
    assert 'value="{}"'.format(newcomer.id) in page
    assert newcomer.email in page
    assert 'value="{}"'.format(setup["org_admin"].id) not in page
    assert "role-badge role-head" in page

    assert response.status_code == 302
    added = models.OrganizationUserRole.objects(organization=org, user=newcomer).first()
    assert added.roles == ["staff", "head"]
    assert added.division.id == division.id
    assert added.appointment == "นักวิชาการพัสดุ"
    # id แผนกขององค์กรอื่นไม่อยู่ในตัวเลือก ฟอร์มจึงไม่ผ่านและไม่บันทึกอะไร
    assert models.OrganizationUserRole.objects(user=outsider_pick).first() is None


def test_add_member_requires_a_role(app, login_as, setup, create_user):
    newcomer = create_user("Noroles", "Sys")
    url = _url(app, "organizations.members.add_member", organization_id=setup["org"].id)

    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.post(url, data={"members": str(newcomer.id)})

    assert response.status_code == 200
    assert not models.OrganizationUserRole.objects(user=newcomer).first()


def test_organization_list_searches_name_and_description(app, login_as, setup, create_org):
    finance = create_org("Finance Office")
    legal = create_org("Legal Office")
    legal.description = "งานนิติการ"
    legal.save()
    url = _url(app, "organizations.system_organizations.index")

    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        by_name = client.get(url, query_string={"q": "finance"}).get_data(as_text=True)
        by_description = client.get(url, query_string={"q": "นิติ"}).get_data(as_text=True)
        none_found = client.get(url, query_string={"q": "zzz"}).get_data(as_text=True)

    def table(html):
        # sidebar switcher ของ global admin แสดงทุกองค์กร จึงตรวจเฉพาะในตาราง
        return html[html.index("<tbody>"):html.index("</tbody>")]

    assert "Finance Office" in table(by_name) and "Legal Office" not in table(by_name)
    assert "Legal Office" in table(by_description) and "Finance Office" not in table(by_description)
    assert "ไม่พบองค์กรที่ค้นหา" in none_found
