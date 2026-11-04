"""การมองเห็น MA (#31): กลุ่มเห็นทั้งหน่วยงาน, ผู้รับผิดชอบเห็นของตัวเอง และ "เฉพาะฝ่ายของฉัน"

ทดสอบผ่าน HTTP ทุกหน้าที่แสดง MA (หน้ารายการ MA, รายการ MA ต่ออายุ, รายการไม่ต่ออายุ)
และหน้ารายละเอียดของ MA ที่มองไม่เห็นต้องได้ 404

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models

MA_A = "[TEST] MA-แอลฟา"
MA_B = "[TEST] MA-บราโว"
MA_MIXED = "[TEST] MA-ผสม"
MA_OTHER_ORG = "[TEST] MA-หน่วยงานอื่น"
ALL_MAS = {MA_A, MA_B, MA_MIXED}

# MA ทุกตัวอยู่ในสถานะ disactive เพื่อให้ขึ้นในหน้ารายการไม่ต่ออายุด้วย (อีก 2 หน้าไม่กรองสถานะ)
LIST_PAGES = {
    "products": "/procurement/products",
    "renewal": "/procurement/requisitions?expiration_date_range=",
    "non_renewal": "/procurement/requisitions/non-renewal",
}


def _item(name, amount, responsible):
    now = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return models.ProcurementItem(
        name=name,
        category="service",
        amount=Decimal(amount),
        start_date=now - datetime.timedelta(days=300),
        end_date=now + datetime.timedelta(days=30),
        responsible_by=list(responsible),
        installments=[models.Installment(due_date=now + datetime.timedelta(days=30))],
    )


def _ma(organization, creator, name, items, status="disactive"):
    procurement = models.Procurement(
        psu_disbursement_number=f"PSU-{name}",
        name=name,
        company="[TEST] บริษัท",
        organization=organization,
        status=status,
        total_amount=sum((item.amount for item in items), Decimal("0")),
        created_by=creator,
    )
    procurement.save_with_items(items)
    return procurement


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org")
    other_org = create_org("[TEST] Org อื่น")
    division_a = models.Division(name="[TEST] ฝ่ายหนึ่ง", organization=org).save()
    division_b = models.Division(name="[TEST] ฝ่ายสอง", organization=org).save()

    def member(first_name, roles, division=None, organization=org):
        user = create_user(first_name, "Viewer")
        role = assign_user_to_org(user, organization, roles=roles)
        role.first_name = first_name
        role.division = division
        role.save()
        return user, role

    admin, role_admin = member("Admin", ["admin"], division_a)
    head_a, role_head_a = member("HeadA", ["head"], division_a)
    manager, role_manager = member("Manager", ["manager"], division_b)
    supervisor, role_supervisor = member("Supervisor", ["staff", "supervisor supplier"], division_b)
    director, role_director = member("Director", ["director"])
    staff_a, role_staff_a = member("StaffA", ["staff"], division_a)
    staff_b, role_staff_b = member("StaffB", ["staff"], division_b)
    staff_none, role_staff_none = member("StaffNone", ["staff"], division_a)
    endorser, role_endorser = member("Endorser", ["endorser"], division_a)
    admin_other, role_admin_other = member("AdminOther", ["admin"], organization=other_org)

    ma_a = _ma(org, admin, MA_A, [_item("[TEST] รายการ a", "100.00", [role_staff_a])])
    ma_b = _ma(org, admin, MA_B, [_item("[TEST] รายการ b", "100.00", [role_staff_b])])
    ma_mixed = _ma(
        org,
        admin,
        MA_MIXED,
        [_item("[TEST] รายการผสม a", "60.00", [role_staff_a]), _item("[TEST] รายการผสม b", "40.00", [role_staff_b])],
    )
    ma_other = _ma(other_org, admin_other, MA_OTHER_ORG, [_item("[TEST] รายการ x", "100.00", [])])
    return SimpleNamespace(**locals())


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        return login_as(app.test_client(), user)

    return _client_for


def _url(path, organization, **params):
    query = "&".join([f"organization_id={organization.id}"] + [f"{key}={value}" for key, value in params.items()])
    return f"{path}{'&' if '?' in path else '?'}{query}"


def _visible_names(client, page, organization, **params):
    if page == "renewal":
        models.Procurement.objects(organization=organization).update(set__status="renewal-requested")
    elif page == "non_renewal":
        models.Procurement.objects(organization=organization).update(set__status="disactive")
    else:
        models.Procurement.objects(organization=organization).update(set__status="active")
    response = client.get(_url(LIST_PAGES[page], organization, **params))
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    return {name for name in ALL_MAS | {MA_OTHER_ORG} if name in html}


@pytest.mark.parametrize("page", LIST_PAGES)
@pytest.mark.parametrize(
    "who, expected",
    [
        ("admin", ALL_MAS),
        ("head_a", ALL_MAS),
        ("manager", ALL_MAS),
        ("supervisor", ALL_MAS),
        ("director", ALL_MAS),
        ("staff_a", {MA_A, MA_MIXED}),
        ("staff_b", {MA_B, MA_MIXED}),
        ("staff_none", set()),
        ("endorser", set()),
    ],
)
def test_list_pages_follow_visibility_rule(world, client_for, page, who, expected):
    names = _visible_names(client_for(getattr(world, who)), page, world.org)

    assert names == expected


@pytest.mark.parametrize("page", LIST_PAGES)
@pytest.mark.parametrize(
    "who, expected",
    [
        ("head_a", {MA_A, MA_MIXED}),
        ("admin", {MA_A, MA_MIXED}),
        ("supervisor", {MA_B, MA_MIXED}),
        ("manager", {MA_B, MA_MIXED}),
        # ไม่มีฝ่าย: checkbox ไม่มีผล
        ("director", ALL_MAS),
        # ไม่ใช่กลุ่มเห็นทั้งหน่วยงาน: ไม่มีผล
        ("staff_a", {MA_A, MA_MIXED}),
        ("staff_none", set()),
    ],
)
def test_only_my_division_filter(world, client_for, page, who, expected):
    names = _visible_names(client_for(getattr(world, who)), page, world.org, division="mine")

    assert names == expected


@pytest.mark.parametrize("page", LIST_PAGES)
@pytest.mark.parametrize("who, shown", [("head_a", True), ("manager", True), ("director", False), ("staff_a", False)])
def test_my_division_checkbox_only_for_privileged_users_with_division(world, client_for, page, who, shown):
    html = client_for(getattr(world, who)).get(_url(LIST_PAGES[page], world.org)).get_data(as_text=True)

    assert ('name="division" value="mine"' in html) is shown
    if shown:
        assert "เฉพาะฝ่ายของฉัน" in html


def test_my_division_checkbox_keeps_checked_state(world, client_for):
    html = client_for(world.head_a).get(_url(LIST_PAGES["products"], world.org, division="mine")).get_data(as_text=True)

    assert 'name="division" value="mine" checked' in html


def _detail(world, procurement):
    return f"/procurement/payment/{procurement.id}?organization_id={world.org.id}"


@pytest.mark.parametrize(
    "who, ma, status",
    [
        ("staff_a", "ma_a", 200),
        ("staff_a", "ma_mixed", 200),
        ("staff_a", "ma_b", 404),
        ("staff_none", "ma_a", 404),
        ("endorser", "ma_a", 404),
        ("director", "ma_b", 200),
        ("head_a", "ma_b", 200),
    ],
)
def test_detail_page_404_for_ma_user_cannot_see(world, client_for, who, ma, status):
    response = client_for(getattr(world, who)).get(_detail(world, getattr(world, ma)))

    assert response.status_code == status


def test_staff_creator_sees_own_ma_without_being_responsible(world, client_for):
    own = _ma(world.org, world.staff_none, "[TEST] MA-ที่ฉันสร้าง", [_item("[TEST] รายการ c", "10.00", [])])
    client = client_for(world.staff_none)

    assert client.get(_detail(world, own)).status_code == 200
    assert "[TEST] MA-ที่ฉันสร้าง" in client.get(_url(LIST_PAGES["products"], world.org)).get_data(as_text=True)


@pytest.mark.parametrize(
    "path",
    [
        "/procurement/payment/{id}",
        "/procurement/products/{id}/edit",
    ],
)
def test_per_ma_pages_404_for_ma_user_cannot_see(world, client_for, path):
    response = client_for(world.staff_none).get(_url(path.format(id=world.ma_b.id), world.org))

    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/procurement/payment/{id}", "/procurement/products/{id}/edit"])
def test_other_org_ma_is_404_even_for_admin(world, client_for, path):
    client = client_for(world.admin)

    assert client.get(_url(path.format(id=world.ma_other.id), world.org)).status_code == 404
    assert client.get(_url(path.format(id="not-an-id"), world.org)).status_code == 404


@pytest.mark.parametrize("page", LIST_PAGES)
def test_other_org_admin_sees_only_own_org(world, client_for, page):
    names = _visible_names(client_for(world.admin_other), page, world.other_org)

    assert names == {MA_OTHER_ORG}


def test_non_renewal_action_on_invisible_ma_is_404(world, client_for):
    world.ma_b.update(set__status="pending")

    response = client_for(world.staff_none).post(_url(f"/procurement/requisitions/{world.ma_b.id}/non-renewal", world.org))

    assert response.status_code == 404
    world.ma_b.reload()
    assert world.ma_b.status == "pending"


@pytest.mark.parametrize("page", LIST_PAGES)
def test_list_pages_show_responsible_division_names(world, client_for, page):
    if page == "renewal":
        models.Procurement.objects(organization=world.org).update(set__status="renewal-requested")
    elif page == "non_renewal":
        models.Procurement.objects(organization=world.org).update(set__status="disactive")
    else:
        models.Procurement.objects(organization=world.org).update(set__status="active")
    response = client_for(world.admin).get(_url(LIST_PAGES[page], world.org))

    html = response.get_data(as_text=True)
    assert "[TEST] ฝ่ายหนึ่ง" in html and "[TEST] ฝ่ายสอง" in html
