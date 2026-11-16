"""ผู้ดูแลองค์กรให้ role แก่สมาชิกได้เฉพาะ role ที่องค์กรเปิดใช้ และคนขับรถเป็นผู้อนุมัติไม่ได้"""

import pytest
from flask import url_for

from kampan import models

DRIVER_CANNOT_APPROVE = "พนักงานขับรถเป็นผู้อนุมัติไม่ได้"


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("Member Role Org")
    org.enabled_roles = ["staff", "admin", "driver", "dispatcher"]
    org.save()
    admin = create_user("Admin", "Members")
    assign_user_to_org(admin, org, roles=["admin"])
    candidate = create_user("Candidate", "Members")
    member = create_user("Member", "Members")
    member_role = assign_user_to_org(member, org, roles=["staff"])
    client = login_as(app.test_client(), admin)

    class World:
        pass

    w = World()
    w.org, w.client, w.candidate, w.member, w.member_role = (
        org,
        client,
        candidate,
        member,
        member_role,
    )
    with app.test_request_context():
        w.add_url = url_for("organizations.members.add_member", organization_id=org.id)
        w.edit_url = url_for(
            "organizations.members.edit_roles",
            organization_id=org.id,
            org_user_id=member_role.id,
        )
    return w


def _add(world, roles):
    return world.client.post(
        world.add_url,
        data={"members": str(world.candidate.id), "roles": roles, "division": ""},
    )


def _edit(world, roles):
    return world.client.post(
        world.edit_url,
        data={
            "first_name": "Member",
            "last_name": "Members",
            "email": "member@test.com",
            "appointment": "",
            "roles": roles,
        },
    )


def _candidate_membership(world):
    return models.OrganizationUserRole.objects(
        organization=world.org, user=world.candidate
    ).first()


def test_add_member_page_offers_only_the_roles_enabled_for_the_organization(world):
    html = world.client.get(world.add_url).get_data(as_text=True)

    assert "ผู้จัดรถ" in html
    assert "อธิการบดี" not in html
    assert "ผู้มีสิทธิ์อนุมัติ" not in html


def test_add_member_with_an_enabled_approval_role_is_saved(world):
    response = _add(world, ["dispatcher"])

    assert response.status_code == 302
    assert _candidate_membership(world).roles == ["dispatcher"]


def test_add_member_with_a_role_not_enabled_for_the_organization_is_refused(world):
    response = _add(world, ["president"])

    assert response.status_code == 200
    assert _candidate_membership(world) is None


def test_add_member_cannot_be_both_driver_and_approver(world):
    response = _add(world, ["driver", "dispatcher"])

    assert response.status_code == 200
    assert DRIVER_CANNOT_APPROVE in response.get_data(as_text=True)
    assert _candidate_membership(world) is None


def test_edit_roles_with_a_role_not_enabled_for_the_organization_is_refused(world):
    response = _edit(world, ["staff", "president"])

    assert response.status_code == 200
    world.member_role.reload()
    assert world.member_role.roles == ["staff"]


def test_edit_roles_cannot_make_a_driver_an_approver(world):
    world.member_role.roles = ["driver"]
    world.member_role.save()

    response = _edit(world, ["driver", "dispatcher"])

    assert response.status_code == 200
    assert DRIVER_CANNOT_APPROVE in response.get_data(as_text=True)
    world.member_role.reload()
    assert world.member_role.roles == ["driver"]


def test_edit_roles_keeps_a_role_the_organization_has_since_disabled(world):
    world.member_role.roles = ["staff", "president"]
    world.member_role.save()

    response = _edit(world, ["staff", "president", "admin"])

    assert response.status_code == 302
    world.member_role.reload()
    assert sorted(world.member_role.roles) == ["admin", "president", "staff"]


def _toasts(html):
    import re

    return re.findall(r'<div[^>]*data-toast[^>]*data-toast-category="(\w+)"[^>]*>(.*?)</div>', html, re.S)


def test_edit_roles_success_shows_a_success_toast_on_the_members_page(world):
    response = _edit(world, ["staff", "admin"])

    page = world.client.get(response.headers["Location"]).get_data(as_text=True)
    assert [category for category, _ in _toasts(page)] == ["success"]
    assert "บันทึกตำแหน่งของ" in page


def test_edit_roles_refused_shows_an_error_toast_with_the_reason(world):
    response = _edit(world, ["driver", "dispatcher"])

    toasts = _toasts(response.get_data(as_text=True))
    assert [category for category, _ in toasts] == ["error"]
    assert DRIVER_CANNOT_APPROVE in toasts[0][1]
