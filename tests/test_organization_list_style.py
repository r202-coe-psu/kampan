"""ตารางในระบบจัดการองค์กรใช้หน้าตาเดียวกับระบบจองรถ: หัวการ์ดมีจำนวนรวม,
ตารางบนจอกลางขึ้นไป + การ์ดบนมือถือ, EmptyState เมื่อไม่มีข้อมูล, ป้าย role ภาษาไทย"""

import re

import pytest
from flask import url_for

from kampan import models
from kampan.models.organizations import ORGANIZATION_ROLES


def _division(org, admin, name):
    return models.Division(
        name=name, organization=org, created_by=admin, last_updated_by=admin, status="active"
    ).save()


def _put_in_division(org_user, division):
    org_user.division = division
    org_user.save()


@pytest.fixture
def filled(app, create_org, create_user, assign_user_to_org):
    """ผู้ดูแลระบบส่วนกลาง + 2 องค์กร; องค์กรแรกมีสมาชิก 2 คน แผนก 2 แผนก"""
    sys_admin = create_user("Sysadmin", "List", roles=["admin"])
    org = create_org("Alpha Org")
    create_org("Beta Org")
    member_a = create_user("Membera", "List")
    member_b = create_user("Memberb", "List")
    role_a = assign_user_to_org(member_a, org, roles=["admin", "supervisor supplier"], added_by=sys_admin)
    assign_user_to_org(member_b, org, roles=["staff"], added_by=sys_admin)
    division_one = _division(org, sys_admin, "Division One")
    _division(org, sys_admin, "Division Two")
    _put_in_division(role_a, division_one)
    return {"admin": sys_admin, "org": org, "division": division_one}


@pytest.fixture
def blank(app, create_org, create_user):
    """องค์กรที่ยังไม่มีสมาชิกหรือแผนกเลย + ผู้ดูแลระบบส่วนกลางที่ไม่ได้สังกัดองค์กร"""
    return {
        "admin": create_user("Sysadmin", "Blank", roles=["admin"]),
        "org": create_org("Blank Org"),
    }


def _url(app, endpoint, **kwargs):
    with app.test_request_context():
        return url_for(endpoint, **kwargs)


def _page(app, login_as, user, url):
    with app.test_client() as client:
        login_as(client, user)
        response = client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _list_pages(app, s):
    """ชื่อหน้า -> (url, จำนวนรายการ, ข้อความของรายการที่ต้องอยู่ในการ์ดมือถือด้วย)"""
    org_id = str(s["org"].id)
    division_id = str(s["division"].id)
    return {
        "system_organizations": (
            _url(app, "organizations.system_organizations.index"), 2, "Beta Org"),
        "members": (
            _url(app, "organizations.members.index", organization_id=org_id), 2, "memberb@test.com"),
        "divisions": (
            _url(app, "organizations.divisions.index", organization_id=org_id), 2, "Division Two"),
        "overview": (
            _url(app, "organizations.overview.index", organization_id=org_id), 3, "Division Two"),
        "division_detail": (
            _url(app, "organizations.divisions.detail", organization_id=org_id, division_id=division_id),
            1, "membera@test.com"),
    }


PAGE_NAMES = ["system_organizations", "members", "divisions", "overview", "division_detail"]


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_list_header_shows_total_count(app, login_as, filled, page):
    url, total, _ = _list_pages(app, filled)[page]

    html = _page(app, login_as, filled["admin"], url)

    # data-member-total ห่อตัวเลขด้วย span จึงเทียบข้อความหลังตัด tag
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))
    assert f"ทั้งหมด {total} รายการ" in text


@pytest.mark.parametrize("page", PAGE_NAMES)
def test_list_has_table_and_mobile_cards(app, login_as, filled, page):
    url, _, sample = _list_pages(app, filled)[page]

    html = _page(app, login_as, filled["admin"], url)

    table_at = html.index("data-table-view")
    cards_at = html.index("data-mobile-list")
    table_tag = html[html.rindex("<", 0, table_at):html.index(">", table_at)]
    cards_tag = html[html.rindex("<", 0, cards_at):html.index(">", cards_at)]
    assert "hidden md:block" in table_tag
    assert "md:hidden" in cards_tag
    assert sample in html[cards_at:], "รายการต้องปรากฏในการ์ดมือถือด้วย"


EMPTY_PAGES = {
    "system_organizations": ("ไม่พบองค์กรที่ค้นหา", None),
    "members": ("ยังไม่มีสมาชิกในองค์กร", "organizations.members.index"),
    "divisions": ("ยังไม่มีแผนก", "organizations.divisions.index"),
    "overview": ("ยังไม่มีแผนกและสมาชิกในองค์กรนี้", "organizations.overview.index"),
}


@pytest.mark.parametrize("page", list(EMPTY_PAGES))
def test_empty_list_shows_empty_state(app, login_as, blank, page):
    text, endpoint = EMPTY_PAGES[page]
    if endpoint is None:
        url = _url(app, "organizations.system_organizations.index", q="zzz-no-such-org")
    else:
        url = _url(app, endpoint, organization_id=str(blank["org"].id))

    html = _page(app, login_as, blank["admin"], url)

    assert text in html
    assert 'role="status"' in html
    assert "data-table-view" not in html


def test_division_detail_empty_list_shows_empty_state(app, login_as, blank):
    division = _division(blank["org"], blank["admin"], "Lonely Division")
    url = _url(
        app, "organizations.divisions.detail",
        organization_id=str(blank["org"].id), division_id=str(division.id),
    )

    html = _page(app, login_as, blank["admin"], url)

    assert "ยังไม่มีสมาชิกในแผนกนี้" in html
    assert "data-table-view" not in html


def test_member_list_shows_roles_as_thai_badges(app, login_as, filled):
    url = _list_pages(app, filled)["members"][0]
    labels = dict(ORGANIZATION_ROLES)

    html = _page(app, login_as, filled["admin"], url)

    for role in ("admin", "supervisor supplier", "staff"):
        assert f"role-badge role-{role.replace(' ', '-')}" in html
        assert f">{labels[role]}</span>" in html
    # ทั้งตารางและการ์ดมือถือต้องมีป้ายของสมาชิกที่มีสองตำแหน่ง
    assert html.count(f">{labels['supervisor supplier']}</span>") >= 2
