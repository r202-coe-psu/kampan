import re

import pytest
from flask import url_for

from kampan import models

# (endpoint, needs_division, needs_org_user)
ADMIN_ONLY_ROUTES = [
    ("organizations.divisions.index", False, False),
    ("organizations.divisions.create_or_edit", False, False),
    ("organizations.divisions.create_or_edit", True, False),
    ("organizations.divisions.detail", True, False),
    ("organizations.divisions.add_member", True, False),
    ("organizations.divisions.users", True, False),
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
