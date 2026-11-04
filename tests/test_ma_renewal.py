"""ต่ออายุ MA = สร้าง MA ใหม่จาก MA เดิม (#32)

- GET เปิดฟอร์มสร้าง MA ที่เติมข้อมูลจาก MA เดิม (ยังไม่สร้างอะไร)
- POST สร้าง MA ใหม่ที่ renewed_from ชี้ MA เดิม และ MA เดิมเป็น "ต่ออายุแล้ว"

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org")
    other_org = create_org("[TEST] Org อื่น")
    division = models.Division(name="[TEST] ฝ่ายไอที", organization=org).save()

    def member(first_name, roles, organization=org):
        user = create_user(first_name, "Renew")
        role = assign_user_to_org(user, organization, roles=roles)
        role.first_name = first_name
        role.division = division if organization == org else None
        role.save()
        return user, role

    admin, role_admin = member("Admin", ["admin"])
    creator, role_creator = member("Creator", ["staff"])
    responsible, role_responsible = member("Responsible", ["staff"])
    other_staff, role_other_staff = member("Other", ["staff"])
    head, role_head = member("Head", ["head"])
    admin_other, role_admin_other = member("AdminOther", ["admin"], organization=other_org)

    old = models.Procurement(
        psu_disbursement_number="PSU-OLD-1",
        name="[TEST] MA เดิม",
        company="[TEST] บริษัทเดิม",
        organization=org,
        status="pending",
        total_amount=Decimal("100000.00"),
        created_by=creator,
    )
    old.save_with_items(
        [
            models.ProcurementItem(
                name="[TEST] License A",
                category="intangible",
                account_code="1204010101 สินทรัพย์ไม่มีตัวตน",
                start_date=datetime.datetime(2025, 1, 1),
                end_date=datetime.datetime(2025, 12, 31),
                amount=Decimal("60000.00"),
                sub_items=[
                    models.ItemDetail(brand="ยี่ห้อ A", model_name="รุ่น A", details="S/N: ABC-001"),
                    models.ItemDetail(brand="ยี่ห้อ B", details="S/N: ABC-002"),
                ],
                winner="บริษัท ผู้ชนะ",
                unit_price=Decimal("30000.00"),
                note="หมายเหตุ A",
                responsible_by=[role_responsible],
                reminder_kind="license",
                requires_activation=True,
                installments=[
                    models.Installment(
                        due_date=datetime.datetime(2025, 6, 30),
                        paid_date=datetime.datetime(2025, 6, 30),
                        payment_number="PAY-OLD-1",
                        paid_amount=Decimal("30000.00"),
                    ),
                    models.Installment(due_date=datetime.datetime(2025, 12, 31)),
                ],
            ),
            models.ProcurementItem(
                name="[TEST] MA B",
                category="service",
                start_date=datetime.datetime(2025, 3, 1),
                end_date=datetime.datetime(2026, 2, 28),
                amount=Decimal("40000.00"),
                responsible_by=[role_admin],
                installments=[models.Installment(due_date=datetime.datetime(2026, 2, 28))],
            ),
        ]
    )
    return SimpleNamespace(**locals())


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        return login_as(app.test_client(), user)

    return _client_for


def _renew_url(world, procurement=None, organization=None):
    procurement = procurement or world.old
    organization = organization or world.org
    return f"/procurement/products/{procurement.id}/renew?organization_id={organization.id}"


def _input_value(html, name):
    match = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*>', html)
    assert match, name
    value = re.search(r'value="([^"]*)"', match.group(0))
    return value.group(1) if value else ""


def test_renew_form_is_prefilled_from_old_ma_and_creates_nothing(world, client_for):
    response = client_for(world.admin).get(_renew_url(world))

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert _input_value(html, "name") == "[TEST] MA เดิม"
    assert _input_value(html, "company") == "[TEST] บริษัทเดิม"
    assert _input_value(html, "total_amount") == "100000.00"
    assert _input_value(html, "psu_disbursement_number") == ""
    assert _input_value(html, "items-0-name") == "[TEST] License A"
    assert _input_value(html, "items-0-amount") == "60000.00"
    assert _input_value(html, "items-0-sub_items-0-brand") == "ยี่ห้อ A"
    assert _input_value(html, "items-0-sub_items-0-model_name") == "รุ่น A"
    assert _input_value(html, "items-0-sub_items-1-brand") == "ยี่ห้อ B"
    assert _input_value(html, "items-0-winner") == "บริษัท ผู้ชนะ"
    assert _input_value(html, "items-0-unit_price") == "30000.00"
    assert _input_value(html, "items-1-name") == "[TEST] MA B"
    assert "S/N: ABC-001" in html and "S/N: ABC-002" in html and "หมายเหตุ A" in html
    # วันเริ่ม-สิ้นสุดเว้นว่าง งวดเหลือ 1 แถวว่าง และไม่มีข้อมูลการจ่ายของ MA เดิม
    for index in (0, 1):
        assert _input_value(html, f"items-{index}-start_date") == ""
        assert _input_value(html, f"items-{index}-end_date") == ""
        assert _input_value(html, f"items-{index}-item_id") == ""
    assert _input_value(html, "items-0-installments-0-due_date") == ""
    assert 'name="items-0-installments-1-due_date"' not in html
    assert "PAY-OLD-1" not in html
    # ผู้รับผิดชอบ, ประเภทการเตือน และต้อง activate ถูก copy
    assert re.search(rf'name="items-0-responsible_by" value="{world.role_responsible.id}"\s+checked', html)
    assert _input_value(html, "items-0-reminder_kind") == "license"
    assert re.search(r'name="items-0-requires_activation"[^>]*checked', html) or re.search(
        r'checked[^>]*name="items-0-requires_activation"', html
    )
    assert "ต่ออายุจาก" in html
    assert models.Procurement.objects.count() == 1
    assert models.ProcurementItem.objects.count() == 2
    world.old.reload()
    assert world.old.status == "pending" and world.old.renewed_to is None


def _renew_form(world, psu="PSU-NEW-1", **overrides):
    """ฟอร์มที่ผู้ใช้กรอกต่อจากค่าที่เติมไว้: เลขที่ ม.อ.เบิกจ่าย, วันที่ และงวดใหม่"""
    data = {
        "psu_disbursement_number": psu,
        "name": "[TEST] MA เดิม",
        "company": "[TEST] บริษัทเดิม",
        "total_amount": "100000.00",
        "items-0-name": "[TEST] License A",
        "items-0-category": "intangible",
        "items-0-account_code": "1204010101 สินทรัพย์ไม่มีตัวตน",
        "items-0-start_date": "2026-01-01",
        "items-0-end_date": "2026-12-31",
        "items-0-amount": "60000.00",
        "items-0-sub_items-0-brand": "ยี่ห้อ A",
        "items-0-sub_items-0-model_name": "รุ่น A",
        "items-0-sub_items-0-details": "S/N: ABC-001",
        "items-0-sub_items-1-brand": "ยี่ห้อ B",
        "items-0-sub_items-1-details": "S/N: ABC-002",
        "items-0-reminder_kind": "license",
        "items-0-requires_activation": "y",
        "items-0-responsible_by": [str(world.role_responsible.id)],
        "items-0-installments-0-due_date": "2026-12-31",
        "items-1-name": "[TEST] MA B",
        "items-1-category": "service",
        "items-1-start_date": "2026-03-01",
        "items-1-end_date": "2027-02-28",
        "items-1-amount": "40000.00",
        "items-1-reminder_kind": "ma",
        "items-1-responsible_by": [str(world.role_admin.id)],
        "items-1-installments-0-due_date": "2027-02-28",
    }
    data.update(overrides)
    return data


def _old_snapshot(world):
    items = models.ProcurementItem.objects(procurement=world.old).order_by("id")
    return [(item.name, item.start_date, item.amount, [i.to_mongo().to_dict() for i in item.installments]) for item in items]


def test_renew_post_creates_new_ma_and_marks_old_renewed(world, client_for):
    before = _old_snapshot(world)

    response = client_for(world.responsible).post(_renew_url(world), data=_renew_form(world))

    assert response.status_code == 302
    new = models.Procurement.objects(id__ne=world.old.id).get()
    assert f"/procurement/payment/{new.id}" in response.headers["Location"]
    assert new.renewed_from.id == world.old.id
    assert new.psu_disbursement_number == "PSU-NEW-1"
    assert new.status == "active"
    assert new.organization.id == world.org.id
    assert new.created_by.id == world.responsible.id
    new_items = list(models.ProcurementItem.objects(procurement=new).order_by("id"))
    assert [item.name for item in new_items] == ["[TEST] License A", "[TEST] MA B"]
    assert new_items[0].start_date == datetime.datetime(2026, 1, 1)
    assert all(not installment.is_paid() for item in new_items for installment in item.installments)
    assert [(row.brand, row.model_name, row.details) for row in new_items[0].sub_items] == [
        ("ยี่ห้อ A", "รุ่น A", "S/N: ABC-001"),
        ("ยี่ห้อ B", None, "S/N: ABC-002"),
    ]

    world.old.reload()
    assert world.old.status == "renewed"
    assert world.old.renewed_to.id == new.id
    assert world.old.psu_disbursement_number == "PSU-OLD-1"
    assert _old_snapshot(world) == before


def test_double_submit_creates_only_one_new_ma(world, client_for):
    client = client_for(world.admin)

    first = client.post(_renew_url(world), data=_renew_form(world))
    second = client.post(_renew_url(world), data=_renew_form(world, psu="PSU-NEW-2"))

    assert first.status_code == 302 and second.status_code == 302
    assert models.Procurement.objects(renewed_from=world.old).count() == 1
    assert models.Procurement.objects(psu_disbursement_number="PSU-NEW-2").count() == 0


def test_concurrent_claim_loses_and_creates_nothing(world):
    """2 คำขอโหลด MA เดิมพร้อมกัน: ตัวที่ claim ทีหลังต้องไม่สร้าง MA ใหม่"""
    first_view = models.Procurement.objects.get(id=world.old.id)
    second_view = models.Procurement.objects.get(id=world.old.id)

    def new_ma(psu):
        item = models.ProcurementItem(
            name="[TEST] ใหม่",
            category="service",
            start_date=datetime.datetime(2026, 1, 1),
            end_date=datetime.datetime(2026, 12, 31),
            amount=Decimal("10.00"),
            installments=[models.Installment(due_date=datetime.datetime(2026, 12, 31))],
        )
        header = models.Procurement(name="[TEST] ใหม่", company="c", psu_disbursement_number=psu, total_amount=Decimal("10.00"))
        return header, [item]

    first_view.renew_into(*new_ma("PSU-A"))
    with pytest.raises(models.RenewalConflict):
        second_view.renew_into(*new_ma("PSU-B"))

    assert models.Procurement.objects(psu_disbursement_number="PSU-B").count() == 0
    assert models.Procurement.objects(renewed_from=world.old).count() == 1


def test_claim_in_progress_blocks_second_renewal(world):
    """คำขอแรก claim แล้วแต่ยังสร้าง MA ใหม่ไม่เสร็จ (status renewed แต่ยังไม่มี renewed_to): คำขอที่ 2 ต้อง claim ไม่ได้"""
    stale_view = models.Procurement.objects.get(id=world.old.id)
    models.Procurement.objects(id=world.old.id).update_one(set__status="renewed", set__status_before_renewal="pending")
    item = models.ProcurementItem(
        name="[TEST] ใหม่",
        category="service",
        start_date=datetime.datetime(2026, 1, 1),
        end_date=datetime.datetime(2026, 12, 31),
        amount=Decimal("10.00"),
        installments=[models.Installment(due_date=datetime.datetime(2026, 12, 31))],
    )
    header = models.Procurement(name="[TEST] ใหม่", company="c", total_amount=Decimal("10.00"))

    with pytest.raises(models.RenewalConflict):
        stale_view.renew_into(header, [item])

    assert models.Procurement.objects.count() == 1
    assert models.Procurement.objects.get(id=world.old.id).status == "renewed"


@pytest.mark.parametrize("method", ["get", "post"])
def test_renewed_ma_cannot_be_renewed_again(world, client_for, method):
    client = client_for(world.admin)
    client.post(_renew_url(world), data=_renew_form(world))

    response = getattr(client, method)(_renew_url(world), data=_renew_form(world, psu="PSU-NEW-2"))

    assert response.status_code == 302
    assert f"/procurement/payment/{world.old.id}" in response.headers["Location"]
    assert models.Procurement.objects.count() == 2


def test_renew_from_disactive_ma(world, client_for):
    world.old.update(set__status="disactive")

    response = client_for(world.admin).post(_renew_url(world), data=_renew_form(world))

    assert response.status_code == 302
    world.old.reload()
    assert world.old.status == "renewed"
    assert world.old.status_before_renewal == "disactive"
    assert models.Procurement.objects(renewed_from=world.old).count() == 1


@pytest.mark.parametrize("who", ["admin", "creator", "responsible"])
def test_renew_allowed_for_users_who_can_edit(world, client_for, who):
    client = client_for(getattr(world, who))

    assert client.get(_renew_url(world)).status_code == 200
    assert client.post(_renew_url(world), data=_renew_form(world)).status_code == 302
    assert models.Procurement.objects(renewed_from=world.old).count() == 1


@pytest.mark.parametrize("who, status", [("head", 302), ("other_staff", 404)])
def test_renew_refused_for_users_who_cannot_edit(world, client_for, who, status):
    client = client_for(getattr(world, who))

    for response in (client.get(_renew_url(world)), client.post(_renew_url(world), data=_renew_form(world))):
        assert response.status_code == status
    world.old.reload()
    assert world.old.status == "pending"
    assert models.Procurement.objects.count() == 1


def test_renew_other_org_ma_is_404(world, client_for):
    client = client_for(world.admin_other)
    url = _renew_url(world, organization=world.other_org)

    assert client.get(url).status_code == 404
    assert client.post(url, data=_renew_form(world)).status_code == 404
    world.old.reload()
    assert world.old.status == "pending"
    assert models.Procurement.objects.count() == 1


def test_renew_with_sum_mismatch_keeps_old_ma_unclaimed(world, client_for):
    response = client_for(world.admin).post(_renew_url(world), data=_renew_form(world, **{"items-1-amount": "39999.00"}))

    assert response.status_code == 200
    assert "ขาด 1.00 บาท" in response.get_data(as_text=True)
    world.old.reload()
    assert world.old.status == "pending" and world.old.renewed_to is None
    assert models.Procurement.objects.count() == 1


def test_failed_save_releases_claim(world, client_for, monkeypatch):
    def broken_save(self, *args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(models.ProcurementItem, "save", broken_save)
    client = client_for(world.admin)

    with pytest.raises(RuntimeError):
        client.post(_renew_url(world), data=_renew_form(world))

    world.old.reload()
    assert world.old.status == "pending"
    assert world.old.renewed_to is None
    assert world.old.status_before_renewal is None
    assert models.Procurement.objects.count() == 1
    assert models.ProcurementItem.objects.count() == 2


def test_failed_link_removes_new_ma_and_releases_claim(world, monkeypatch):
    """ผูก renewed_to ไม่สำเร็จ (เช่น DB ล่มหลังสร้าง MA ใหม่): ลบ MA ใหม่และคืน claim"""
    from kampan.models import procurement as procurement_module

    original_update_one = procurement_module.me.QuerySet.update_one

    def update_one(queryset, *args, **kwargs):
        if "set__renewed_to" in kwargs:
            raise RuntimeError("db down")
        return original_update_one(queryset, *args, **kwargs)

    monkeypatch.setattr(procurement_module.me.QuerySet, "update_one", update_one)
    item = models.ProcurementItem(
        name="[TEST] ใหม่",
        category="service",
        start_date=datetime.datetime(2026, 1, 1),
        end_date=datetime.datetime(2026, 12, 31),
        amount=Decimal("10.00"),
        installments=[models.Installment(due_date=datetime.datetime(2026, 12, 31))],
    )
    header = models.Procurement(name="[TEST] ใหม่", company="c", total_amount=Decimal("10.00"))

    with pytest.raises(RuntimeError):
        world.old.renew_into(header, [item])

    old = models.Procurement.objects.get(id=world.old.id)
    assert old.status == "pending" and old.renewed_to is None
    assert models.Procurement.objects.count() == 1
    assert models.ProcurementItem.objects.count() == 2


# ---------------------------------------------------------------------------
# หน้าจอ: ปุ่มต่ออายุ, แถบต่ออายุไปที่ / ต่ออายุจาก และสายการต่ออายุ
# ---------------------------------------------------------------------------

MA_PAGES = {
    "products": "/procurement/products?organization_id={org}",
    "renewal": "/procurement/requisitions?organization_id={org}&expiration_date_range=",
    "detail": "/procurement/payment/{ma}?organization_id={org}",
}


def _page(world, page, procurement=None):
    return MA_PAGES[page].format(org=world.org.id, ma=(procurement or world.old).id)


@pytest.mark.parametrize("flag", [True, False])
@pytest.mark.parametrize("page", MA_PAGES)
def test_ma_pages_have_no_old_renewal_request_path(world, client_for, app, monkeypatch, page, flag):
    monkeypatch.setitem(app.config, "PROCUREMENT_REQUISITION_ENABLED", flag)

    html = client_for(world.admin).get(_page(world, page)).get_data(as_text=True)

    assert "/renewal-requested" not in html
    assert "renew_modal_" not in html
    assert _renew_url(world) in html


@pytest.mark.parametrize("page", MA_PAGES)
def test_renew_button_hidden_from_users_who_cannot_edit(world, client_for, page):
    html = client_for(world.head).get(_page(world, page)).get_data(as_text=True)

    assert f"/procurement/products/{world.old.id}/renew" not in html


def test_renewed_ma_shows_banners_chain_and_no_renew_button(world, client_for):
    client = client_for(world.admin)
    client.post(_renew_url(world), data=_renew_form(world))
    new = models.Procurement.objects(renewed_from=world.old).get()
    newest_response = client.post(_renew_url(world, new), data=_renew_form(world, psu="PSU-NEW-3"))
    assert newest_response.status_code == 302
    newest = models.Procurement.objects(renewed_from=new).get()

    old_html = client.get(_page(world, "detail")).get_data(as_text=True)
    middle_html = client.get(_page(world, "detail", new)).get_data(as_text=True)
    products_html = client.get(_page(world, "products")).get_data(as_text=True)

    assert "ต่ออายุไปที่รายการ" in old_html
    assert f"/procurement/payment/{new.id}?" in old_html
    assert "ต่ออายุแล้ว" in old_html
    assert _renew_url(world) not in old_html
    assert _renew_url(world) not in products_html
    assert "ต่ออายุจากรายการ" in middle_html and "ต่ออายุไปที่รายการ" in middle_html
    # สายการต่ออายุแสดงครบทั้ง 3 ทอด เรียงจากเก่าไปใหม่
    chain_html = middle_html[middle_html.index("สายการต่ออายุ"):]
    positions = [chain_html.index(number) for number in ("PSU-OLD-1", "PSU-NEW-1", "PSU-NEW-3")]
    assert positions == sorted(positions)
    assert newest.renewed_from.id == new.id
