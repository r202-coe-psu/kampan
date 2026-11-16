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


def test_every_car_reservation_page_has_the_profile_menu_linking_to_the_profile(app, world, login_as):
    org, user = world
    with app.test_client() as client:
        login_as(client, user)
        page = client.get(f"/car_reservation/requests/?organization_id={org.id}")
    body = page.data.decode()
    assert 'data-role="profile-menu"' in body
    assert f"/car_reservation/profile?organization_id={org.id}" in body


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
