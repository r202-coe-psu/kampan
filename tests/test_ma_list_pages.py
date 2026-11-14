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
NON_RENEWAL = "/procurement/requisitions/non-renewal"
LIST_PAGES = [PRODUCTS, NON_RENEWAL]


def _status_for_path(path):
    if path == NON_RENEWAL:
        return "disactive"
    return "active"

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
    status = _status_for_path(path)
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
    status = _status_for_path(path)
    mas = _ma_names(_create_ma(world, end_in_days=10 + index, status=status) for index in range(5))
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
    status = _status_for_path(path)
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


def test_non_renewal_page_sorts_by_latest_end_date_first(world):
    in_10 = _create_ma(world, end_in_days=10, status="disactive")
    two_items = _create_ma(world, items=[(50, [_installment(50)]), (5, [_installment(5)])], status="disactive")
    in_40 = _create_ma(world, end_in_days=40, status="disactive")

    assert _shown_mas(_get(world, NON_RENEWAL)) == _ma_names([in_40, in_10, two_items])


@pytest.mark.parametrize("path", LIST_PAGES)
def test_list_pages_show_each_rows_responsible_divisions(world, path):
    status = _status_for_path(path)
    _create_mas(world, 3, status=status)

    html = _get(world, path).get_data(as_text=True)

    for index in (1, 2, 3):
        assert f"[TEST] ฝ่าย {index}" in html
        if path != NON_RENEWAL:
            assert f"Owner{index} Test" in html


# ---------------------------------------------------------------------------
# เรียงลำดับ (?sort=) และแถบตัวกรอง
# ---------------------------------------------------------------------------

DEFAULT_SORT = {PRODUCTS: "created_desc", NON_RENEWAL: "end_desc"}


def _sort_set(world, path):
    """MA 4 ตัว: สร้างตามลำดับ A, B, C, D · ชื่อและวันสิ้นสุดสลับกันจนทุกตัวเลือกเรียงไม่เหมือนกัน
    คืนชื่อเรียงตามแต่ละตัวเลือก"""
    status = _status_for_path(path)
    mas = {}
    for key, name_number, end_in in (("a", 30, 40), ("b", 10, 10), ("c", 40, 30), ("d", 20, 20)):
        ma = _create_ma(world, end_in_days=end_in, status=status)
        name = f"[TEST] MA-{name_number:04d}"
        models.Procurement.objects(id=ma.id).update(set__name=name)
        mas[key] = name
    order = lambda keys: [mas[key] for key in keys]  # noqa: E731
    return {
        "created_desc": order("dcba"),
        "created_asc": order("abcd"),
        "end_asc": order("bdca"),
        "end_desc": order("acdb"),
        "due_asc": order("bdca"),  # งวดที่ยังไม่จ่ายครบกำหนดพร้อมวันสิ้นสุด (ดู test_due_asc_*)
        "name_asc": order("bdac"),
    }


@pytest.mark.parametrize("sort", ["created_desc", "created_asc", "end_asc", "end_desc", "due_asc", "name_asc"])
@pytest.mark.parametrize("path", LIST_PAGES)
def test_list_pages_sort_options(world, path, sort):
    expected = _sort_set(world, path)

    assert _shown_mas(_get(world, path, sort=sort)) == expected[sort]


@pytest.mark.parametrize("path", LIST_PAGES)
def test_list_pages_default_sort_and_unknown_sort_use_the_page_default(world, path):
    expected = _sort_set(world, path)
    default = expected[DEFAULT_SORT[path]]

    assert _shown_mas(_get(world, path)) == default
    for bad in ("nope", "", "created_desc;drop", "-created_date"):
        response = _get(world, path, sort=bad)
        assert response.status_code == 200
        assert _shown_mas(response) == default
        html = response.get_data(as_text=True)
        assert re.search(rf'name="sort"[^>]*value="{DEFAULT_SORT[path]}"', html)


def test_products_default_order_is_newest_created_first(world):
    mas = _ma_names(_create_mas(world, 3))

    assert _shown_mas(_get(world, PRODUCTS)) == list(reversed(mas))


@pytest.mark.parametrize("path", LIST_PAGES)
def test_sort_control_shows_the_selected_option_as_dropdown(world, path):
    _sort_set(world, path)

    html = _get(world, path, sort="name_asc").get_data(as_text=True)

    assert re.search(r'<input type="hidden" name="sort" id="sort" value="name_asc"', html)
    button = re.search(r'id="dd-button-sort".*?<span data-dd-label[^>]*>([^<]*)</span>', html, re.S)
    assert button and button.group(1) == "ชื่อ ก → ฮ"
    for label in ("สร้างล่าสุด → เก่าสุด", "สร้างเก่าสุด → ล่าสุด", "ใกล้หมดอายุที่สุด", "หมดอายุหลังสุด"):
        assert label in html


@pytest.mark.parametrize("path", LIST_PAGES)
def test_sort_is_kept_in_page_links_with_other_filters(world, path):
    status = _status_for_path(path)
    _create_mas(world, 5, status=status, responsible=world.admin_role)

    html = _get(world, path, sort="name_asc", division="mine", per_page=2).get_data(as_text=True)

    links = [link.replace("&amp;", "&") for link in re.findall(r'href="([^"]*page=\d[^"]*)"', html)]
    assert links
    for link in links:
        params = link.split("?")[1].split("&")
        assert "sort=name_asc" in params and "division=mine" in params and "per_page=2" in params


@pytest.mark.parametrize("path", LIST_PAGES)
def test_sorted_pages_paginate_without_losing_or_repeating_rows(world, path):
    expected = _sort_set(world, path)

    for sort, names in expected.items():
        first = _shown_mas(_get(world, path, sort=sort, per_page=3))
        second = _shown_mas(_get(world, path, sort=sort, per_page=3, page=2))
        assert first + second == names, sort


@pytest.mark.parametrize("path", LIST_PAGES)
@pytest.mark.parametrize("sort", ["created_desc", "end_asc", "name_asc"])
def test_sorted_list_query_count_does_not_grow_with_ma_count(world, query_counter, path, sort):
    status = _status_for_path(path)
    _create_mas(world, 3, status=status)
    few = _query_count(world, query_counter, f"{path}?sort={sort}")

    _create_mas(world, 30, status=status)
    many = _query_count(world, query_counter, f"{path}?sort={sort}")

    assert many == few


def _non_renewal(world, name, **overrides):
    ma = _create_ma(world, status="disactive", **{k: v for k, v in overrides.items() if k in ("end_in_days", "responsible")})
    updates = {"set__name": name}
    if "company" in overrides:
        updates["set__company"] = overrides["company"]
    models.Procurement.objects(id=ma.id).update(**updates)
    return ma


def test_non_renewal_filters_by_search_company_category_responsible_and_end_range(world):
    owner = _add_member(world, 90)
    alpha = _non_renewal(world, "[TEST] MA-0101", company="บริษัท อัลฟา", end_in_days=10, responsible=owner)
    beta = _non_renewal(world, "[TEST] MA-0102", company="บริษัท เบตา", end_in_days=100)
    models.ProcurementItem.objects(procurement=beta).update(set__category="software")

    def shown(**params):
        return set(_shown_mas(_get(world, NON_RENEWAL, **params)))

    assert shown() == {"[TEST] MA-0101", "[TEST] MA-0102"}
    assert shown(name="MA-0102") == {"[TEST] MA-0102"}
    assert shown(name="PSU-" + alpha.psu_disbursement_number.split("-")[1]) == {"[TEST] MA-0101"}
    assert shown(company="เบตา") == {"[TEST] MA-0102"}
    assert shown(category="software") == {"[TEST] MA-0102"}
    assert shown(responsible=owner.id) == {"[TEST] MA-0101"}
    end_alpha = (TODAY + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
    assert shown(end_from=end_alpha, end_to=end_alpha) == {"[TEST] MA-0101"}
    assert shown(end_from=(TODAY + datetime.timedelta(days=11)).strftime("%Y-%m-%d")) == {"[TEST] MA-0102"}
    assert shown(end_to=(TODAY + datetime.timedelta(days=11)).strftime("%Y-%m-%d")) == {"[TEST] MA-0101"}
    # ค่าที่ไม่ถูกต้องไม่ทำให้หน้า 500 และไม่กรองอะไร
    assert shown(end_from="not-a-date", responsible="zzz") == {"[TEST] MA-0101", "[TEST] MA-0102"}


def test_non_renewal_filters_never_leak_other_organizations(world, create_org):
    other_org = create_org("[TEST] Org อื่น")
    foreign = models.Procurement(
        organization=other_org, name="[TEST] MA-0999", company="บริษัท อื่น", total_amount=Decimal("100.00"), status="disactive"
    )
    member = models.OrganizationUserRole(
        user=world.admin, organization=other_org, roles=["staff"], status="active", added_by=world.admin, last_modifier=world.admin
    ).save()
    foreign.save_with_items([_item(999, member, 5, [_installment(5)])])
    _non_renewal(world, "[TEST] MA-0100")

    for params in ({}, {"company": "อื่น"}, {"name": "MA-0999"}, {"responsible": member.id}):
        assert "[TEST] MA-0999" not in _get(world, NON_RENEWAL, **params).get_data(as_text=True)


@pytest.mark.parametrize("path", LIST_PAGES)
def test_filter_bar_has_count_clear_button_and_no_native_select(world, path):
    status = _status_for_path(path)
    _create_mas(world, 2, status=status)

    html = _get(world, path).get_data(as_text=True)

    assert "<select" not in html.split('id="ma_filter_form"', 1)[1].split("</form>", 1)[0]
    form_html = html.split('id="ma_filter_form"', 1)[1].split("</form>", 1)[0]
    assert "ล้างตัวกรอง" in form_html and "พบ <span" in form_html
    assert re.search(r'href="[^"]*%s[^"]*"[^>]*>\s*<i class="ph ph-x"></i> ล้างตัวกรอง' % re.escape(path), form_html)


# ---------------------------------------------------------------------------
# จำนวนรายการต่อหน้าตั้งต้น และการแบ่งหน้าที่ Mongo ทำ (skip/limit) ทั้งเรียงตามสร้าง/ชื่อและวันหมดอายุ
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,per_page,last_page_size",
    [(PRODUCTS, 6, 2), (NON_RENEWAL, 8, 4)],
)
def test_default_page_size_and_last_page(world, path, per_page, last_page_size):
    status = _status_for_path(path)
    for index in range(20):
        _create_ma(world, end_in_days=10 + index, status=status)
    pages = -(-20 // per_page)

    first = _shown_mas(_get(world, path))
    last = _shown_mas(_get(world, path, page=pages))
    beyond = _shown_mas(_get(world, path, page=pages + 5))  # หน้าเกินใช้หน้าสุดท้าย

    assert len(first) == per_page
    assert len(last) == last_page_size
    assert beyond == last
    assert not set(first) & set(last)


@pytest.mark.parametrize("sort", ["end_asc", "end_desc"])
def test_end_date_sort_pages_are_cut_by_the_database(world, monkeypatch, sort):
    """เรียงวันหมดอายุ: แต่ละหน้าได้เฉพาะ id ของหน้านั้นจาก aggregation ($skip/$limit) ครบทุกหน้าไม่ซ้ำไม่ตก"""
    status = _status_for_path(NON_RENEWAL)
    created = [_create_ma(world, end_in_days=10 + index, status=status).name for index in range(19)]
    expected = created if sort == "end_asc" else list(reversed(created))

    pipelines = []
    original = mongomock.collection.Collection.aggregate

    def recording(self, pipeline, *args, **kwargs):
        pipelines.append(list(pipeline))
        return original(self, pipeline, *args, **kwargs)

    monkeypatch.setattr(mongomock.collection.Collection, "aggregate", recording)
    shown = []
    for page in (1, 2, 3):
        shown += _shown_mas(_get(world, NON_RENEWAL, sort=sort, page=page))

    assert shown == expected
    limits = [stage["$limit"] for pipeline in pipelines for stage in pipeline if "$limit" in stage]
    assert limits[:3] == [8, 8, 3]  # หน้าสุดท้ายเหลือ 3 จาก 19


@pytest.mark.parametrize("path", LIST_PAGES)
def test_due_asc_sorts_by_nearest_unpaid_installment_not_by_end_date(world, path):
    """ใกล้วันจ่ายงวดที่สุด: ดูเฉพาะงวดที่ยังไม่จ่าย งวดที่จ่ายแล้วไม่นับ MA ที่จ่ายครบแล้วไว้ท้าย"""
    status = _status_for_path(path)
    paid = _installment(1, paid=True, paid_by=world.admin)
    a = _create_ma(world, status=status, items=[(100, [paid, _installment(50)])])
    b = _create_ma(world, status=status, items=[(20, [_installment(-5, paid=True, paid_by=world.admin), _installment(90)])])
    c = _create_ma(world, status=status, items=[(60, [_installment(5, paid=True, paid_by=world.admin)])])
    d = _create_ma(world, status=status, items=[(80, [_installment(10)]), (90, [_installment(70)])])

    shown = _shown_mas(_get(world, path, sort="due_asc"))

    assert shown == [d.name, a.name, b.name, c.name]
    first_page = _shown_mas(_get(world, path, sort="due_asc", per_page=3))
    second_page = _shown_mas(_get(world, path, sort="due_asc", per_page=3, page=2))
    assert first_page + second_page == shown and second_page == [c.name]
