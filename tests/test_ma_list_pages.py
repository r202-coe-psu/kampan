"""หน้ารายการ MA ทั้ง 3 หน้า: จำนวน query คงที่, การแบ่งหน้า (clamp page / จำกัด per_page) และตัวนับสถานะ

นับ query ด้วยการครอบ ``find`` / ``aggregate`` / ``count_documents`` ของ mongomock
(mongomock ไม่ส่ง event ของ pymongo monitoring) ทุก query ของ mongoengine รวมถึงการ dereference
ReferenceField ผ่านเมธอดเหล่านี้ทั้งหมด

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
import re
from collections import Counter
from decimal import Decimal
from types import SimpleNamespace

import mongomock
import pytest

from kampan import models

PRODUCTS = "/procurement/products"
RENEWAL = "/procurement/requisitions"
NON_RENEWAL = "/procurement/requisitions/non-renewal"
LIST_PAGES = [PRODUCTS, RENEWAL, NON_RENEWAL]

TODAY = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def query_counter(monkeypatch):
    counts = Counter()
    for method_name in ("find", "aggregate", "count_documents"):
        original = getattr(mongomock.collection.Collection, method_name)

        def counted(self, *args, _original=original, **kwargs):
            counts[self.name] += 1
            return _original(self, *args, **kwargs)

        monkeypatch.setattr(mongomock.collection.Collection, method_name, counted)
    return counts


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("[TEST] Org")
    admin = create_user("Admin", "Lister")
    admin_role = assign_user_to_org(admin, org, roles=["admin"])
    division = models.Division(name="[TEST] ฝ่ายแอดมิน", organization=org).save()
    admin_role.division = division
    admin_role.save()
    state = SimpleNamespace(org=org, admin=admin, admin_role=admin_role, division=division, count=0)

    def client():
        return login_as(app.test_client(), admin)

    state.client = client
    return state


def _add_member(world, index):
    """ผู้รับผิดชอบคนใหม่ (ผู้ใช้และฝ่ายของตัวเอง) ให้แต่ละ MA อ้างถึงเอกสารคนละชุด"""
    user = models.User(
        first_name=f"Owner{index}",
        last_name="Test",
        email=f"owner{index}@test.com",
        username=f"owner_{index}",
    ).save()
    division = models.Division(name=f"[TEST] ฝ่าย {index}", organization=world.org).save()
    return models.OrganizationUserRole(
        user=user,
        organization=world.org,
        roles=["staff"],
        status="active",
        added_by=world.admin,
        last_modifier=world.admin,
        division=division,
    ).save()


def _installment(due_in_days, paid=False, paid_by=None):
    return models.Installment(
        due_date=TODAY + datetime.timedelta(days=due_in_days),
        paid_date=TODAY if paid else None,
        paid_by=paid_by if paid else None,
    )


def _item(index, member, end_in_days, installments):
    return models.ProcurementItem(
        name=f"[TEST] รายการ {index}",
        category="service",
        amount=Decimal("100.00"),
        start_date=TODAY - datetime.timedelta(days=300),
        end_date=TODAY + datetime.timedelta(days=end_in_days),
        responsible_by=[member],
        installments=installments,
    )


def _create_ma(world, end_in_days=30, installments=None, items=None, status="active", responsible=None):
    """MA 1 ตัว: ``items`` เป็นรายการ (end_in_days, installments) ถ้าไม่ให้มีรายการย่อยเดียว
    created_date เพิ่มทีละวินาทีตามลำดับที่สร้าง (หน้ารายการ MA เรียงใหม่สุดก่อน)"""
    world.count += 1
    index = world.count
    member = responsible if responsible is not None else _add_member(world, index)
    if items is None:
        default_installments = [_installment(-10, paid=True, paid_by=world.admin), _installment(end_in_days)]
        items = [(end_in_days, installments or default_installments)]
    procurement_items = [_item(index, member, days, item_installments) for days, item_installments in items]
    procurement = models.Procurement(
        psu_disbursement_number=f"PSU-{index:04d}",
        name=f"[TEST] MA-{index:04d}",
        company="[TEST] บริษัท",
        organization=world.org,
        status=status,
        total_amount=Decimal("100.00") * len(procurement_items),
        created_by=world.admin,
        created_date=TODAY + datetime.timedelta(seconds=index),
    )
    procurement.save_with_items(procurement_items)
    return procurement


def _create_mas(world, count, **kwargs):
    return [_create_ma(world, **kwargs) for _ in range(count)]


def _url(path, organization, **params):
    query = "&".join([f"organization_id={organization.id}"] + [f"{key}={value}" for key, value in params.items()])
    return f"{path}{'&' if '?' in path else '?'}{query}"


def _get(world, path, **params):
    return world.client().get(_url(path, world.org, **params))


def _query_count(world, query_counter, path):
    query_counter.clear()
    response = _get(world, path)
    assert response.status_code == 200
    return sum(query_counter.values())


# ---------------------------------------------------------------------------
# จำนวน query ไม่ขึ้นกับจำนวน MA
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", LIST_PAGES)
def test_list_page_query_count_does_not_grow_with_ma_count(world, query_counter, path):
    status = "disactive" if path == NON_RENEWAL else "active"
    _create_mas(world, 3, status=status)
    few = _query_count(world, query_counter, path)

    _create_mas(world, 40, status=status)
    many = _query_count(world, query_counter, path)

    assert many == few, f"{path}: {few} queries with 3 MAs, {many} with 43 MAs"


# ---------------------------------------------------------------------------
# แบ่งหน้า: clamp page และจำกัด per_page
# ---------------------------------------------------------------------------


def _shown_mas(response) -> list[str]:
    """ชื่อ MA ในหน้า ตามลำดับที่แสดงครั้งแรก"""
    names = []
    for name in re.findall(r"\[TEST\] MA-\d{4}", response.get_data(as_text=True)):
        if name not in names:
            names.append(name)
    return names


def _ma_names(procurements) -> list[str]:
    return [procurement.name for procurement in procurements]


def _five_mas_for(world, path):
    """MA 5 ตัว วันสิ้นสุดห่างกันทีละวัน คืนชื่อตามลำดับที่หน้านั้นแสดง"""
    status = "disactive" if path == NON_RENEWAL else "active"
    mas = _ma_names(_create_ma(world, end_in_days=10 + index, status=status) for index in range(5))
    if path == RENEWAL:
        return mas  # วันสิ้นสุดใกล้สุดก่อน
    return list(reversed(mas))  # MA ใหม่สุดก่อน / วันสิ้นสุดไกลสุดก่อน


@pytest.mark.parametrize("path", LIST_PAGES)
@pytest.mark.parametrize(
    "page, expected_slice",
    [
        ("1", slice(0, 2)),
        ("2", slice(2, 4)),
        ("0", slice(0, 2)),
        ("-1", slice(0, 2)),
        ("abc", slice(0, 2)),
        ("3", slice(4, 5)),
        ("999", slice(4, 5)),
    ],
)
def test_page_number_is_clamped_to_existing_pages(world, path, page, expected_slice):
    ordered = _five_mas_for(world, path)

    response = _get(world, path, page=page, per_page=2)

    assert response.status_code == 200
    assert _shown_mas(response) == ordered[expected_slice]


@pytest.mark.parametrize("path", LIST_PAGES)
def test_empty_list_page_with_page_number_is_not_404(world, path):
    response = _get(world, path, page=5)

    assert response.status_code == 200
    assert _shown_mas(response) == []


@pytest.mark.parametrize("path", LIST_PAGES)
def test_per_page_is_capped_at_100(world, path):
    status = "disactive" if path == NON_RENEWAL else "active"
    _create_mas(world, 101, status=status, responsible=world.admin_role)

    response = _get(world, path, per_page=100000)

    assert response.status_code == 200
    assert len(_shown_mas(response)) == 100


@pytest.mark.parametrize("path", LIST_PAGES)
def test_invalid_per_page_falls_back_to_at_least_one_row(world, path):
    _five_mas_for(world, path)

    for per_page in ("0", "-3"):
        response = _get(world, path, per_page=per_page)
        assert response.status_code == 200
        assert len(_shown_mas(response)) == 1


def test_non_renewal_is_paginated_and_keeps_filters_in_page_links(world):
    mine = _ma_names(
        _create_ma(world, end_in_days=10 + index, status="disactive", responsible=world.admin_role)
        for index in range(3)
    )
    others = _ma_names(_create_mas(world, 2, status="disactive"))

    first = _get(world, NON_RENEWAL, division="mine", per_page=2)
    html = first.get_data(as_text=True)

    assert first.status_code == 200
    assert _shown_mas(first) == [mine[2], mine[1]]
    assert "3 รายการ" in html
    page_two_links = [
        link
        for link in re.findall(r'href="([^"]*non-renewal[^"]*)"', html)
        if "page=2" in link.replace("&amp;", "&").split("?")[1].split("&")
    ]
    assert page_two_links
    for link in page_two_links:
        params = link.replace("&amp;", "&").split("?")[1].split("&")
        assert "division=mine" in params and "per_page=2" in params and f"organization_id={world.org.id}" in params

    second = _get(world, NON_RENEWAL, division="mine", per_page=2, page=2)
    assert _shown_mas(second) == [mine[0]]
    assert not set(others) & set(_shown_mas(second))


def test_non_renewal_row_numbers_continue_across_pages(world):
    _create_mas(world, 3, status="disactive", responsible=world.admin_role)

    html = _get(world, NON_RENEWAL, per_page=2, page=2).get_data(as_text=True)

    row_numbers = re.findall(r'rounded-full flex items-center justify-center text-sm font-bold">\s*(\d+)\s*<', html)
    assert row_numbers == ["3"]


# ---------------------------------------------------------------------------
# ตัวนับสถานะและการเรียง
# ---------------------------------------------------------------------------


def _status_counts(response) -> dict:
    html = response.get_data(as_text=True)
    counts = {}
    for status, css in [
        ("overdue", "text-error"),
        ("upcoming", "text-warning"),
        ("paid", "text-success"),
        ("unpaid", "text-base-content/60"),
    ]:
        match = re.search(rf'font-bold {re.escape(css)} text-3xl leading-none">\s*(\d+)\s*<', html)
        counts[status] = int(match.group(1))
    return counts


def test_products_status_counts_and_filter_follow_worst_unpaid_installment(world):
    paid_by = world.admin
    overdue = _create_ma(world, installments=[_installment(-5)])
    upcoming = _create_ma(world, installments=[_installment(-30, paid=True, paid_by=paid_by), _installment(3)])
    paid = _create_ma(
        world,
        installments=[_installment(-30, paid=True, paid_by=paid_by), _installment(-5, paid=True, paid_by=paid_by)],
    )
    unpaid = _create_ma(world, installments=[_installment(60)])
    # รายการย่อยหนึ่งจ่ายครบ อีกรายการเลยกำหนด → เลยกำหนด
    worst_item = _create_ma(
        world,
        items=[(30, [_installment(-5, paid=True, paid_by=paid_by)]), (30, [_installment(-1)])],
    )
    # งวดที่ยังไม่จ่ายซึ่งครบกำหนดเร็วสุดอยู่ท้ายรายการ → เลยกำหนด
    out_of_order = _create_ma(
        world,
        installments=[_installment(-20, paid=True, paid_by=paid_by), _installment(30), _installment(-2)],
    )

    response = _get(world, PRODUCTS)

    assert _status_counts(response) == {"overdue": 3, "upcoming": 1, "paid": 1, "unpaid": 1}
    expected_by_filter = {
        "overdue": {overdue.name, worst_item.name, out_of_order.name},
        "upcoming": {upcoming.name},
        "paid": {paid.name},
        "unpaid": {unpaid.name},
    }
    for status, expected in expected_by_filter.items():
        filtered = _get(world, PRODUCTS, payment_status=status)
        assert set(_shown_mas(filtered)) == expected, status
        # ตัวนับนับจาก MA ที่เห็นทั้งหมด ไม่ขึ้นกับ filter
        assert _status_counts(filtered) == {"overdue": 3, "upcoming": 1, "paid": 1, "unpaid": 1}


def test_renewal_page_sorts_by_earliest_item_end_date_across_pages(world):
    in_40 = _create_ma(world, end_in_days=40)
    in_10 = _create_ma(world, end_in_days=10)
    two_items = _create_ma(world, items=[(50, [_installment(50)]), (5, [_installment(5)])])
    in_25 = _create_ma(world, end_in_days=25)
    expected = _ma_names([two_items, in_10, in_25, in_40])

    assert _shown_mas(_get(world, RENEWAL, per_page=3)) == expected[:3]
    assert _shown_mas(_get(world, RENEWAL, per_page=3, page=2)) == expected[3:]


def test_non_renewal_page_sorts_by_latest_end_date_first(world):
    in_10 = _create_ma(world, end_in_days=10, status="disactive")
    two_items = _create_ma(world, items=[(50, [_installment(50)]), (5, [_installment(5)])], status="disactive")
    in_40 = _create_ma(world, end_in_days=40, status="disactive")

    assert _shown_mas(_get(world, NON_RENEWAL)) == _ma_names([in_40, in_10, two_items])


@pytest.mark.parametrize("path", LIST_PAGES)
def test_list_pages_show_each_rows_responsible_divisions(world, path):
    status = "disactive" if path == NON_RENEWAL else "active"
    _create_mas(world, 3, status=status)

    html = _get(world, path).get_data(as_text=True)

    for index in (1, 2, 3):
        assert f"[TEST] ฝ่าย {index}" in html
        if path != NON_RENEWAL:
            assert f"Owner{index} Test" in html
