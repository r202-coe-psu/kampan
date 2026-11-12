"""MA ที่ไม่ใช่แบบร่างแก้ได้แค่หัว หรือรายการเดียว (?item_id=) และลบรายการย่อยด้วยปุ่มยืนยัน (ตัดสินใจ 2026-11-13)"""

import datetime
from decimal import Decimal

import pytest

from kampan import models
from test_ma_structure import (  # noqa: F401
    _csrf_token,
    _first_installment,
    _item,
    _model_item,
    _pay_directly,
    _q,
    client_for,
    csrf_enabled,
    existing_ma,
    gridfs_enabled,
    ma_form,
    world,
)


def _named(name, amount):
    item = _model_item(amount)  # วันสิ้นสุดไกลกว่า 90 วัน MA จึงคง active
    item.name = name
    return item


@pytest.fixture
def two_item_ma(world, create_ma):
    return create_ma(
        world.org,
        user=world.admin,
        name="[TEST] MA สองรายการ",
        responsible=[world.role_admin],
        total_amount="100.00",
        items=[_named("[TEST] รายการ A", "60.00"), _named("[TEST] รายการ B", "40.00")],
    )


def _edit_url(world, procurement, item=None):
    url = f"/procurement/products/{procurement.id}/edit?{_q(world.org)}"
    return f"{url}&item_id={item.id}" if item else url


def _delete_url(world, procurement, item, org=None):
    return f"/procurement/products/{procurement.id}/items/{item.id}/delete?{_q(org or world.org)}"


def _item_fields(item, **overrides):
    fields = {
        "item_id": str(item.id),
        "name": item.name,
        "amount": str(item.amount),
        "installments": [{"installment_id": str(item.installments[0]._id), "due_date": "2030-12-31"}],
    }
    fields.update(overrides)
    return _item(**fields)


def _amounts(procurement):
    return {item.name: item.amount for item in models.ProcurementItem.objects(procurement=procurement)}


# ---------------------------------------------------------------------------
# แก้เฉพาะหัว (ไม่มี ?item_id=)
# ---------------------------------------------------------------------------


def test_header_edit_page_has_no_item_cards_or_item_buttons(world, client_for, two_item_ma):
    html = client_for(world.admin).get(_edit_url(world, two_item_ma)).get_data(as_text=True)

    assert 'name="name"' in html and 'name="company"' in html
    assert 'name="psu_disbursement_number"' in html and 'name="disbursement_date"' in html
    assert 'name="total_amount"' not in html
    assert 'name="items-0-' not in html
    assert 'data-action="add-item"' not in html and 'data-action="remove-item"' not in html


def test_header_edit_saves_header_and_ignores_posted_item_fields(world, client_for, two_item_ma):
    first, second = two_item_ma.get_items()
    data = ma_form(
        [
            _item_fields(first, amount="1.00", name="แก้ชื่อรายการ"),
            _item_fields(second, amount="2.00"),
            _item(name="[TEST] รายการแอบเพิ่ม", amount="5.00"),
        ],
        total_amount="8.00",
        name="[TEST] ชื่อใหม่",
        version=two_item_ma.get_version(),
    )

    response = client_for(world.admin).post(_edit_url(world, two_item_ma), data=data)

    assert response.status_code == 302
    two_item_ma.reload()
    assert two_item_ma.name == "[TEST] ชื่อใหม่"
    assert two_item_ma.total_amount == Decimal("100.00")
    assert _amounts(two_item_ma) == {"[TEST] รายการ A": Decimal("60.00"), "[TEST] รายการ B": Decimal("40.00")}


def test_header_edit_without_any_item_fields_succeeds_and_keeps_items(world, client_for, two_item_ma):
    data = {
        "psu_disbursement_number": "PSU-NEW",
        "name": "[TEST] เฉพาะหัว",
        "company": "[TEST] บริษัทใหม่",
        "version": two_item_ma.get_version(),
    }

    response = client_for(world.admin).post(_edit_url(world, two_item_ma), data=data)

    assert response.status_code == 302
    two_item_ma.reload()
    assert (two_item_ma.name, two_item_ma.company, two_item_ma.psu_disbursement_number) == (
        "[TEST] เฉพาะหัว",
        "[TEST] บริษัทใหม่",
        "PSU-NEW",
    )
    assert models.ProcurementItem.objects(procurement=two_item_ma).count() == 2


def test_header_edit_cannot_turn_active_ma_back_into_draft(world, client_for, two_item_ma):
    data = {"psu_disbursement_number": "", "name": "x", "company": "", "action": "draft", "version": two_item_ma.get_version()}

    response = client_for(world.admin).post(_edit_url(world, two_item_ma), data=data)

    assert response.status_code == 200  # ฟิลด์บังคับยังต้องกรอก ไม่เข้าโหมดแบบร่าง
    two_item_ma.reload()
    assert two_item_ma.status == "active" and two_item_ma.name == "[TEST] MA สองรายการ"


# ---------------------------------------------------------------------------
# แก้รายการเดียว (?item_id=)
# ---------------------------------------------------------------------------


def test_item_edit_page_shows_only_that_item_without_header_details_and_no_add_remove(world, client_for, two_item_ma):
    first, second = two_item_ma.get_items()

    html = client_for(world.admin).get(_edit_url(world, two_item_ma, second)).get_data(as_text=True)

    assert 'name="items-0-name"' in html and 'name="items-1-name"' not in html
    assert f'value="{second.id}"' in html and f'value="{first.id}"' not in html
    # แก้ไขรายการย่อยโดยตรง: ไม่แสดงข้อมูลหัวสัญญา (ไม่มีช่องแก้ และไม่มีข้อมูลหัวแบบอ่านอย่างเดียว)
    assert 'id="header_readonly"' not in html and 'name="company"' not in html
    assert "ข้อมูลหัว MA" not in html and "แก้ไขรายการย่อย" in html
    assert 'name="total_amount"' not in html
    assert 'data-action="add-item"' not in html and 'data-action="remove-item"' not in html


def test_item_edit_changes_only_that_item_and_recomputes_total(world, client_for, two_item_ma):
    first, second = two_item_ma.get_items()
    data = ma_form(
        [_item_fields(second, amount="55.50", note="แก้แล้ว")],
        total_amount="1.00",
        name="[TEST] พยายามเปลี่ยนชื่อ",
        version=two_item_ma.get_version(),
    )

    response = client_for(world.admin).post(_edit_url(world, two_item_ma, second), data=data)

    assert response.status_code == 302
    two_item_ma.reload()
    assert _amounts(two_item_ma) == {"[TEST] รายการ A": Decimal("60.00"), "[TEST] รายการ B": Decimal("55.50")}
    assert two_item_ma.total_amount == Decimal("115.50")
    assert two_item_ma.name == "[TEST] MA สองรายการ"  # หัวแก้ไม่ได้ในโหมดนี้
    first.reload()
    assert first.note in (None, "")


def test_item_edit_for_unknown_or_other_ma_item_is_404(world, client_for, two_item_ma, create_ma):
    other = create_ma(world.org, user=world.admin, name="[TEST] MA อื่น", total_amount="10.00")
    foreign_item = other.get_items()[0]
    client = client_for(world.admin)

    assert client.get(_edit_url(world, two_item_ma, foreign_item)).status_code == 404
    assert client.get(f"/procurement/products/{two_item_ma.id}/edit?{_q(world.org)}&item_id=not-an-id").status_code == 404
    assert client.post(_edit_url(world, two_item_ma, foreign_item), data={}).status_code == 404


def test_item_edit_crafted_post_cannot_add_remove_or_swap_items(world, client_for, two_item_ma):
    first, second = two_item_ma.get_items()
    client = client_for(world.admin)
    version = two_item_ma.get_version()

    # เพิ่มรายการที่สอง
    extra = ma_form(
        [_item_fields(first), _item(name="[TEST] แอบเพิ่ม", amount="9.00")], total_amount="109.00", version=version
    )
    assert client.post(_edit_url(world, two_item_ma, first), data=extra).status_code == 200
    # ส่ง item_id ของรายการอื่น (หวังให้ลบ / แก้รายการที่ไม่ได้เลือก)
    swapped = ma_form([_item_fields(second, amount="1.00")], total_amount="1.00", version=version)
    assert client.post(_edit_url(world, two_item_ma, first), data=swapped).status_code == 200
    # ไม่ส่งรายการเลย
    empty = {"psu_disbursement_number": "x", "name": "x", "company": "x", "version": version}
    assert client.post(_edit_url(world, two_item_ma, first), data=empty).status_code == 200

    two_item_ma.reload()
    assert two_item_ma.total_amount == Decimal("100.00")
    assert _amounts(two_item_ma) == {"[TEST] รายการ A": Decimal("60.00"), "[TEST] รายการ B": Decimal("40.00")}


def test_item_edit_refuses_removing_paid_installment_and_keeps_stale_lock(world, client_for, two_item_ma):
    first = two_item_ma.get_items()[0]
    _pay_directly_first(first)
    first.reload()
    two_item_ma.reload()
    data = ma_form(
        [_item_fields(first, installment_mode="y", installments=[{"due_date": "2026-11-30"}])],  # ไม่ส่งงวดเดิมที่จ่ายแล้วกลับมา
        total_amount="100.00",
        version=two_item_ma.get_version(),
    )

    response = client_for(world.admin).post(_edit_url(world, two_item_ma, first), data=data)

    assert response.status_code == 200
    assert "งวดที่จ่ายแล้วลบไม่ได้" in response.get_data(as_text=True)
    first.reload()
    assert first.installments[0].paid_date is not None


def _pay_directly_first(item):
    models.ProcurementItem.objects(id=item.id, __raw__={"installments._id": item.installments[0]._id}).update_one(
        set__installments__S__paid_date=datetime.datetime(2026, 11, 1),
        set__installments__S__payment_number="PAY-1",
        set__updated_date=datetime.datetime.now() + datetime.timedelta(seconds=1),
    )


def test_item_edit_stale_form_is_rejected(world, client_for, two_item_ma):
    second = two_item_ma.get_items()[1]
    data = ma_form([_item_fields(second, amount="41.00")], total_amount="x", version=two_item_ma.get_version())
    models.ProcurementItem.objects(id=second.id).update_one(
        set__note="คนอื่นแก้", set__updated_date=datetime.datetime.now() + datetime.timedelta(seconds=5)
    )

    response = client_for(world.admin).post(_edit_url(world, two_item_ma, second), data=data)

    assert response.status_code == 200
    assert "ถูกแก้ไขหรือบันทึกจ่ายงวดโดยผู้อื่น" in response.get_data(as_text=True)
    assert _amounts(two_item_ma)["[TEST] รายการ B"] == Decimal("40.00")


# ---------------------------------------------------------------------------
# แบบร่างยังแก้ฟอร์มเต็ม (เพิ่ม / ลบรายการได้)
# ---------------------------------------------------------------------------


def test_draft_edit_keeps_full_form_and_can_add_and_remove_items(world, client_for, create_ma):
    draft = create_ma(world.org, user=world.admin, name="[TEST] แบบร่าง", status="draft", total_amount="50.00")
    client = client_for(world.admin)
    html = client.get(_edit_url(world, draft)).get_data(as_text=True)
    assert 'name="total_amount"' in html and 'data-action="add-item"' in html and 'data-action="remove-item"' in html

    kept = draft.get_items()[0]
    data = ma_form(
        [_item_fields(kept, amount="50.00"), _item(name="[TEST] เพิ่มในแบบร่าง", amount="25.00")],
        total_amount="75.00",
        name="[TEST] แบบร่าง",
        version=draft.get_version(),
        action="save",
    )
    assert client.post(_edit_url(world, draft), data=data).status_code == 302
    draft.reload()
    assert draft.status == "active" and models.ProcurementItem.objects(procurement=draft).count() == 2

    # ลบรายการออกจากแบบร่างอีกใบผ่านฟอร์มเต็ม
    draft2 = create_ma(
        world.org,
        user=world.admin,
        name="[TEST] แบบร่าง 2",
        status="draft",
        total_amount="30.00",
        items=[_named("[TEST] D1", "10.00"), _named("[TEST] D2", "20.00")],
    )
    d1 = draft2.get_items()[0]
    data = ma_form(
        [_item_fields(d1, amount="10.00")], total_amount="10.00", version=draft2.get_version(), action="draft"
    )
    assert client.post(_edit_url(world, draft2), data=data).status_code == 302
    assert [item.name for item in models.ProcurementItem.objects(procurement=draft2)] == ["[TEST] D1"]


# ---------------------------------------------------------------------------
# ลบรายการย่อย
# ---------------------------------------------------------------------------


def _reminder_log(world, procurement, item):
    return models.ReminderLog(
        organization=world.org,
        procurement=procurement,
        item=item,
        kind="expiry",
        trigger_date=datetime.datetime(2026, 11, 1),
        status="sent",
    ).save()


def _with_child_contract(world, parent, item):
    """สำเนาสัญญาย่อยแบบที่สร้างตอนสร้าง MA หลายรายการ"""
    from kampan.web.views.procurement.products import _duplicate_child_procurements

    _duplicate_child_procurements(parent, [item], world.admin)
    return models.Procurement.objects.get(parent_procurement=parent, name=item.name)


def test_delete_item_removes_item_logs_child_contract_and_updates_total(world, client_for, two_item_ma):
    first, second = two_item_ma.get_items()
    child = _with_child_contract(world, two_item_ma, second)
    keep_child = _with_child_contract(world, two_item_ma, first)
    child_item = child.get_items()[0]
    logs = [_reminder_log(world, two_item_ma, second), _reminder_log(world, child, child_item)]
    keep_log = _reminder_log(world, two_item_ma, first)
    assert len(logs) == 2

    response = client_for(world.admin).post(_delete_url(world, two_item_ma, second))

    assert response.status_code == 302
    assert response.headers["Location"].startswith(f"/procurement/payment/{two_item_ma.id}")
    two_item_ma.reload()
    assert two_item_ma.total_amount == Decimal("60.00")
    assert [item.id for item in models.ProcurementItem.objects(procurement=two_item_ma)] == [first.id]
    assert models.ReminderLog.objects(item=second.id).count() == 0
    assert models.Procurement.objects(id=child.id).count() == 0
    assert models.ProcurementItem.objects(id=child_item.id).count() == 0
    assert models.ReminderLog.objects(item=child_item.id).count() == 0
    # ของรายการที่เหลือไม่ถูกแตะ
    assert models.Procurement.objects(id=keep_child.id).count() == 1
    assert models.ReminderLog.objects(id=keep_log.id).count() == 1


def test_delete_item_refused_for_only_item(world, client_for, existing_ma):
    item = existing_ma.get_items()[0]
    client = client_for(world.admin)

    response = client.post(_delete_url(world, existing_ma, item))

    assert response.status_code == 302
    assert models.ProcurementItem.objects(id=item.id).count() == 1
    from test_ma_structure import _flashes

    assert [category for category, _ in _flashes(client)] == ["error"]


def test_delete_item_refused_when_item_has_paid_installment(world, client_for, two_item_ma):
    first = two_item_ma.get_items()[0]
    _pay_directly_first(first)
    two_item_ma = models.Procurement.objects.get(id=two_item_ma.id)

    response = client_for(world.admin).post(_delete_url(world, two_item_ma, first))

    assert response.status_code == 302
    assert models.ProcurementItem.objects(procurement=two_item_ma).count() == 2
    assert two_item_ma.total_amount == Decimal("100.00")


def test_delete_item_other_org_and_unknown_ids_are_404(world, client_for, two_item_ma):
    second = two_item_ma.get_items()[1]

    # ผู้ใช้ org อื่นที่ส่ง organization_id ของตัวเอง: MA ไม่อยู่ใน org นั้น
    other = client_for(world.admin_b)
    assert other.post(_delete_url(world, two_item_ma, second, org=world.other_org)).status_code == 404
    admin = client_for(world.admin)
    assert admin.post(f"/procurement/products/{two_item_ma.id}/items/{two_item_ma.id}/delete?{_q(world.org)}").status_code == 404
    assert admin.post(f"/procurement/products/{two_item_ma.id}/items/not-an-id/delete?{_q(world.org)}").status_code == 404
    assert admin.post(f"/procurement/products/not-an-id/items/{second.id}/delete?{_q(world.org)}").status_code == 404
    assert models.ProcurementItem.objects(procurement=two_item_ma).count() == 2


def test_delete_item_rejects_get(world, client_for, two_item_ma):
    second = two_item_ma.get_items()[1]

    assert client_for(world.admin).get(_delete_url(world, two_item_ma, second)).status_code == 405


def test_delete_item_without_csrf_token_changes_nothing(world, client_for, two_item_ma, csrf_enabled):
    second = two_item_ma.get_items()[1]

    response = client_for(world.admin).post(_delete_url(world, two_item_ma, second))

    assert response.status_code == 302
    assert models.ProcurementItem.objects(procurement=two_item_ma).count() == 2


def test_delete_item_with_csrf_token_from_dialog_works(world, client_for, two_item_ma, csrf_enabled):
    second = two_item_ma.get_items()[1]
    client = client_for(world.admin)
    html = client.get(f"/procurement/payment/{two_item_ma.id}?{_q(world.org)}").get_data(as_text=True)

    client.post(_delete_url(world, two_item_ma, second), data={"csrf_token": _csrf_token(html)})

    assert [item.name for item in models.ProcurementItem.objects(procurement=two_item_ma)] == ["[TEST] รายการ A"]


def test_delete_item_refused_for_user_without_edit_rights(world, client_for, two_item_ma):
    second = two_item_ma.get_items()[1]

    response = client_for(world.head).post(_delete_url(world, two_item_ma, second))

    assert response.status_code == 302
    assert models.ProcurementItem.objects(procurement=two_item_ma).count() == 2


def test_detail_page_shows_delete_dialog_and_disables_when_not_allowed(world, client_for, two_item_ma, existing_ma):
    client = client_for(world.admin)
    first, second = two_item_ma.get_items()
    _pay_directly_first(first)

    html = client.get(f"/procurement/payment/{two_item_ma.id}?{_q(world.org)}").get_data(as_text=True)

    assert f'id="delete_item_modal_{second.id}"' in html
    assert f"/items/{second.id}/delete" in html
    assert f'id="delete_item_modal_{first.id}"' not in html  # มีงวดจ่ายแล้ว: ปุ่มถูก disable พร้อมเหตุผล
    assert "รายการนี้มีงวดที่จ่ายแล้ว ลบไม่ได้" in html
    assert f"item_id={second.id}" in html  # ปุ่มแก้ไขของแต่ละรายการเข้าโหมดแก้รายการเดียว

    only = client.get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)
    assert "delete_item_modal_" not in only
    assert "MA ต้องมีรายการย่อยอย่างน้อย 1 รายการ" in only


def test_delete_item_refused_when_sub_contract_copy_has_paid_installment(app, create_org, create_user, assign_user_to_org):
    """สัญญาย่อยที่เป็นสำเนาจะถูกลบไปด้วย ถ้าฝั่งสัญญาย่อยจ่ายแล้วต้องห้ามลบ (ประวัติการจ่ายห้ามหาย)"""
    import datetime
    from decimal import Decimal

    from kampan import models

    org = create_org("[TEST] Org delete")
    user = create_user("Del", "Test")
    assign_user_to_org(user, org, roles=["admin"])

    def make_item(name, paid=False):
        due = datetime.datetime(2027, 1, 1)
        return models.ProcurementItem(
            name=name, category="software", amount=Decimal("100.00"), start_date=due, end_date=due,
            installments=[models.Installment(due_date=due, paid_date=due if paid else None)],
        )

    parent = models.Procurement(psu_disbursement_number="P", name="P", company="C", organization=org, status="active", total_amount=Decimal("200.00"))
    parent.save_with_items([make_item("A"), make_item("B")])
    child = models.Procurement(psu_disbursement_number="P", name="A", company="C", organization=org, status="active", total_amount=Decimal("100.00"), parent_procurement=parent)
    child.save_with_items([make_item("A", paid=True)])
    parent = models.Procurement.objects(id=parent.id).get()
    item_a = next(i for i in parent.get_items() if i.name == "A")

    assert "สัญญาย่อย" in parent.get_item_delete_block(item_a)
    try:
        parent.delete_item(item_a, user)
    except models.ItemDeleteError:
        pass
    else:
        raise AssertionError("delete_item should refuse")
    assert models.Procurement.objects(id=child.id).count() == 1
    assert len(models.Procurement.objects(id=parent.id).get().get_items()) == 2
