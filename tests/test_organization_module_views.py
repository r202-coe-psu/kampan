import re

import pytest
from flask import url_for

from kampan import models

# (endpoint, needs_division, needs_org_user)
ADMIN_ONLY_ROUTES = [
    ("organizations.divisions.index", False, False),
    ("organizations.divisions.detail", True, False),
    ("organizations.members.index", False, False),
    ("organizations.members.add_member", False, False),
    ("organizations.members.edit_roles", False, True),
    ("organizations.overview.index", False, False),
]
ROUTE_IDS = [
    f"{endpoint}{'-division' if division else ''}{'-orguser' if org_user else ''}"
    for endpoint, division, org_user in ADMIN_ONLY_ROUTES
]


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _build_url(app, endpoint, org, division=None, org_user=None):
    kwargs = {"organization_id": str(org.id)}
    if division is not None:
        kwargs["division_id"] = str(division.id)
    if org_user is not None:
        kwargs["org_user_id"] = str(org_user.id)
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


@pytest.fixture
def org_setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("Org Module")
    admin = create_user("Adminuser", "Org")
    staff = create_user("Staffuser", "Org")
    admin_role = assign_user_to_org(admin, org, roles=["admin"])
    staff_role = assign_user_to_org(staff, org, roles=["staff"], added_by=admin)
    division = models.Division(
        name="Division One",
        organization=org,
        created_by=admin,
        last_updated_by=admin,
        status="active",
    )
    division.save()
    return {
        "org": org,
        "admin": admin,
        "staff": staff,
        "admin_role": admin_role,
        "staff_role": staff_role,
        "division": division,
    }


def _urls(app, s, endpoint, with_division, with_org_user):
    return _build_url(
        app,
        endpoint,
        s["org"],
        division=s["division"] if with_division else None,
        org_user=s["staff_role"] if with_org_user else None,
    )


@pytest.mark.parametrize(
    "endpoint,with_division,with_org_user", ADMIN_ONLY_ROUTES, ids=ROUTE_IDS
)
def test_org_admin_can_open_organization_pages(
    app, org_setup, endpoint, with_division, with_org_user
):
    url = _urls(app, org_setup, endpoint, with_division, with_org_user)
    with app.test_client() as client:
        _login(client, org_setup["admin"])
        response = client.get(url)
        assert response.status_code == 200, url


def test_org_admin_can_open_upload_page(app, org_setup):
    with app.test_request_context():
        url = url_for(
            "organizations.members.upload_member_file",
            organization_id=str(org_setup["org"].id),
        )
    with app.test_client() as client:
        _login(client, org_setup["admin"])
        assert client.get(url).status_code == 200


def test_org_staff_can_open_upload_page(app, org_setup):
    with app.test_request_context():
        url = url_for(
            "organizations.members.upload_member_file",
            organization_id=str(org_setup["org"].id),
        )
    with app.test_client() as client:
        _login(client, org_setup["staff"])
        assert client.get(url).status_code == 200


@pytest.mark.parametrize(
    "endpoint,with_division,with_org_user", ADMIN_ONLY_ROUTES, ids=ROUTE_IDS
)
def test_org_staff_is_denied_admin_only_pages(
    app, org_setup, endpoint, with_division, with_org_user
):
    url = _urls(app, org_setup, endpoint, with_division, with_org_user)
    with app.test_client() as client:
        _login(client, org_setup["staff"])
        response = client.get(url)
        # acl turns 403 into a redirect to the login page
        assert response.status_code in (302, 403), url
        if response.status_code == 302:
            with app.test_request_context():
                login_url = url_for("accounts.login")
            assert response.headers["Location"].startswith(login_url)


def test_divisions_index_uses_organization_layout(app, org_setup):
    org = org_setup["org"]
    with app.test_request_context():
        index_url = url_for(
            "organizations.divisions.index", organization_id=str(org.id)
        )
        members_url = url_for(
            "organizations.members.index", organization_id=str(org.id)
        )
        item_orders_url = url_for("item_orders.index", organization_id=str(org.id))

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        html = client.get(index_url).get_data(as_text=True)

    assert members_url in html.replace("&amp;", "&")
    assert item_orders_url not in html.replace("&amp;", "&")
    assert "/item_orders" not in html


def test_email_templates_page_uses_organization_layout(app, org_setup):
    org = org_setup["org"]
    with app.test_request_context():
        email_templates_url = url_for(
            "email_templates.index", organization_id=str(org.id)
        )
        members_url = url_for(
            "organizations.members.index", organization_id=str(org.id)
        )
        divisions_url = url_for(
            "organizations.divisions.index", organization_id=str(org.id)
        )

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        response = client.get(email_templates_url)
        org_html = client.get(divisions_url).get_data(as_text=True)

    assert response.status_code == 200
    html = response.get_data(as_text=True).replace("&amp;", "&")
    assert members_url in html
    assert "/item_orders" not in html
    assert email_templates_url in org_html.replace("&amp;", "&")


def test_email_template_create_page_uses_organization_layout(app, org_setup):
    org = org_setup["org"]
    with app.test_request_context():
        create_url = url_for(
            "email_templates.create_or_edit", organization_id=str(org.id)
        )

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        response = client.get(create_url)

    assert response.status_code == 200
    assert "/item_orders" not in response.get_data(as_text=True)


def test_divisions_index_pagination_links_to_divisions_index(app, org_setup):
    org = org_setup["org"]
    admin = org_setup["admin"]
    for i in range(34):
        models.Division(
            name=f"Division extra {i}",
            organization=org,
            created_by=admin,
            last_updated_by=admin,
            status="active",
        ).save()

    with app.test_request_context():
        index_url = url_for(
            "organizations.divisions.index", organization_id=str(org.id)
        )

    with app.test_client() as client:
        _login(client, admin)
        response = client.get(index_url)
        assert response.status_code == 200
        html = response.get_data(as_text=True).replace("&amp;", "&")
        page2 = client.get(index_url + "&page=2")
        assert page2.status_code == 200

    hrefs = re.findall(r'href=["\']([^"\']*page=2[^"\']*)["\']', html)
    assert hrefs, "page 2 link not rendered"
    assert all(h.startswith("/organizations/divisions") for h in hrefs), hrefs
    assert "/item_orders" not in html


def test_details_redirects_to_overview(app, org_setup):
    org = org_setup["org"]
    with app.test_request_context():
        details_url = url_for("organizations.details.index", organization_id=str(org.id))
        overview_url = url_for("organizations.overview.index", organization_id=str(org.id))

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        response = client.get(details_url)

    assert response.status_code == 301
    assert response.headers["Location"] == overview_url


def test_overview_counts_members_per_division(app, org_setup, create_user, assign_user_to_org):
    org = org_setup["org"]
    admin = org_setup["admin"]
    division = org_setup["division"]
    empty_division = models.Division(
        name="Empty Division",
        organization=org,
        created_by=admin,
        last_updated_by=admin,
        status="active",
    ).save()
    deleted_division = models.Division(
        name="Deleted Division",
        organization=org,
        created_by=admin,
        last_updated_by=admin,
        status="disactive",
    ).save()

    def member(name, member_division, status="active"):
        org_user = assign_user_to_org(create_user(name, "Member"), org, status=status, added_by=admin)
        org_user.division = member_division
        org_user.save()

    member("Alpha", division)
    member("Bravo", division)
    member("Charlie", division, status="pending")
    member("Delta", division, status="disactive")
    member("Echo", deleted_division)

    # สมาชิกขององค์กรอื่นต้องไม่ถูกนับ
    other_org = models.Organization(name="Other", status="active").save()
    assign_user_to_org(create_user("Outsider", "Member"), other_org, added_by=admin)

    with app.test_request_context():
        url = url_for("organizations.overview.index", organization_id=str(org.id))

    with app.test_client() as client:
        _login(client, admin)
        response = client.get(url)

    assert response.status_code == 200
    context_rows = {}
    html = response.get_data(as_text=True)
    for row in re.findall(r"<tr [^>]*data-division-row>(.*?)</tr>", html, re.S):
        name = re.search(r"data-division-name>\s*(.*?)\s*</p>", row).group(1)
        count = re.search(r"data-member-count>(\d+)</span>", row).group(1)
        context_rows[name] = int(count)

    # admin กับ staff ใน org_setup ไม่มีแผนก + Echo อยู่ในแผนกที่ถูกลบ
    assert context_rows == {
        "Division One": 3,
        "Empty Division": 0,
        "ยังไม่ได้ระบุแผนก": 3,
    }
    assert "รอเข้าสู่ระบบ 1 คน" in html
    assert "Deleted Division" not in html


def test_members_filter_by_division(app, org_setup, create_user, assign_user_to_org):
    org = org_setup["org"]
    admin = org_setup["admin"]
    division = org_setup["division"]
    deleted_division = models.Division(
        name="Deleted Division",
        organization=org,
        created_by=admin,
        last_updated_by=admin,
        status="disactive",
    ).save()

    def member(name, member_division):
        org_user = assign_user_to_org(create_user(name, "Member"), org, added_by=admin)
        org_user.division = member_division
        org_user.save()
        return org_user

    member("Inside", division)
    member("Orphan", deleted_division)

    with app.test_request_context():
        url = url_for("organizations.members.index", organization_id=str(org.id))

    with app.test_client() as client:
        _login(client, admin)
        in_division = client.get(url, query_string={"division": str(division.id)}).get_data(as_text=True)
        unassigned = client.get(url, query_string={"division": "none"}).get_data(as_text=True)
        unknown = client.get(url, query_string={"division": str(deleted_division.id)}).get_data(as_text=True)
        submitted = client.post(url, data={"division": str(division.id)})

    assert "inside@test.com" in in_division
    assert "orphan@test.com" not in in_division
    assert "staffuser@test.com" not in in_division

    assert "orphan@test.com" in unassigned
    assert "staffuser@test.com" in unassigned
    assert "inside@test.com" not in unassigned

    assert "inside@test.com" not in unknown
    assert "orphan@test.com" not in unknown

    assert f"division={division.id}" in submitted.headers["Location"]


def _division_url(app, endpoint, org, division, **kwargs):
    with app.test_request_context():
        return url_for(
            endpoint, organization_id=str(org.id), division_id=str(division.id), **kwargs
        )


def _member(create_user, assign_user_to_org, org, name, division, admin, status="active"):
    org_user = assign_user_to_org(create_user(name, "Member"), org, status=status, added_by=admin)
    org_user.division = division
    org_user.save()
    return org_user


def test_division_page_lists_all_members_and_candidates(
    app, org_setup, create_user, assign_user_to_org
):
    org, admin, division = org_setup["org"], org_setup["admin"], org_setup["division"]
    other = models.Division(
        name="Other Division", organization=org, created_by=admin, last_updated_by=admin
    ).save()
    for i in range(35):
        _member(create_user, assign_user_to_org, org, f"Inside{i}", division, admin)
    _member(create_user, assign_user_to_org, org, "Waiting", division, admin, status="pending")
    _member(create_user, assign_user_to_org, org, "Removed", division, admin, status="disactive")
    _member(create_user, assign_user_to_org, org, "Elsewhere", other, admin)

    with app.test_client() as client:
        _login(client, admin)
        response = client.get(_division_url(app, "organizations.divisions.detail", org, division))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    # แสดงทุกคนในหน้าเดียว ไม่แบ่งหน้า รวมคนที่รอเข้าสู่ระบบ
    assert "data-member-total>36<" in html
    assert "inside34@test.com" in html
    assert "removed@test.com" not in html
    # คนในแผนกอื่นเป็นตัวเลือกพร้อมชื่อแผนกเดิม
    assert 'data-from="Other Division"' in html
    assert 'data-from=""' in html  # admin/staff ที่ยังไม่มีแผนก


def test_old_division_users_url_redirects_to_division_page(app, org_setup):
    org, division = org_setup["org"], org_setup["division"]
    with app.test_client() as client:
        _login(client, org_setup["admin"])
        response = client.get(_division_url(app, "organizations.divisions.users", org, division))

    assert response.status_code == 301
    assert response.headers["Location"] == _division_url(
        app, "organizations.divisions.detail", org, division
    )


def test_add_member_moves_from_other_division_and_flashes_warning(
    app, org_setup, create_user, assign_user_to_org
):
    org, admin, division = org_setup["org"], org_setup["admin"], org_setup["division"]
    other = models.Division(
        name="Other Division", organization=org, created_by=admin, last_updated_by=admin
    ).save()
    mover = _member(create_user, assign_user_to_org, org, "Mover", other, admin)
    staff_role = org_setup["staff_role"]

    with app.test_client() as client:
        _login(client, admin)
        response = client.post(
            _division_url(app, "organizations.divisions.add_member", org, division),
            data={"members": [str(mover.id), str(staff_role.id)]},
        )
        page = client.get(response.headers["Location"]).get_data(as_text=True)

    mover.reload()
    staff_role.reload()
    assert mover.division.id == division.id
    assert staff_role.division.id == division.id
    assert "สมาชิก 1 คนถูกย้ายมาอยู่แผนก “Division One”" in page
    assert "ย้ายมาจาก Other Division" in page


def test_add_member_ignores_members_of_other_organizations(
    app, org_setup, create_org, create_user, assign_user_to_org
):
    org, admin, division = org_setup["org"], org_setup["admin"], org_setup["division"]
    outsider = assign_user_to_org(create_user("Outsider", "Member"), create_org("Other Org"), added_by=admin)

    with app.test_client() as client:
        _login(client, admin)
        client.post(
            _division_url(app, "organizations.divisions.add_member", org, division),
            data={"members": [str(outsider.id)]},
        )

    outsider.reload()
    assert outsider.division is None


def test_remove_member_from_division_requires_post_and_same_division(
    app, org_setup, create_user, assign_user_to_org
):
    org, admin, division = org_setup["org"], org_setup["admin"], org_setup["division"]
    other = models.Division(
        name="Other Division", organization=org, created_by=admin, last_updated_by=admin
    ).save()
    inside = _member(create_user, assign_user_to_org, org, "Inside", division, admin)
    elsewhere = _member(create_user, assign_user_to_org, org, "Elsewhere", other, admin)

    def remove_url(org_user):
        return _division_url(
            app, "organizations.divisions.remove_division_user", org, division,
            division_user_id=str(org_user.id),
        )

    with app.test_client() as client:
        _login(client, admin)
        assert client.get(remove_url(inside)).status_code in (302, 403, 405)
        assert client.post(remove_url(elsewhere)).status_code in (302, 404)
        assert client.post(remove_url(inside)).status_code == 302

    inside.reload()
    elsewhere.reload()
    assert inside.division is None
    assert inside.status == "active"
    assert elsewhere.division.id == other.id


def test_delete_division_requires_post(app, org_setup):
    org, division = org_setup["org"], org_setup["division"]
    url = _division_url(app, "organizations.divisions.delete", org, division)

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        assert client.get(url).status_code in (302, 403, 405)
        division.reload()
        assert division.status == "active"
        assert client.post(url).status_code == 302

    division.reload()
    assert division.status == "disactive"


def test_division_forms_are_modals(app, org_setup):
    org, division = org_setup["org"], org_setup["division"]
    with app.test_request_context():
        index_url = url_for("organizations.divisions.index", organization_id=str(org.id))
        overview_url = url_for("organizations.overview.index", organization_id=str(org.id))
        create_url = url_for("organizations.divisions.create_or_edit", organization_id=str(org.id))
        edit_url = url_for(
            "organizations.divisions.create_or_edit",
            organization_id=str(org.id),
            division_id=str(division.id),
        )
        detail_url = url_for(
            "organizations.divisions.detail", organization_id=str(org.id), division_id=str(division.id)
        )

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        index_html = client.get(index_url).get_data(as_text=True)
        overview_html = client.get(overview_url).get_data(as_text=True)
        detail_html = client.get(detail_url).get_data(as_text=True)
        # ไม่มีหน้าฟอร์มแยกแล้ว GET พากลับไปหน้าที่มี modal
        create_get = client.get(create_url)
        edit_get = client.get(edit_url)

    assert 'id="create-division"' in index_html and f'action="{create_url}"' in index_html.replace("&amp;", "&")
    assert 'id="create-division"' in overview_html
    assert 'id="edit-division"' in detail_html
    assert 'value="Division One"' in detail_html  # ฟอร์มแก้ไขมีค่าเดิม
    assert create_get.status_code == 302 and create_get.headers["Location"] == index_url
    assert edit_get.status_code == 302 and edit_get.headers["Location"] == detail_url


def test_division_form_modal_creates_and_edits(app, org_setup):
    org, division = org_setup["org"], org_setup["division"]
    with app.test_request_context():
        create_url = url_for("organizations.divisions.create_or_edit", organization_id=str(org.id))
        edit_url = url_for(
            "organizations.divisions.create_or_edit",
            organization_id=str(org.id),
            division_id=str(division.id),
        )

    with app.test_client() as client:
        _login(client, org_setup["admin"])
        created = client.post(create_url, data={"name": "Procurement", "description": "ซื้อของ"})
        client.post(edit_url, data={"name": "Division Renamed", "description": "ใหม่"})
        empty = client.post(create_url, data={"name": ""})

    new_division = models.Division.objects(name="Procurement", organization=org).first()
    assert new_division is not None
    # เพิ่มแล้วพาไปหน้าแผนกใหม่
    assert created.headers["Location"].startswith(f"/organizations/divisions/{new_division.id}/detail")
    division.reload()
    assert division.name == "Division Renamed" and division.description == "ใหม่"
    assert empty.status_code == 302
    assert models.Division.objects(name="", organization=org).count() == 0


@pytest.fixture
def empty_org(app, create_org, create_user, assign_user_to_org):
    org = create_org("Empty Org")
    admin = create_user("Emptyadmin", "Org")
    assign_user_to_org(admin, org, roles=["admin"])
    return {"org": org, "admin": admin}


def _get_html(app, user, endpoint, method="get", data=None, **kwargs):
    with app.test_request_context():
        url = url_for(endpoint, **kwargs)
    with app.test_client() as client:
        _login(client, user)
        response = getattr(client, method)(url, data=data or {})
    assert response.status_code == 200
    return response.get_data(as_text=True)


def test_divisions_index_empty_state_offers_create(app, empty_org):
    html = _get_html(
        app,
        empty_org["admin"],
        "organizations.divisions.index",
        organization_id=str(empty_org["org"].id),
    )

    assert "ยังไม่มีแผนก" in html
    assert "create-division" in html


def test_email_templates_empty_state_links_to_create(app, empty_org):
    org_id = str(empty_org["org"].id)
    with app.test_request_context():
        create_url = url_for("email_templates.create_or_edit", organization_id=org_id)

    html = _get_html(
        app, empty_org["admin"], "email_templates.index", organization_id=org_id
    )

    assert "ยังไม่มีรูปแบบอีเมล" in html
    assert create_url in html.replace("&amp;", "&")


def test_system_organizations_empty_search_offers_clear(app, create_user):
    sys_admin = create_user("Sysadmin", "Empty")
    sys_admin.roles = ["admin"]
    sys_admin.save()
    with app.test_request_context():
        index_url = url_for("organizations.system_organizations.index")

    html = _get_html(
        app,
        sys_admin,
        "organizations.system_organizations.index",
        q="ไม่มีองค์กรนี้แน่นอน",
    )

    assert "ไม่พบองค์กรที่ค้นหา" in html
    assert "ล้างการค้นหา" in html
    assert f'href="{index_url}"' in html
