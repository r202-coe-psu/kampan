"""หน้าโปรไฟล์ในระบบจองรถ และเมนูโปรไฟล์ที่แถบบน"""

import pytest

from kampan import models


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Profile Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()
    user = create_user("Prof", "Ile")
    assign_user_to_org(user, org, roles=["staff"])
    return org, user


def test_profile_page_shows_name_roles_and_request_counts(app, world, login_as):
    org, user = world
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/profile?organization_id={org.id}")
    body = page.data.decode()
    assert page.status_code == 200
    assert user.email in body
    assert 'data-role="role-badges"' in body
    assert 'data-role="request-summary"' in body


def test_sidebar_user_block_links_to_the_profile_and_there_is_no_topbar(app, world, login_as):
    org, user = world
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/requests/?organization_id={org.id}")
    body = page.data.decode()
    assert 'data-role="topbar"' not in body
    assert 'data-role="profile-menu"' not in body
    assert (
        f'data-role="sidebar-profile" href="/car_reservation/profile?organization_id={org.id}"'
        in body
    )


def test_profile_page_requires_membership(app, world, create_user, login_as):
    org, _ = world
    outsider = create_user("Out", "Sider")
    with app.test_client() as client:
        login_as(client, outsider)
        page = client.get(f"/car_reservation/profile?organization_id={org.id}")
    assert page.status_code in (302, 403)


def test_request_detail_has_a_preview_button_and_modal_pointing_at_the_paper_pdf(
    app, world, login_as, create_car
):
    org, user = world
    reservation = models.CarReservation(
        organization=org, creator=user, request_type="domestic",
        request_reason="ทดสอบ", status="pending",
    ).save()
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/requests/{reservation.id}?organization_id={org.id}")
    body = page.data.decode()
    assert page.status_code == 200
    assert 'data-role="preview-paper"' in body
    assert f"/requests/{reservation.id}/paper" in body


def switcher_links(body):
    from lxml import html as lxml_html

    doc = lxml_html.fromstring(body)
    return doc.xpath("//dialog[@id='organization_switcher_modal']//a/@href")


def test_switching_organization_from_car_reservation_stays_in_car_reservation(
    app, world, create_org, assign_user_to_org, login_as
):
    from urllib.parse import parse_qs, urlparse

    org, user = world
    other = create_org("Other Car Org")
    other.enabled_modules = ["car_reservation"]
    other.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    other.save()
    assign_user_to_org(user, other, roles=["staff"])
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/requests/?organization_id={org.id}")
    nexts = [parse_qs(urlparse(h).query).get("next", [""])[0] for h in switcher_links(page.data.decode())]
    assert nexts and all(n.startswith("/car_reservation/calendar") for n in nexts)


def test_switching_to_an_organization_without_car_reservation_goes_to_the_system_picker(
    app, world, create_org, assign_user_to_org, login_as
):
    from urllib.parse import parse_qs, urlparse

    org, user = world
    other = create_org("No Car Org")
    other.enabled_modules = ["inventory"]
    other.save()
    assign_user_to_org(user, other, roles=["staff"])
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/requests/?organization_id={org.id}")
    links = {
        parse_qs(urlparse(h).query)["organization_id"][0]: parse_qs(urlparse(h).query).get("next")
        for h in switcher_links(page.data.decode())
    }
    assert links[str(other.id)] is None
