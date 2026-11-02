"""ผลของการสร้าง/แก้ไข/ลบในระบบจัดการองค์กรต้องแจ้งผู้ใช้ผ่าน flash

success / error แสดงเป็น toast ที่หายเอง ส่วน warning (ย้ายสมาชิกข้ามแผนก)
ยังเป็น modal ที่ผู้ใช้ต้องกดรับทราบ
"""

import pytest
from flask import url_for

from kampan import models


@pytest.fixture
def setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("Flash Org")
    global_admin = create_user("Globaladmin", "Flash", roles=["admin"])
    admin = create_user("Orgadmin", "Flash")
    assign_user_to_org(admin, org, roles=["admin"])
    member = create_user("Somchai", "Member")
    member_role = assign_user_to_org(member, org, roles=["staff"], added_by=admin)
    division = models.Division(
        name="Finance",
        organization=org,
        created_by=admin,
        last_updated_by=admin,
        status="active",
    ).save()
    return {
        "org": org,
        "global_admin": global_admin,
        "admin": admin,
        "member": member,
        "member_role": member_role,
        "division": division,
    }


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _post_and_follow(app, login_as, user, url, data=None):
    with app.test_client() as client:
        login_as(client, user)
        response = client.post(url, data=data or {}, follow_redirects=True)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _assert_toast(html, message, tone="alert-success"):
    assert message in html
    toast = html[html.index('class="toast') :]
    assert message in toast
    assert "data-toast" in toast
    assert tone in toast


def test_create_division_shows_toast(app, login_as, setup):
    url = _url(
        app, "organizations.divisions.create_or_edit", organization_id=str(setup["org"].id)
    )
    html = _post_and_follow(
        app, login_as, setup["admin"], url, {"name": "Procurement", "description": "x"}
    )

    _assert_toast(html, "เพิ่มแผนก Procurement แล้ว")


def test_edit_division_shows_toast(app, login_as, setup):
    division = setup["division"]
    url = _url(
        app,
        "organizations.divisions.create_or_edit",
        organization_id=str(setup["org"].id),
        division_id=str(division.id),
    )
    html = _post_and_follow(
        app, login_as, setup["admin"], url, {"name": "Finance 2", "description": "x"}
    )

    _assert_toast(html, "บันทึกแผนก Finance 2 แล้ว")


def test_invalid_division_form_does_not_flash(app, login_as, setup):
    url = _url(
        app, "organizations.divisions.create_or_edit", organization_id=str(setup["org"].id)
    )
    html = _post_and_follow(app, login_as, setup["admin"], url, {"name": ""})

    assert "data-toast" not in html


def test_delete_division_shows_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.divisions.delete",
        organization_id=str(setup["org"].id),
        division_id=str(setup["division"].id),
    )
    html = _post_and_follow(app, login_as, setup["admin"], url)

    _assert_toast(html, "ลบแผนก Finance แล้ว")


def test_remove_member_from_division_shows_toast(app, login_as, setup):
    member_role = setup["member_role"]
    member_role.division = setup["division"]
    member_role.save()
    url = _url(
        app,
        "organizations.divisions.remove_division_user",
        organization_id=str(setup["org"].id),
        division_id=str(setup["division"].id),
        division_user_id=str(member_role.id),
    )
    html = _post_and_follow(app, login_as, setup["admin"], url)

    _assert_toast(html, "นำ Somchai Member ออกจากแผนก Finance แล้ว")


def test_add_member_to_division_shows_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.divisions.add_member",
        organization_id=str(setup["org"].id),
        division_id=str(setup["division"].id),
    )
    html = _post_and_follow(
        app, login_as, setup["admin"], url, {"members": [str(setup["member_role"].id)]}
    )

    _assert_toast(html, "เพิ่มสมาชิก 1 คนเข้าแผนก Finance แล้ว")


def test_add_member_to_division_without_selection_shows_error_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.divisions.add_member",
        organization_id=str(setup["org"].id),
        division_id=str(setup["division"].id),
    )
    html = _post_and_follow(app, login_as, setup["admin"], url, {})

    _assert_toast(html, "ไม่มีสมาชิกที่เพิ่มเข้าแผนก Finance ได้", tone="alert-error")


def test_moved_member_warning_stays_a_modal(app, login_as, setup, create_user, assign_user_to_org):
    other = models.Division(
        name="Legal",
        organization=setup["org"],
        created_by=setup["admin"],
        last_updated_by=setup["admin"],
        status="active",
    ).save()
    member_role = setup["member_role"]
    member_role.division = other
    member_role.save()
    url = _url(
        app,
        "organizations.divisions.add_member",
        organization_id=str(setup["org"].id),
        division_id=str(setup["division"].id),
    )
    html = _post_and_follow(
        app, login_as, setup["admin"], url, {"members": [str(member_role.id)]}
    )

    warning = "สมาชิก 1 คนถูกย้ายมาอยู่แผนก “Finance”"
    assert warning in html
    # แต่ละคนเป็นรายการแยก พร้อมแผนกเดิม
    assert "Somchai Member" in html[html.index(warning):]
    assert "ย้ายมาจาก Legal" in html[html.index(warning):]
    # ข้อความ warning อยู่ใน <dialog> ที่เปิดเอง ไม่ใช่ใน toast
    dialog_start = html.rindex("<dialog", 0, html.index(warning))
    assert "</dialog>" not in html[dialog_start : html.index(warning)]
    assert "modal-open" in html[dialog_start:] or ".showModal()" in html[dialog_start:]
    # ส่วนข้อความ success ของการเพิ่มสมาชิกเป็น toast
    assert "เพิ่มสมาชิก 1 คนเข้าแผนก Finance แล้ว" in html
    toast_start = html.index('class="toast')
    assert html.index("เพิ่มสมาชิก 1 คนเข้าแผนก Finance แล้ว") > toast_start
    assert warning not in html[toast_start:]


def test_edit_member_roles_shows_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.members.edit_roles",
        organization_id=str(setup["org"].id),
        org_user_id=str(setup["member_role"].id),
    )
    html = _post_and_follow(
        app,
        login_as,
        setup["admin"],
        url,
        {
            "first_name": "Somchai",
            "last_name": "Member",
            "email": "somchai@test.com",
            "appointment": "Clerk",
            "roles": ["staff"],
        },
    )

    _assert_toast(html, "บันทึกตำแหน่งของ Somchai Member แล้ว")


def test_remove_member_from_organization_shows_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.members.remove_org_user",
        organization_id=str(setup["org"].id),
        org_user_id=str(setup["member_role"].id),
    )
    html = _post_and_follow(app, login_as, setup["admin"], url)

    _assert_toast(html, "นำ Somchai Member ออกจากองค์กรแล้ว")


def test_delete_organization_as_global_admin_shows_toast(app, login_as, setup):
    url = _url(
        app,
        "organizations.system_organizations.delete",
        organization_id=str(setup["org"].id),
    )
    with app.test_client() as client:
        login_as(client, setup["global_admin"])
        response = client.post(url, follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    _assert_toast(html, "ลบองค์กร Flash Org แล้ว")


def test_create_organization_as_global_admin_shows_toast(app, login_as, setup):
    url = _url(app, "organizations.system_organizations.create_or_edit")
    html = _post_and_follow(
        app, login_as, setup["global_admin"], url, {"name": "Brand New Org"}
    )

    _assert_toast(html, "เพิ่มองค์กร Brand New Org แล้ว")


def test_edit_user_roles_shows_toast(app, login_as, setup):
    member = setup["member"]
    url = _url(app, "organizations.system_users.edit_roles", user_id=str(member.id))
    html = _post_and_follow(
        app,
        login_as,
        setup["global_admin"],
        url,
        {
            "first_name": member.first_name,
            "last_name": member.last_name,
            "email": member.email,
            "roles": ["staff"],
        },
    )

    _assert_toast(html, "บันทึกระดับผู้ใช้ของ Somchai Member แล้ว")
