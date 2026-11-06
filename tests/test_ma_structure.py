"""โครงสร้าง MA: หัวสัญญา → รายการย่อย → งวด (#25, #26, #27)

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import asyncio
import datetime
import io
import re
from decimal import Decimal
from types import SimpleNamespace

import mongoengine as me
import pandas as pd
import pytest

from kampan import models
from kampan.controllers.procurement_status import ProcurementStatusUpdater
from kampan.utils import upload_files
from kampan.utils.money import MONEY_PLACES_ERROR


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org A")
    other_org = create_org("[TEST] Org B")
    division_it = models.Division(name="[TEST] ฝ่ายไอที", organization=org).save()
    division_fin = models.Division(name="[TEST] ฝ่ายการเงิน", organization=org).save()

    def member(first_name, organization, roles, division=None):
        user = create_user(first_name, "Tester")
        role = assign_user_to_org(user, organization, roles=roles)
        role.first_name = first_name
        role.last_name = "Tester"
        role.division = division
        role.save()
        return user, role

    admin, role_admin = member("Admin", org, ["admin"], division_it)
    creator, role_creator = member("Creator", org, ["staff"], division_it)
    responsible, role_responsible = member("Responsible", org, ["staff"], division_fin)
    other_staff, role_other_staff = member("Other", org, ["staff"], division_fin)
    # เห็น MA ทั้งหน่วยงาน (#31) แต่ไม่ใช่ผู้แก้ไข MA ได้
    head, role_head = member("Head", org, ["head"], division_fin)
    admin_b, role_admin_b = member("AdminB", other_org, ["admin"])
    return SimpleNamespace(**locals())


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        return login_as(app.test_client(), user)

    return _client_for


@pytest.fixture
def gridfs_enabled():
    import mongomock.gridfs

    mongomock.gridfs.enable_gridfs_integration()


def _q(organization):
    return f"organization_id={organization.id}"


def _item(**overrides):
    item = {
        "name": "[TEST] รายการย่อย",
        "category": "software",
        "account_code": "",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "amount": "50000.00",
        "reminder_kind": "ma",
        "responsible_by": [],
        "installments": [{"due_date": "2026-12-31"}],
    }
    item.update(overrides)
    return item


def ma_form(items, total_amount="100000.00", psu="PSU-25/2569", name="[TEST] MA", **extra):
    data = {"psu_disbursement_number": psu, "name": name, "company": "[TEST] บริษัท", "total_amount": total_amount}
    data.update(extra)
    for index, item in enumerate(items):
        item = dict(item)
        installments = item.pop("installments")
        sub_items = item.pop("sub_items", [])
        for key, value in item.items():
            data[f"items-{index}-{key}"] = value
        for sub_index, sub_item in enumerate(sub_items):
            for key, value in sub_item.items():
                data[f"items-{index}-sub_items-{sub_index}-{key}"] = value
        for installment_index, installment in enumerate(installments):
            for key, value in installment.items():
                data[f"items-{index}-installments-{installment_index}-{key}"] = value
    return data


def _two_item_form(world):
    return ma_form(
        [
            _item(
                name="[TEST] License A",
                category="intangible",
                account_code="1204010101 สินทรัพย์ไม่มีตัวตน",
                amount="60000.00",
                sub_items=[
                    {"brand": "ยี่ห้อ A", "model_name": "รุ่น A", "details": "S/N: ABC-001\nรหัสครุภัณฑ์: CC/1"},
                    {"brand": "ยี่ห้อ B", "model_name": "", "details": "S/N: ABC-002"},
                    {"brand": "", "model_name": "", "details": "รหัสครุภัณฑ์: CC/3"},
                ],
                winner="บริษัท ผู้ชนะ",
                unit_price="30000.00",
                note="หมายเหตุ A",
                reminder_kind="license",
                requires_activation="y",
                responsible_by=[str(world.role_admin.id), str(world.role_responsible.id)],
                installment_mode="y",
                installments=[{"due_date": "2026-06-30"}, {"due_date": "2026-12-31"}],
            ),
            _item(
                name="[TEST] MA B",
                start_date="2026-03-01",
                end_date="2027-02-28",
                amount="40000.00",
                responsible_by=[str(world.role_creator.id)],
            ),
        ]
    )


def _create(client, world, data):
    return client.post(f"/procurement/products/create?{_q(world.org)}", data=data)


# ---------------------------------------------------------------------------
# สร้าง MA
# ---------------------------------------------------------------------------


def test_create_ma_with_two_items_saves_header_items_and_installments(world, client_for):
    response = _create(client_for(world.admin), world, _two_item_form(world))

    assert response.status_code == 302
    procurement = models.Procurement.objects.get(parent_procurement=None)
    assert f"/procurement/payment/{procurement.id}" in response.headers["Location"]
    assert procurement.psu_disbursement_number == "PSU-25/2569"
    assert procurement.total_amount == Decimal("100000.00")
    assert procurement.organization.id == world.org.id
    assert procurement.created_by.id == world.admin.id

    children = list(models.Procurement.objects(parent_procurement=procurement).order_by("id"))
    assert len(children) == 2
    assert [c.name for c in children] == ["[TEST] MA - [TEST] License A", "[TEST] MA - [TEST] MA B"]
    assert [c.total_amount for c in children] == [Decimal("60000.00"), Decimal("40000.00")]
    assert all(c.company == procurement.company for c in children)
    assert all(c.psu_disbursement_number == procurement.psu_disbursement_number for c in children)

    items = list(models.ProcurementItem.objects(procurement=procurement).order_by("id"))
    assert [item.name for item in items] == ["[TEST] License A", "[TEST] MA B"]
    first, second = items
    assert first.organization.id == world.org.id
    assert first.category == "intangible"
    assert first.account_code == "1204010101 สินทรัพย์ไม่มีตัวตน"
    assert first.amount == Decimal("60000.00")
    assert [(row.brand, row.model_name, row.details) for row in first.sub_items] == [
        ("ยี่ห้อ A", "รุ่น A", "S/N: ABC-001\nรหัสครุภัณฑ์: CC/1"),
        ("ยี่ห้อ B", None, "S/N: ABC-002"),
        (None, None, "รหัสครุภัณฑ์: CC/3"),
    ]
    assert (first.winner, first.note) == ("บริษัท ผู้ชนะ", "หมายเหตุ A")
    assert second.sub_items == []
    assert first.unit_price == Decimal("30000.00")
    assert first.reminder_kind == "license"
    assert first.requires_activation is True
    assert [installment.due_date for installment in first.installments] == [
        datetime.datetime(2026, 6, 30),
        datetime.datetime(2026, 12, 31),
    ]
    assert all(installment.paid_date is None for installment in first.installments)
    assert first.installment_mode is True and second.installment_mode is False
    assert {member.id for member in first.responsible_by} == {world.role_admin.id, world.role_responsible.id}
    assert second.winner is None and second.unit_price is None
    assert len(second.installments) == 1


def test_detail_page_shows_every_item_with_details_line_breaks(world, client_for):
    client = client_for(world.admin)
    _create(client, world, _two_item_form(world))
    procurement = models.Procurement.objects.get(parent_procurement=None)

    html = client.get(f"/procurement/payment/{procurement.id}?{_q(world.org)}").get_data(as_text=True)

    for text in ("PSU-25/2569", "[TEST] License A", "[TEST] MA B", "1204010101 สินทรัพย์ไม่มีตัวตน", "ยี่ห้อ A", "ยี่ห้อ B", "รุ่น A", "S/N: ABC-002", "บริษัท ผู้ชนะ"):
        assert text in html
    assert "whitespace-pre-line" in html and "S/N: ABC-001\nรหัสครุภัณฑ์: CC/1" in html
    assert "[TEST] ฝ่ายไอที" in html and "[TEST] ฝ่ายการเงิน" in html


def _sub_item_rows(count):
    return [{"brand": f"ยี่ห้อ {i}", "model_name": f"รุ่น {i}", "details": f"S/N: SN-{i}"} for i in range(count)]


def test_create_ignores_fully_empty_sub_item_rows(world, client_for):
    rows = [{"brand": "", "model_name": "", "details": ""}, {"brand": " ", "model_name": "", "details": "  \n"}]
    rows += _sub_item_rows(1)
    data = ma_form([_item(amount="100000.00", sub_items=rows)])

    assert _create(client_for(world.admin), world, data).status_code == 302

    item = models.ProcurementItem.objects.get()
    assert [row.details for row in item.sub_items] == ["S/N: SN-0"]


def test_create_accepts_100_sub_items_and_rejects_101(world, client_for):
    ok = ma_form([_item(amount="100000.00", sub_items=_sub_item_rows(100))])
    assert _create(client_for(world.admin), world, ok).status_code == 302
    assert len(models.ProcurementItem.objects.get().sub_items) == 100

    response = _create(client_for(world.admin), world, ma_form([_item(amount="100000.00", sub_items=_sub_item_rows(101))], psu="PSU-2"))

    assert response.status_code == 200
    assert "จำนวนแถวยี่ห้อ / รุ่น / รายละเอียดต้องไม่เกิน 100 แถว" in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 1


def test_create_rejects_too_long_brand(world, client_for):
    rows = [{"brand": "x" * 101, "model_name": "", "details": ""}]

    response = _create(client_for(world.admin), world, ma_form([_item(amount="100000.00", sub_items=rows)]))

    assert response.status_code == 200
    assert models.Procurement.objects.count() == 0


def test_edit_adds_removes_and_changes_sub_items(world, client_for, create_ma):
    item = _model_item("1000.00", responsible=[world.role_admin])
    item.sub_items = [
        models.ItemDetail(brand="เดิม 1", details="S/N: OLD-1"),
        models.ItemDetail(brand="เดิม 2", details="S/N: OLD-2"),
    ]
    procurement = create_ma(world.org, user=world.admin, name="[TEST] MA", total_amount="1000.00", items=[item])
    item = procurement.get_items()[0]
    rows = [
        {"brand": "เดิม 1 แก้", "model_name": "รุ่นใหม่", "details": "S/N: OLD-1"},
        {"brand": "ใหม่ 3", "model_name": "", "details": "S/N: NEW-3"},
    ]
    data = ma_form(
        [
            _item(
                item_id=str(item.id),
                name=item.name,
                amount="1000.00",
                sub_items=rows,
                responsible_by=[str(world.role_admin.id)],
                installments=[{"installment_id": str(item.installments[0]._id), "due_date": "2026-12-31"}],
            )
        ],
        total_amount="1000.00",
        version=procurement.get_version(),
    )

    response = client_for(world.admin).post(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}", data=data)

    assert response.status_code == 302
    item.reload()
    assert [(row.brand, row.model_name, row.details) for row in item.sub_items] == [
        ("เดิม 1 แก้", "รุ่นใหม่", "S/N: OLD-1"),
        ("ใหม่ 3", None, "S/N: NEW-3"),
    ]


def test_edit_form_prefills_sub_items(world, client_for, create_ma):
    item = _model_item("1000.00", responsible=[world.role_admin])
    item.sub_items = [models.ItemDetail(brand="ยี่ห้อ-EDIT", model_name="รุ่น-EDIT", details="S/N: EDIT-1")]
    procurement = create_ma(world.org, user=world.admin, name="[TEST] MA", total_amount="1000.00", items=[item])

    html = client_for(world.admin).get(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}").get_data(as_text=True)

    assert 'name="items-0-sub_items-0-brand"' in html and "ยี่ห้อ-EDIT" in html
    assert 'name="items-0-sub_items-0-model_name"' in html and "รุ่น-EDIT" in html
    assert 'name="items-0-sub_items-0-details"' in html and "S/N: EDIT-1" in html


def test_create_page_shows_sub_item_section_open_and_with_row_template(world, client_for):
    html = client_for(world.admin).get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True)

    heading = html.index("ยี่ห้อ / รุ่น / รายละเอียด")
    # ส่วนนี้ต้องไม่อยู่ใน <details> ที่พับไว้ และเริ่มต้นมี 1 แถวว่างให้เห็นช่อง
    open_details = html[:heading].count("<details") - html[:heading].count("</details>")
    assert open_details == 0
    assert 'name="items-0-sub_items-0-brand"' in html
    assert 'name="items-0-sub_items-0-details"' in html
    assert 'data-action="add-sub-item"' in html
    assert "items-0-sub_items-__K__-brand" in html and "items-__I__-sub_items-__K__-details" in html
    assert "รายละเอียดเพิ่มเติม" not in html


def test_detail_page_hides_sub_item_table_when_item_has_none(world, client_for, existing_ma):
    html = client_for(world.admin).get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)

    assert "sub-items-table" not in html


@pytest.mark.parametrize(
    "amounts, message",
    [
        (("60000.00", "35000.00"), "ผลรวมรายการย่อย 95,000.00 บาท ไม่ตรงกับยอด MA 100,000.00 บาท (ขาด 5,000.00 บาท)"),
        (("60000.00", "40000.01"), "ผลรวมรายการย่อย 100,000.01 บาท ไม่ตรงกับยอด MA 100,000.00 บาท (เกิน 0.01 บาท)"),
    ],
)
def test_create_sum_mismatch_saves_nothing_and_shows_difference(world, client_for, amounts, message):
    data = ma_form([_item(amount=amounts[0]), _item(amount=amounts[1])])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0
    assert models.ProcurementItem.objects.count() == 0


@pytest.mark.parametrize("field", ["total_amount", "items-0-amount", "items-0-unit_price"])
def test_create_rejects_money_with_more_than_two_decimals(world, client_for, field):
    data = ma_form([_item(amount="100000.00")])
    data[field] = "1.234"

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    assert MONEY_PLACES_ERROR in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0


def test_create_zero_amount_item_with_one_installment_ok(world, client_for):
    data = ma_form([_item(amount="0")], total_amount="0")

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 302
    item = models.ProcurementItem.objects.get()
    assert item.amount == Decimal("0")
    assert len(item.installments) == 1


def test_create_item_without_installment_rejected(world, client_for):
    data = ma_form([_item(amount="100000.00", installment_mode="y", installments=[])])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    assert "กรุณาระบุวันครบกำหนด" in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0


def test_create_requires_psu_disbursement_number(world, client_for):
    response = _create(client_for(world.admin), world, ma_form([_item(amount="100000.00")], psu=""))

    assert response.status_code == 200
    assert models.Procurement.objects.count() == 0


def test_create_rejects_responsible_from_other_org(world, client_for):
    data = ma_form([_item(amount="100000.00", responsible_by=[str(world.role_admin_b.id)])])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    assert "ผู้รับผิดชอบต้องเป็นสมาชิกของหน่วยงานนี้" in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0


def test_create_form_defaults_responsible_to_current_member(world, client_for):
    html = client_for(world.admin).get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True)

    checked = re.findall(r'name="items-0-responsible_by" value="([0-9a-f]+)"\s+checked', html)
    assert checked == [str(world.role_admin.id)]
    # ตัวเลือกผู้รับผิดชอบมีเฉพาะสมาชิกของหน่วยงานนี้
    assert str(world.role_admin_b.id) not in html


@pytest.mark.parametrize("roles", (["staff"], ["head"], ["manager"], ["endorser"], ["driver"], ["director"], ["supervisor supplier"]))
def test_any_active_member_can_create_ma_and_then_edit_it(world, client_for, assign_user_to_org, create_user, roles):
    user = create_user("Member", "Tester")
    role = assign_user_to_org(user, world.org, roles=roles)
    client = client_for(user)

    response = _create(client, world, ma_form([_item(amount="100000.00", responsible_by=[str(role.id)])]))

    assert response.status_code == 302
    procurement = models.Procurement.objects.get()
    assert procurement.created_by.id == user.id
    # ผู้สร้างแก้ไขและเห็น MA ของตัวเองได้เสมอ แม้ role จะไม่ใช่กลุ่มเห็นทั้งหน่วยงาน
    assert client.get(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}").status_code == 200


def test_member_filter_script_targets_an_existing_container(world, client_for):
    """ช่องค้นหาผู้รับผิดชอบกรองด้วย closest('[data-member-picker]') ต้องมี container นั้นอยู่จริงรอบช่องค้นหา"""
    html = client_for(world.admin).get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True)

    assert "closest('[data-member-picker]')" in html
    picker = html.split("data-member-picker", 1)[1].split("</section>", 1)[0]
    assert "member-filter" in picker and "member-option" in picker


def test_create_page_button_is_shown_to_every_member(world, client_for):
    html = client_for(world.creator).get(f"/procurement/products?{_q(world.org)}").get_data(as_text=True)

    assert f"/procurement/products/create?{_q(world.org)}" in html


def test_create_refused_for_other_org_member_and_removed_member(world, client_for, assign_user_to_org, create_user):
    removed = create_user("Removed", "Tester")
    role = assign_user_to_org(removed, world.org, roles=["staff"])
    role.status = "disactive"
    role.save()

    for user in (world.admin_b, removed):
        response = _create(client_for(user), world, ma_form([_item(amount="100000.00")]))
        assert response.status_code in (302, 403, 404)
    assert models.Procurement.objects.count() == 0


# ---------------------------------------------------------------------------
# model: save_with_items เป็นทางบันทึกเดียว
# ---------------------------------------------------------------------------


def _model_item(amount, responsible=(), installments=None):
    return models.ProcurementItem(
        name="[TEST] รายการ",
        category="service",
        amount=Decimal(amount),
        start_date=datetime.datetime(2026, 1, 1),
        end_date=datetime.datetime(2026, 12, 31),
        responsible_by=list(responsible),
        installments=installments if installments is not None else [models.Installment(due_date=datetime.datetime(2026, 12, 31))],
    )


def _header(organization, total="100.00"):
    return models.Procurement(name="[TEST] MA", company="บริษัท", total_amount=Decimal(total), organization=organization)


def test_save_with_items_sum_mismatch_raises_before_writing(world):
    procurement = _header(world.org, "100.00")

    with pytest.raises(me.ValidationError) as error:
        procurement.save_with_items([_model_item("60.00"), _model_item("39.99")])

    assert "ขาด 0.01 บาท" in str(error.value)
    assert procurement.pk is None
    assert models.Procurement.objects.count() == 0
    assert models.ProcurementItem.objects.count() == 0


def test_save_with_items_rejects_item_without_installment(world):
    with pytest.raises(me.ValidationError):
        _header(world.org).save_with_items([_model_item("100.00", installments=[])])

    assert models.Procurement.objects.count() == 0


def test_save_with_items_rejects_responsible_from_other_org(world):
    with pytest.raises(me.ValidationError):
        _header(world.org).save_with_items([_model_item("100.00", responsible=[world.role_admin_b])])

    assert models.Procurement.objects.count() == 0
    assert models.ProcurementItem.objects.count() == 0


def test_save_with_items_cleans_up_when_item_write_fails(world, monkeypatch):
    original_save = models.ProcurementItem.save
    calls = []

    def flaky_save(self, *args, **kwargs):
        calls.append(self)
        if len(calls) == 2:
            raise RuntimeError("db down")
        return original_save(self, *args, **kwargs)

    monkeypatch.setattr(models.ProcurementItem, "save", flaky_save)
    with pytest.raises(RuntimeError):
        _header(world.org).save_with_items([_model_item("60.00"), _model_item("40.00")])

    assert models.Procurement.objects.count() == 0
    assert models.ProcurementItem.objects.count() == 0


def test_responsible_divisions_follow_responsible_members(world):
    procurement = _header(world.org)
    item = _model_item("100.00", responsible=[world.role_admin, world.role_creator, world.role_responsible])
    procurement.save_with_items([item])

    item.reload()
    assert sorted(division.name for division in item.responsible_divisions) == ["[TEST] ฝ่ายการเงิน", "[TEST] ฝ่ายไอที"]

    item.responsible_by = [world.role_responsible]
    procurement.save_with_items([item])
    item.reload()
    assert [division.name for division in item.responsible_divisions] == ["[TEST] ฝ่ายการเงิน"]


# ---------------------------------------------------------------------------
# สถานะงวด
# ---------------------------------------------------------------------------

TODAY = datetime.date(2026, 6, 1)


@pytest.mark.parametrize(
    "due_date, paid_date, expected",
    [
        (datetime.datetime(2026, 5, 31), None, "overdue"),
        (datetime.datetime(2026, 6, 1), None, "upcoming"),
        (datetime.datetime(2026, 6, 8), None, "upcoming"),
        (datetime.datetime(2026, 6, 9), None, "unpaid"),
        (datetime.datetime(2026, 5, 1), datetime.datetime(2026, 5, 2), "paid"),
    ],
)
def test_installment_status(due_date, paid_date, expected):
    installment = models.Installment(due_date=due_date, paid_date=paid_date)

    assert installment.get_status(TODAY) == expected


def test_item_and_header_status_use_worst_unpaid_installment(world):
    paid = models.Installment(due_date=datetime.datetime(2026, 1, 1), paid_date=datetime.datetime(2026, 1, 1))
    later = models.Installment(due_date=datetime.datetime(2026, 12, 1))
    soon = models.Installment(due_date=datetime.datetime(2026, 6, 5))
    item_a = _model_item("50.00", installments=[paid, later])
    item_b = _model_item("50.00", installments=[later.__class__(due_date=later.due_date), soon])
    procurement = _header(world.org)
    procurement.save_with_items([item_a, item_b])

    assert item_a.get_payment_status(TODAY) == "unpaid"
    assert item_b.get_payment_status(TODAY) == "upcoming"
    assert procurement.get_payment_status(TODAY) == "upcoming"
    assert procurement.get_installment_progress() == (1, 4)
    next_item, next_installment = procurement.get_next_unpaid()
    assert next_item is item_b and next_installment.due_date == datetime.datetime(2026, 6, 5)

    for installment in item_a.installments + item_b.installments:
        installment.paid_date = datetime.datetime(2026, 6, 1)
    assert procurement.get_payment_status(TODAY) == "paid"


def test_even_due_dates_end_on_end_date():
    dates = models.procurement.even_due_dates(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), 4)

    assert dates == [
        datetime.date(2026, 4, 2),
        datetime.date(2026, 7, 2),
        datetime.date(2026, 10, 1),
        datetime.date(2026, 12, 31),
    ]


# ---------------------------------------------------------------------------
# แก้ไข MA: กติกา "ผู้แก้ไข MA ได้"
# ---------------------------------------------------------------------------


@pytest.fixture
def existing_ma(world, create_ma):
    return create_ma(
        world.org,
        user=world.creator,
        name="[TEST] MA เดิม",
        status="pending",
        responsible=[world.role_responsible],
        total_amount="1000.00",
    )


def _edit_form(procurement, total="1000.00", name="[TEST] MA แก้แล้ว"):
    item = procurement.get_items()[0]
    return ma_form(
        [
            _item(
                item_id=str(item.id),
                name=item.name,
                amount=total,
                responsible_by=[str(member.id) for member in item.responsible_by],
                installments=[{"installment_id": str(item.installments[0]._id), "due_date": "2026-12-31"}],
            )
        ],
        total_amount=total,
        name=name,
        version=procurement.get_version(),
    )


@pytest.mark.parametrize("who", ["admin", "creator", "responsible"])
def test_edit_allowed_for_admin_creator_and_item_responsible(world, client_for, existing_ma, who):
    client = client_for(getattr(world, who))
    url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"

    assert client.get(url).status_code == 200
    response = client.post(url, data=_edit_form(existing_ma))

    assert response.status_code == 302
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA แก้แล้ว"
    assert models.ProcurementItem.objects(procurement=existing_ma).count() == 1


def test_edit_refused_for_viewer_who_is_not_creator_or_responsible(world, client_for, existing_ma):
    client = client_for(world.head)
    url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"

    get_response = client.get(url)
    post_response = client.post(url, data=_edit_form(existing_ma))

    for response in (get_response, post_response):
        assert response.status_code == 302
        assert f"/procurement/payment/{existing_ma.id}" in response.headers["Location"]
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"


def test_edit_by_staff_who_cannot_see_ma_is_404(world, client_for, existing_ma):
    client = client_for(world.other_staff)
    url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"

    assert client.get(url).status_code == 404
    assert client.post(url, data=_edit_form(existing_ma)).status_code == 404
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"


def test_edit_other_org_ma_is_404(world, client_for, existing_ma, assign_user_to_org):
    client = client_for(world.admin_b)
    url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.other_org)}"

    assert client.get(url).status_code == 404
    assert client.post(url, data=_edit_form(existing_ma)).status_code == 404
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"


def test_edit_removing_item_deletes_it_and_keeps_item_ids(world, client_for, create_ma):
    first = _model_item("60.00")
    second = _model_item("40.00")
    procurement = create_ma(world.org, user=world.admin, total_amount="100.00", items=[first, second])
    installment_id = first.installments[0]._id
    data = ma_form(
        [
            _item(
                item_id=str(first.id),
                amount="100.00",
                installments=[{"installment_id": str(first.installments[0]._id), "due_date": "2026-12-31"}],
            )
        ],
        total_amount="100.00",
        version=procurement.get_version(),
    )

    response = client_for(world.admin).post(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}", data=data)

    assert response.status_code == 302
    assert [item.id for item in models.ProcurementItem.objects(procurement=procurement)] == [first.id]
    first.reload()
    assert first.amount == Decimal("100.00")
    assert first.installments[0]._id == installment_id


def test_edit_cannot_adopt_item_of_another_ma(world, client_for, create_ma):
    victim = create_ma(world.org, user=world.admin, name="[TEST] MA อื่น", total_amount="100.00")
    victim_item = victim.get_items()[0]
    target = create_ma(world.org, user=world.admin, name="[TEST] MA เป้าหมาย", total_amount="100.00")
    data = ma_form(
        [_item(item_id=str(victim_item.id), amount="100.00")], total_amount="100.00", version=target.get_version()
    )

    client_for(world.admin).post(f"/procurement/products/{target.id}/edit?{_q(world.org)}", data=data)

    victim_item.reload()
    assert victim_item.procurement.id == victim.id
    assert models.ProcurementItem.objects(procurement=victim).count() == 1


def test_edit_sum_mismatch_keeps_existing_data(world, client_for, existing_ma):
    data = _edit_form(existing_ma, total="1000.00")
    data["items-0-amount"] = "999.00"

    response = client_for(world.admin).post(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=data)

    assert response.status_code == 200
    assert "ขาด 1.00 บาท" in response.get_data(as_text=True)
    assert models.ProcurementItem.objects(procurement=existing_ma).get().amount == Decimal("1000.00")


def test_edit_with_stale_form_is_rejected_and_keeps_payment(world, client_for, existing_ma):
    stale_form = _edit_form(existing_ma)
    client_for(world.responsible).post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-STALE"},
    )

    response = client_for(world.admin).post(
        f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=stale_form
    )

    assert response.status_code == 200
    assert "ถูกแก้ไขหรือบันทึกจ่ายงวดโดยผู้อื่น" in response.get_data(as_text=True)
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"
    assert _first_installment(existing_ma).payment_number == "PAY-STALE"


def test_edit_keeps_paid_state_and_pay_log_of_paid_installment(world, client_for, existing_ma):
    client_for(world.responsible).post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-KEEP", "paid_amount": "10.50"},
    )
    existing_ma = models.Procurement.objects.get(id=existing_ma.id)
    data = _edit_form(existing_ma)
    # ฟอร์มแก้ไขไม่มีช่องการจ่าย: ค่าที่ส่งมาเกินจากฟอร์มต้องไม่ทับสถานะที่บันทึกไว้
    data["items-0-installments-0-paid_date"] = ""
    data["items-0-installments-0-payment_number"] = "HACK"

    response = client_for(world.admin).post(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=data)

    assert response.status_code == 302
    installment = _first_installment(existing_ma)
    assert installment.paid_date == datetime.datetime(2026, 11, 1)
    assert installment.payment_number == "PAY-KEEP"
    assert installment.paid_amount == Decimal("10.50")
    assert installment.paid_by.id == world.responsible.id
    assert [entry.action for entry in installment.pay_log] == ["paid"]


# ---------------------------------------------------------------------------
# ค้นหาในหน้ารายการ MA
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyword", ["PSU-SEARCH", "หัวสัญญาค้นได้", "รายการย่อยค้นได้", "SN-XYZ-99", "ยี่ห้อค้นได้", "รุ่นค้นได้"]
)
def test_products_search_matches_psu_header_item_name_and_sub_items(world, client_for, create_ma, keyword):
    item = _model_item("100.00")
    item.name = "[TEST] รายการย่อยค้นได้"
    item.sub_items = [models.ItemDetail(brand="ยี่ห้อค้นได้", model_name="รุ่นค้นได้", details="S/N: SN-XYZ-99")]
    create_ma(world.org, user=world.admin, name="[TEST] หัวสัญญาค้นได้", psu_disbursement_number="PSU-SEARCH-1", total_amount="100.00", items=[item])
    create_ma(world.org, user=world.admin, name="[TEST] MA ไม่เกี่ยว", psu_disbursement_number="OTHER-1", total_amount="1000.00")

    html = client_for(world.admin).get(f"/procurement/products?{_q(world.org)}&name={keyword}").get_data(as_text=True)

    assert "[TEST] หัวสัญญาค้นได้" in html
    assert "[TEST] MA ไม่เกี่ยว" not in html


def test_products_search_does_not_leak_other_org(world, client_for, create_ma):
    item_b = _model_item("100.00")
    item_b.sub_items = [models.ItemDetail(brand="BRAND-SECRET-B", details="S/N: SECRET-B")]
    create_ma(world.other_org, user=world.admin_b, name="[TEST] MA ของ B", psu_disbursement_number="SECRET-B", total_amount="100.00", items=[item_b])

    for keyword in ("SECRET-B", "BRAND-SECRET-B", "MA ของ B"):
        html = client_for(world.admin).get(f"/procurement/products?{_q(world.org)}&name={keyword}").get_data(as_text=True)
        assert "[TEST] MA ของ B" not in html


def test_staff_sees_only_ma_where_responsible_in_any_item(world, client_for, create_ma):
    mine = _model_item("50.00", responsible=[world.role_other_staff])
    not_mine = _model_item("50.00", responsible=[world.role_responsible])
    create_ma(world.org, user=world.admin, name="[TEST] MA ที่ฉันดูแล", total_amount="100.00", items=[not_mine, mine])
    create_ma(world.org, user=world.admin, name="[TEST] MA ของคนอื่น", total_amount="1000.00")

    html = client_for(world.other_staff).get(f"/procurement/products?{_q(world.org)}").get_data(as_text=True)

    assert "[TEST] MA ที่ฉันดูแล" in html
    assert "[TEST] MA ของคนอื่น" not in html


# ---------------------------------------------------------------------------
# บันทึกจ่าย / ยกเลิกจ่ายรายงวด
# ---------------------------------------------------------------------------


def _installment_url(procurement, action):
    item = procurement.get_items()[0]
    installment = item.installments[0]
    return f"/procurement/payment/{procurement.id}/items/{item.id}/installments/{installment._id}/{action}"


def _first_installment(procurement):
    return models.ProcurementItem.objects(procurement=procurement).get().installments[0]


def test_pay_and_undo_installment(world, client_for, existing_ma):
    client = client_for(world.responsible)

    response = client.post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-001", "paid_amount": "999.50"},
    )

    assert response.status_code == 302
    installment = _first_installment(existing_ma)
    assert installment.paid_date == datetime.datetime(2026, 11, 1)
    assert installment.paid_by.id == world.responsible.id
    assert installment.payment_number == "PAY-001"
    assert installment.paid_amount == Decimal("999.50")

    response = client.post(f"{_installment_url(existing_ma, 'unpay')}?{_q(world.org)}")

    assert response.status_code == 302
    installment = _first_installment(existing_ma)
    assert installment.paid_date is None
    assert installment.paid_by is None
    assert installment.payment_number is None
    assert installment.paid_amount is None


@pytest.mark.parametrize("action", ["pay", "unpay"])
def test_installment_actions_reject_get(world, client_for, existing_ma, action):
    response = client_for(world.admin).get(f"{_installment_url(existing_ma, action)}?{_q(world.org)}")

    assert response.status_code == 405


def test_pay_refused_for_user_who_cannot_edit(world, client_for, existing_ma):
    response = client_for(world.head).post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}", data={"paid_date": "2026-11-01"}
    )

    assert response.status_code == 302
    assert _first_installment(existing_ma).paid_date is None


def test_pay_rejects_more_than_two_decimals(world, client_for, existing_ma):
    client_for(world.admin).post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "paid_amount": "1.234"},
    )

    assert _first_installment(existing_ma).paid_date is None


def test_pay_duplicate_payment_number_rejected_in_same_org_only(world, client_for, create_ma, existing_ma):
    other_same_org = create_ma(world.org, user=world.admin, name="[TEST] MA 2")
    other_org = create_ma(world.other_org, user=world.admin_b, name="[TEST] MA B")
    admin_client = client_for(world.admin)
    admin_client.post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}", data={"paid_date": "2026-11-01", "payment_number": "DUP-1"}
    )

    admin_client.post(
        f"{_installment_url(other_same_org, 'pay')}?{_q(world.org)}", data={"paid_date": "2026-11-01", "payment_number": "DUP-1"}
    )
    client_for(world.admin_b).post(
        f"{_installment_url(other_org, 'pay')}?{_q(world.other_org)}", data={"paid_date": "2026-11-01", "payment_number": "DUP-1"}
    )

    assert _first_installment(other_same_org).paid_date is None
    assert _first_installment(other_org).payment_number == "DUP-1"
    # แก้การจ่ายของงวดเดิมด้วยเลขเดิมได้
    admin_client.post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}", data={"paid_date": "2026-11-02", "payment_number": "DUP-1"}
    )
    assert _first_installment(existing_ma).paid_date == datetime.datetime(2026, 11, 2)


def test_detail_hides_edit_and_pay_buttons_from_viewer(world, client_for, existing_ma):
    edit_url = f"/procurement/products/{existing_ma.id}/edit"
    detail_url = f"/procurement/payment/{existing_ma.id}?{_q(world.org)}"

    viewer_response = client_for(world.head).get(detail_url)
    viewer_html = viewer_response.get_data(as_text=True)
    editor_html = client_for(world.responsible).get(detail_url).get_data(as_text=True)

    assert viewer_response.status_code == 200
    assert edit_url not in viewer_html and "/pay?" not in viewer_html
    assert edit_url in editor_html and "/pay?" in editor_html


# ---------------------------------------------------------------------------
# ไม่ต่ออายุ: ใช้กติกาผู้แก้ไข MA ได้
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("who, allowed", [("creator", True), ("responsible", True), ("admin", True), ("head", False)])
def test_non_renewal_action_uses_can_edit_rule(world, client_for, existing_ma, who, allowed):
    response = client_for(getattr(world, who)).post(
        f"/procurement/requisitions/{existing_ma.id}/non-renewal?{_q(world.org)}"
    )

    assert response.status_code == 302
    existing_ma.reload()
    assert existing_ma.status == ("disactive" if allowed else "pending")


def test_ma_renewal_list_renders_items_info(world, client_for, existing_ma):
    html = client_for(world.admin).get(
        f"/procurement/requisitions?{_q(world.org)}&expiration_date_range=3_months"
    ).get_data(as_text=True)

    assert "[TEST] MA เดิม" in html
    assert "PSU-0001" in html


# ---------------------------------------------------------------------------
# นำเข้า Excel / controller / อีเมล
# ---------------------------------------------------------------------------


def _ma_excel(rows):
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def _excel_row(**overrides):
    row = {
        "เลขที่ ม.อ.เบิกจ่าย": "PSU-IMPORT-1",
        "เลขที่สินค้า/เลขที่เอกสาร": "SN-IMPORT",
        "ชื่อรายการ": "[TEST] นำเข้า",
        "รหัสครุภัณฑ์": "AC-IMPORT",
        "วันที่เริ่มต้น": "01/01/2026",
        "วันที่สิ้นสุด": "31/12/2026",
        "จำนวนเงิน(บาท)": 1200,
        "จำนวนงวด": 4,
        "ประเภท": "ซอฟต์แวร์",
        "ผู้รับผิดชอบ": "Responsible Tester",
        "บริษัท": "[TEST] บริษัท",
    }
    row.update(overrides)
    return row


def _upload_document(world, rows):
    document = models.Document(
        organization=world.org,
        category="ma",
        created_by=world.admin,
        updated_by=world.admin,
    )
    document.file.put(_ma_excel(rows), filename="ma.xlsx")
    document.save()
    return document


def test_upload_save_ma_db_creates_header_and_item(world, gridfs_enabled):
    document = _upload_document(world, [_excel_row(), _excel_row()])

    upload_files.save_ma_db(document, None, world.admin.id)

    procurement = models.Procurement.objects.get()
    assert procurement.psu_disbursement_number == "PSU-IMPORT-1"
    assert procurement.total_amount == Decimal("1200")
    item = models.ProcurementItem.objects.get()
    assert item.procurement.id == procurement.id
    assert [(row.brand, row.model_name, row.details) for row in item.sub_items] == [
        (None, None, "S/N: SN-IMPORT\nรหัสครุภัณฑ์: AC-IMPORT")
    ]
    assert [member.id for member in item.responsible_by] == [world.role_responsible.id]
    assert len(item.installments) == 4
    assert item.installments[-1].due_date == datetime.datetime(2026, 12, 31)
    document.reload()
    # แถวที่ 2 ซ้ำกับแถวแรก
    assert document.status == "incomplete"
    assert document.error_messages == ["แถวที่ 3: ข้อมูลซ้ำกับที่มีในระบบแล้ว"]


def test_upload_optional_brand_and_model_columns_go_into_the_sub_row(world, gridfs_enabled):
    document = _upload_document(world, [_excel_row(**{"ยี่ห้อ": "Dell", "รุ่น": "X1"})])

    upload_files.save_ma_db(document, None, world.admin.id)

    item = models.ProcurementItem.objects.get()
    assert [(row.brand, row.model_name, row.details) for row in item.sub_items] == [
        ("Dell", "X1", "S/N: SN-IMPORT\nรหัสครุภัณฑ์: AC-IMPORT")
    ]


def test_upload_without_sn_asset_brand_or_model_creates_no_sub_row(world, gridfs_enabled):
    document = _upload_document(world, [_excel_row(**{"เลขที่สินค้า/เลขที่เอกสาร": "", "รหัสครุภัณฑ์": ""})])

    upload_files.save_ma_db(document, None, world.admin.id)

    assert models.ProcurementItem.objects.get().sub_items == []


def test_upload_responsible_lookup_is_scoped_to_document_org(world, gridfs_enabled):
    world.role_admin_b.first_name = "Foreign"
    world.role_admin_b.last_name = "Member"
    world.role_admin_b.save()
    document = _upload_document(world, [_excel_row(**{"ผู้รับผิดชอบ": "Foreign Member"})])

    upload_files.save_ma_db(document, None, world.admin.id)

    assert models.ProcurementItem.objects.get().responsible_by == []


def test_procurement_status_moves_only_active_ma_near_expiry_to_pending(world, create_ma):
    active = create_ma(world.org, user=world.admin, status="active")
    stopped = create_ma(world.org, user=world.admin, status="disactive")
    updater = ProcurementStatusUpdater.__new__(ProcurementStatusUpdater)

    for procurement in (active, stopped):
        asyncio.run(updater.process_data({"procurement_id": procurement.id}))

    active.reload()
    stopped.reload()
    assert active.status == "pending"
    assert stopped.status == "disactive"


# ---------------------------------------------------------------------------
# CSRF: POST ที่เปลี่ยนสถานะต้องมี token (แอปไม่มี CSRFProtect ทั้งระบบ ตรวจผ่าน FlaskForm เท่านั้น)
# ---------------------------------------------------------------------------


@pytest.fixture
def csrf_enabled(app, monkeypatch):
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)


def _csrf_token(html):
    match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert match, "หน้าเว็บไม่ได้ render csrf_token"
    return match.group(1)


def _pay(client, world, procurement, **data):
    data.setdefault("paid_date", "2026-11-01")
    return client.post(f"{_installment_url(procurement, 'pay')}?{_q(world.org)}", data=data)


def test_unpay_without_csrf_token_is_refused(world, client_for, existing_ma, csrf_enabled, monkeypatch):
    client = client_for(world.responsible)
    with monkeypatch.context() as patch:
        patch.setitem(client.application.config, "WTF_CSRF_ENABLED", False)
        _pay(client, world, existing_ma, payment_number="PAY-CSRF")

    client.post(f"{_installment_url(existing_ma, 'unpay')}?{_q(world.org)}")

    assert _first_installment(existing_ma).payment_number == "PAY-CSRF"


def test_unpay_with_csrf_token_from_detail_page(world, client_for, existing_ma, csrf_enabled, monkeypatch):
    client = client_for(world.responsible)
    with monkeypatch.context() as patch:
        patch.setitem(client.application.config, "WTF_CSRF_ENABLED", False)
        _pay(client, world, existing_ma, payment_number="PAY-CSRF")
    token = _csrf_token(client.get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True))

    client.post(f"{_installment_url(existing_ma, 'unpay')}?{_q(world.org)}", data={"csrf_token": token})

    assert _first_installment(existing_ma).paid_date is None


def test_non_renewal_without_csrf_token_is_refused(world, client_for, existing_ma, csrf_enabled):
    client_for(world.admin).post(f"/procurement/requisitions/{existing_ma.id}/non-renewal?{_q(world.org)}")

    existing_ma.reload()
    assert existing_ma.status == "pending"


def test_non_renewal_with_csrf_token_from_renewal_list(world, client_for, existing_ma, csrf_enabled):
    client = client_for(world.admin)
    html = client.get(f"/procurement/requisitions?{_q(world.org)}").get_data(as_text=True)
    assert f"/procurement/requisitions/{existing_ma.id}/non-renewal" in html

    client.post(
        f"/procurement/requisitions/{existing_ma.id}/non-renewal?{_q(world.org)}",
        data={"csrf_token": _csrf_token(html)},
    )

    existing_ma.reload()
    assert existing_ma.status == "disactive"


def test_other_ma_posts_without_csrf_token_change_nothing(world, client_for, existing_ma, csrf_enabled):
    client = client_for(world.admin)
    item = existing_ma.get_items()[0]

    _pay(client, world, existing_ma, payment_number="PAY-NO-TOKEN")
    client.post(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=_edit_form(existing_ma))
    client.post(
        f"/procurement/reminder_logs/{existing_ma.id}/items/{item.id}/manual?{_q(world.org)}",
        data={"contact_date": "01/11/2569", "note": "โทรแจ้ง"},
    )
    client.post(f"/procurement/products/{existing_ma.id}/renew?{_q(world.org)}", data=_edit_form(existing_ma))
    _create(client, world, _two_item_form(world))

    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม" and existing_ma.status == "pending"
    assert _first_installment(existing_ma).paid_date is None
    assert models.ReminderLog.objects.count() == 0
    assert models.Procurement.objects.count() == 1


# ---------------------------------------------------------------------------
# input ที่ประกอบขึ้นเองต้องไม่ทำให้ 500 / บันทึกจ่ายที่ไม่ได้เขียนอะไรต้องไม่แจ้งว่าสำเร็จ
# ---------------------------------------------------------------------------


def _flashes(client):
    with client.session_transaction() as session:
        return list(session.get("_flashes", []))


@pytest.mark.parametrize("action", ["pay", "unpay"])
@pytest.mark.parametrize("bad", ["item", "installment"])
def test_installment_action_with_non_objectid_is_404(world, client_for, existing_ma, action, bad):
    item = existing_ma.get_items()[0]
    item_id = "not-an-id" if bad == "item" else item.id
    installment_id = "not-an-id" if bad == "installment" else item.installments[0]._id

    response = client_for(world.admin).post(
        f"/procurement/payment/{existing_ma.id}/items/{item_id}/installments/{installment_id}/{action}?{_q(world.org)}",
        data={"paid_date": "2026-11-01"},
    )

    assert response.status_code == 404


@pytest.mark.parametrize("amount", ["sNaN", "NaN", "Infinity", "-Infinity", "snan"])
def test_pay_with_non_finite_amount_is_a_validation_error(world, client_for, existing_ma, amount):
    client = client_for(world.admin)

    response = _pay(client, world, existing_ma, paid_amount=amount)

    assert response.status_code == 302
    assert _first_installment(existing_ma).paid_date is None
    assert [category for category, _ in _flashes(client)] == ["error"]


@pytest.mark.parametrize("amount", ["sNaN", "NaN", "Infinity"])
def test_ma_form_with_non_finite_amount_is_a_validation_error(world, client_for, existing_ma, amount):
    data = _edit_form(existing_ma)
    data["total_amount"] = amount
    data["items-0-amount"] = amount

    response = client_for(world.admin).post(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=data)

    assert response.status_code == 200
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"


@pytest.fixture
def installment_removed_before_write(monkeypatch):
    """จำลองคนอื่นลบงวดนี้ (แก้ MA) หลังจากเราโหลดงวดแล้ว แต่ก่อนเขียน"""
    from kampan.web.views.procurement import payment

    original = payment._get_installment_for_change

    def load_then_remove(*args):
        loaded = original(*args)
        item = loaded[2]
        models.ProcurementItem.objects(id=item.id).update_one(
            set__installments=[models.Installment(due_date=datetime.datetime(2026, 12, 31))]
        )
        return loaded

    monkeypatch.setattr(payment, "_get_installment_for_change", load_then_remove)


@pytest.mark.parametrize("action", ["pay", "unpay"])
def test_installment_action_that_writes_nothing_reports_error(
    world, client_for, existing_ma, installment_removed_before_write, action
):
    client = client_for(world.admin)

    client.post(f"{_installment_url(existing_ma, action)}?{_q(world.org)}", data={"paid_date": "2026-11-01"})

    assert _flashes(client) == [("error", "ไม่พบงวดนี้ หรือข้อมูลถูกแก้ไขแล้ว")]
    assert _first_installment(existing_ma).paid_date is None


# ---------------------------------------------------------------------------
# แก้ไข MA ชนกับการบันทึกจ่ายที่เกิดหลังตรวจ version แต่ก่อนเขียน
# ---------------------------------------------------------------------------


def _pay_directly(procurement, payment_number):
    """บันทึกจ่ายแบบเดียวกับ payment.pay_installment (positional update + ตั้ง updated_date)"""
    item = models.ProcurementItem.objects(procurement=procurement).get()
    models.ProcurementItem.objects(id=item.id, __raw__={"installments._id": item.installments[0]._id}).update_one(
        set__installments__S__paid_date=datetime.datetime(2026, 11, 1),
        set__installments__S__payment_number=payment_number,
        set__updated_date=datetime.datetime.now() + datetime.timedelta(seconds=1),
    )


def test_edit_refused_when_payment_lands_between_version_check_and_write(world, client_for, existing_ma, monkeypatch):
    original = models.Procurement.save_with_items

    def pay_then_save(self, *args, **kwargs):
        _pay_directly(existing_ma, "PAY-RACE")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(models.Procurement, "save_with_items", pay_then_save)

    response = client_for(world.admin).post(
        f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=_edit_form(existing_ma)
    )

    assert response.status_code == 200
    assert "ถูกแก้ไขหรือบันทึกจ่ายงวดโดยผู้อื่น" in response.get_data(as_text=True)
    assert _first_installment(existing_ma).payment_number == "PAY-RACE"
    existing_ma.reload()
    assert existing_ma.name == "[TEST] MA เดิม"


def test_save_with_items_rolls_back_header_when_an_item_changed_after_load(world):
    procurement = _header(world.org)
    procurement.save_with_items([_model_item("60.00"), _model_item("40.00")])
    loaded = models.Procurement.objects.get(id=procurement.id)
    first, second = loaded.get_items()
    models.ProcurementItem.objects(id=second.id).update_one(
        set__note="แก้โดยคนอื่น", set__updated_date=datetime.datetime.now() + datetime.timedelta(seconds=1)
    )

    loaded.name = "[TEST] แก้ทับ"
    first.note = "แก้ของเรา"
    second.note = "แก้ทับของคนอื่น"
    with pytest.raises(models.ConcurrentEditConflict):
        loaded.save_with_items([first, second])

    assert models.Procurement.objects.get(id=procurement.id).name == "[TEST] MA"
    assert models.ProcurementItem.objects.get(id=first.id).note != "แก้ของเรา"
    assert models.ProcurementItem.objects.get(id=second.id).note == "แก้โดยคนอื่น"


def test_save_with_items_refuses_when_header_changed_after_load(world):
    procurement = _header(world.org)
    procurement.save_with_items([_model_item("100.00")])
    loaded = models.Procurement.objects.get(id=procurement.id)
    models.Procurement.objects(id=procurement.id).update_one(
        set__status="pending", set__updated_date=datetime.datetime.now() + datetime.timedelta(seconds=1)
    )

    loaded.name = "[TEST] แก้ทับ"
    with pytest.raises(models.ConcurrentEditConflict):
        loaded.save_with_items(loaded.get_items())

    stored = models.Procurement.objects.get(id=procurement.id)
    assert (stored.name, stored.status) == ("[TEST] MA", "pending")


# ---------------------------------------------------------------------------
# จำนวนงวดต่อรายการย่อยไม่เกิน 120 (Excel และฟอร์ม)
# ---------------------------------------------------------------------------


def test_upload_rejects_more_than_120_installments(world, gridfs_enabled):
    document = _upload_document(
        world,
        [
            _excel_row(**{"จำนวนงวด": 121}),
            _excel_row(**{"ชื่อรายการ": "[TEST] 120 งวด", "จำนวนงวด": 120, "วันที่สิ้นสุด": "31/12/2035"}),
        ],
    )

    assert upload_files.validate_ma_file(document) == ["แถวที่ 2: จำนวนงวดต้องไม่เกิน 120"]

    upload_files.save_ma_db(document, None, world.admin.id)

    item = models.ProcurementItem.objects.get()
    assert item.name == "[TEST] 120 งวด" and len(item.installments) == 120
    document.reload()
    assert document.error_messages == ["แถวที่ 2: จำนวนงวดต้องไม่เกิน 120"]


def test_ma_form_rejects_more_than_120_installments(world, client_for):
    installments = [{"due_date": "2026-12-31"}] * 121
    data = ma_form([_item(amount="100000.00", installment_mode="y", installments=installments)])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    assert "จำนวนงวดต้องไม่เกิน 120" in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0


def test_ma_form_accepts_120_installments(world, client_for):
    data = ma_form([_item(amount="100000.00", installment_mode="y", installments=[{"due_date": "2026-12-31"}] * 120)])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 302
    assert len(models.ProcurementItem.objects.get().installments) == 120


# ---------------------------------------------------------------------------
# ตัวควบคุมฟอร์ม: ใช้ DaisyUI (date picker Cally, select ใน label.select) ไม่ใช้ของ native
# ---------------------------------------------------------------------------


def _picker_inputs(html):
    """คืน [(hidden input id/name/value, label text)] ของ date picker ทุกตัวนอก <template>"""
    html = re.sub(r"<template.*?</template>", "", html, flags=re.S)
    result = []
    for match in re.finditer(r'<div class="relative w-full" data-date-picker[^>]*data-input-id="([^"]+)"[^>]*data-label-id="([^"]+)"', html):
        input_id, label_id = match.groups()
        hidden = re.search(rf'<input type="hidden" id="{re.escape(input_id)}" name="([^"]+)"([^>]*)>', html)
        value = re.search(r'value="([^"]*)"', hidden.group(2))
        label = re.search(rf'id="{re.escape(label_id)}"[^>]*>\s*([^<]*?)\s*</span>', html)
        result.append((hidden.group(1), value.group(1) if value else "", label.group(1)))
    return result


def test_create_form_uses_daisyui_controls_not_native_date_or_bare_select(world, client_for):
    html = client_for(world.admin).get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True)

    assert 'type="date"' not in html
    form_html = html.split('id="ma_form"', 1)[1].split("</form>", 1)[0]
    assert "<select" not in form_html
    # ประเภท, ผังบัญชี และประเภทการเตือนเป็น dropdown ของ DaisyUI (hidden input เก็บค่าด้วย name เดิม)
    for name in ("items-0-category", "items-0-account_code", "items-0-reminder_kind"):
        assert re.search(rf'<input type="hidden" name="{name}" id="{name}"', form_html), name
    names = [name for name, _, _ in _picker_inputs(html)]
    assert "items-0-start_date" in names and "items-0-end_date" in names
    assert "items-0-installments-0-due_date" in names
    # แถวที่เพิ่มด้วย JS มาจาก <template> ซึ่งต้องมี container ให้ initDatePickersIn / initDropdownSelectsIn
    template = html.split('<template id="installment_template">', 1)[1].split("</template>", 1)[0]
    assert "data-date-picker" in template and "__J__" in template and 'type="date"' not in template
    item_template = html.split('<template id="item_template">', 1)[1].split("</template>", 1)[0]
    assert "data-dropdown-select" in item_template and "__I__" in item_template and "<select" not in item_template


def test_edit_form_shows_existing_dates_as_iso_value_and_buddhist_era_label(world, client_for, existing_ma):
    html = client_for(world.admin).get(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}").get_data(as_text=True)

    item = existing_ma.get_items()[0]
    pickers = {name: (value, label) for name, value, label in _picker_inputs(html)}

    def be(value):
        value = value.date() if hasattr(value, "date") else value
        return value.strftime("%Y-%m-%d"), f"{value.day:02d}/{value.month:02d}/{value.year + 543}"

    assert pickers["items-0-start_date"] == be(item.start_date)
    assert pickers["items-0-end_date"] == be(item.end_date)
    assert pickers["items-0-installments-0-due_date"] == be(item.installments[0].due_date)


def test_invalid_date_post_shows_error_and_error_style_on_picker(world, client_for):
    data = _two_item_form(world)
    data["items-0-end_date"] = "not-a-date"

    response = _create(client_for(world.admin), world, data)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    button = re.search(r'<button type="button" id="cally-items-0-end_date" class="([^"]*)"', html).group(1)
    assert "input-error" in button
    fieldset = html.split('id="field-items-0-end_date"', 1)[1].split("</fieldset>", 1)[0]
    assert "text-error" in fieldset


def test_create_and_edit_ma_with_separate_sn_and_asset_code(world, client_for):
    client = client_for(world.admin)
    data = ma_form([
        _item(
            amount="50000.00",
            has_sub_item_sn="y",
            has_sub_item_asset="y",
            sub_items=[
                {"brand": "Apple", "model_name": "MacBook Pro", "serial_number": "SN-MBP-001", "asset_code": "AC-MBP-01"},
                {"brand": "Apple", "model_name": "MacBook Air", "serial_number": "SN-MBA-002", "asset_code": ""},
                {"brand": "Dell", "model_name": "UltraSharp", "serial_number": "", "asset_code": "AC-DEL-03"},
            ],
        )
    ], total_amount="50000.00", psu="PSU-SEPARATE-FIELDS")

    response = _create(client, world, data)
    assert response.status_code == 302

    item = models.ProcurementItem.objects.get()
    assert item.has_sn() is True
    assert item.has_asset() is True
    assert len(item.sub_items) == 3
    assert item.sub_items[0].serial_number == "SN-MBP-001"
    assert item.sub_items[0].asset_code == "AC-MBP-01"
    assert item.sub_items[1].serial_number == "SN-MBA-002"
    assert item.sub_items[1].asset_code is None
    assert item.sub_items[2].serial_number is None
    assert item.sub_items[2].asset_code == "AC-DEL-03"

    # Detail page: dynamic table columns check
    html = client.get(f"/procurement/payment/{item.procurement.id}?{_q(world.org)}").get_data(as_text=True)
    table_html = html.split('class="table table-sm sub-items-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>ยี่ห้อ</th>" in table_html
    assert "<th>รุ่น</th>" in table_html
    assert "<th>S/N</th>" in table_html
    assert "<th>รหัสครุภัณฑ์</th>" in table_html
    assert "<th>รายละเอียด</th>" not in table_html
    assert "SN-MBP-001" in table_html
    assert "AC-MBP-01" in table_html
    assert "SN-MBA-002" in table_html
    assert "AC-DEL-03" in table_html

    # Edit form prefilling
    edit_html = client.get(f"/procurement/products/{item.procurement.id}/edit?{_q(world.org)}").get_data(as_text=True)
    sn_tag = re.search(r'<input[^>]*name="items-0-has_sub_item_sn"[^>]*>', edit_html).group(0)
    assert "checked" in sn_tag
    asset_tag = re.search(r'<input[^>]*name="items-0-has_sub_item_asset"[^>]*>', edit_html).group(0)
    assert "checked" in asset_tag
    assert 'name="items-0-sub_items-0-serial_number"' in edit_html and "SN-MBP-001" in edit_html
    assert 'name="items-0-sub_items-0-asset_code"' in edit_html and "AC-MBP-01" in edit_html


def test_payment_table_columns_dynamic_detection(world, client_for, create_ma):
    client = client_for(world.admin)

    # Case 1: only S/N
    item_sn = _model_item("1000.00", responsible=[world.role_admin])
    item_sn.has_sub_item_sn = True
    item_sn.sub_items = [models.ItemDetail(brand="Lenovo", model_name="T14", serial_number="SN-LENOVO-01")]
    ma_sn = create_ma(world.org, user=world.admin, name="[TEST] S/N Only", total_amount="1000.00", items=[item_sn])

    html_sn = client.get(f"/procurement/payment/{ma_sn.id}?{_q(world.org)}").get_data(as_text=True)
    table_sn = html_sn.split('class="table table-sm sub-items-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>S/N</th>" in table_sn
    assert "<th>รหัสครุภัณฑ์</th>" not in table_sn
    assert "SN-LENOVO-01" in table_sn

    # Case 2: only Asset Code
    item_asset = _model_item("2000.00", responsible=[world.role_admin])
    item_asset.has_sub_item_asset = True
    item_asset.sub_items = [models.ItemDetail(brand="HP", model_name="ProBook", asset_code="AC-HP-01")]
    ma_asset = create_ma(world.org, user=world.admin, name="[TEST] Asset Only", total_amount="2000.00", items=[item_asset])

    html_asset = client.get(f"/procurement/payment/{ma_asset.id}?{_q(world.org)}").get_data(as_text=True)
    table_asset = html_asset.split('class="table table-sm sub-items-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>S/N</th>" not in table_asset
    assert "<th>รหัสครุภัณฑ์</th>" in table_asset
    assert "AC-HP-01" in table_asset


def test_search_matches_sub_items_serial_number_and_asset_code(world, client_for, create_ma):
    item = _model_item("5000.00", responsible=[world.role_admin])
    item.has_sub_item_sn = True
    item.has_sub_item_asset = True
    item.sub_items = [
        models.ItemDetail(brand="Cisco", model_name="Catalyst", serial_number="SN-CISCO-SEARCH-99", asset_code="AC-CISCO-SEARCH-88")
    ]
    procurement = create_ma(world.org, user=world.admin, name="[TEST] Cisco Switch", total_amount="5000.00", items=[item])

    # Search by S/N
    html = client_for(world.admin).get(f"/procurement/products?q=SN-CISCO-SEARCH-99&{_q(world.org)}").get_data(as_text=True)
    assert procurement.psu_disbursement_number in html

    # Search by asset code
    html = client_for(world.admin).get(f"/procurement/products?q=AC-CISCO-SEARCH-88&{_q(world.org)}").get_data(as_text=True)
    assert procurement.psu_disbursement_number in html

