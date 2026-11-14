"""สวิตช์ "แบ่งจ่ายเป็นงวด", การบันทึกจ่ายด้วยปุ่ม "จ่ายแล้ว" พร้อมประวัติการกด และการแก้ไข MA ที่ไม่ทับสถานะการจ่าย"""

import datetime
import re
from decimal import Decimal

import pytest

from kampan import models
from kampan.utils.reminders import due_reminders
from test_ma_structure import (  # noqa: F401
    _create,
    _edit_form,
    _first_installment,
    _installment_url,
    _item,
    _q,
    client_for,
    existing_ma,
    gridfs_enabled,
    ma_form,
    world,
)


def _item_doc(procurement):
    return models.ProcurementItem.objects(procurement=procurement).get()


def _edit(client, world, procurement, data):
    """แก้รายการย่อยเดียวของ MA (?item_id=) เพราะ MA ที่ไม่ใช่แบบร่างแก้รายการ / งวดผ่านโหมดแก้รายการเท่านั้น"""
    item_id = data.get("items-0-item_id") or _item_doc(procurement).id
    return client.post(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}&item_id={item_id}", data=data)


def _pay(client, world, procurement, **data):
    data.setdefault("paid_date", "2026-11-01")
    data.setdefault("payment_number", "PAY-DEFAULT")
    return client.post(f"{_installment_url(procurement, 'pay')}?{_q(world.org)}", data=data)


def _form_for(procurement, **item_overrides):
    """ฟอร์มแก้ไขของ MA ที่มีรายการย่อยเดียว (ส่งงวดเดิมกลับตาม installment_id)"""
    item = _item_doc(procurement)
    installments = [
        {"installment_id": str(installment._id), "due_date": installment.due_date.strftime("%Y-%m-%d")}
        for installment in item.get_sorted_installments()
    ]
    fields = {
        "item_id": str(item.id),
        "name": item.name,
        "amount": str(item.amount),
        "installments": installments,
        "responsible_by": [str(member.id) for member in item.responsible_by],
        "end_date": item.end_date.strftime("%Y-%m-%d"),
    }
    if item.pays_in_installments():
        fields["installment_mode"] = "y"
    fields.update(item_overrides)
    return ma_form(
        [_item(**fields)],
        total_amount=str(item.amount),
        name=procurement.name,
        version=procurement.get_version(),
    )


# ---------------------------------------------------------------------------
# สวิตช์ปิด: ไม่มีการจ่าย ไม่เก็บงวด
# ---------------------------------------------------------------------------


def test_toggle_off_stores_no_installments_and_ignores_posted_rows(world, client_for):
    # ฟอร์มส่งแถวงวดมา 2 แถว (เช่นเหลือจากตอนเปิดสวิตช์) แต่สวิตช์ปิด: ไม่ใช้แถวเหล่านั้น
    data = ma_form(
        [_item(amount="100000.00", end_date="2027-03-15", installments=[{"due_date": "2026-06-30"}, {"due_date": ""}])],
    )

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 302
    item = models.ProcurementItem.objects.get()
    assert item.installment_mode is False
    assert list(item.installments) == []
    assert item.pays_in_installments() is False


def test_toggle_off_without_any_installment_rows_still_saves(world, client_for):
    data = ma_form([_item(amount="100000.00", installments=[])])

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 302
    assert len(models.ProcurementItem.objects.get().installments) == 0


def test_item_without_payment_still_counts_toward_the_ma_total(world, client_for):
    data = ma_form([_item(amount="99999.00")], total_amount="100000.00")

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200  # ผลรวมยอดรายการย่อยไม่ตรงยอด MA ยังตรวจเหมือนเดิม
    assert models.Procurement.objects.count() == 0


def test_editing_end_date_keeps_the_installments_and_paid_state(world, client_for, existing_ma):
    client_for(world.responsible).post(
        f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-1"},
    )
    existing_ma = models.Procurement.objects.get(id=existing_ma.id)
    before = _first_installment(existing_ma)

    response = _edit(client_for(world.admin), world, existing_ma, _form_for(existing_ma, end_date="2027-06-30"))

    assert response.status_code == 302
    item = _item_doc(existing_ma)
    assert item.end_date == datetime.datetime(2027, 6, 30)
    assert len(item.installments) == 1
    after = item.installments[0]
    assert after._id == before._id
    assert after.paid_date == datetime.datetime(2026, 11, 1) and after.payment_number == "PAY-1"
    assert [entry.action for entry in after.pay_log] == ["paid"]


# ---------------------------------------------------------------------------
# สวิตช์เปิด: กรอกวันครบกำหนดเอง
# ---------------------------------------------------------------------------


def test_toggle_on_saves_the_given_due_dates(world, client_for):
    data = ma_form(
        [
            _item(
                amount="100000.00",
                installment_mode="y",
                installments=[{"due_date": "2026-03-31"}, {"due_date": "2026-09-30"}, {"due_date": "2026-06-30"}],
            )
        ]
    )

    assert _create(client_for(world.admin), world, data).status_code == 302

    item = models.ProcurementItem.objects.get()
    assert item.installment_mode is True
    assert [installment.due_date.date() for installment in item.get_sorted_installments()] == [
        datetime.date(2026, 3, 31),
        datetime.date(2026, 6, 30),
        datetime.date(2026, 9, 30),
    ]


def _on_ma(world, client_for, dues=("2026-03-31", "2026-09-30")):
    data = ma_form(
        [_item(amount="100000.00", installment_mode="y", installments=[{"due_date": due} for due in dues])]
    )
    _create(client_for(world.admin), world, data)
    return models.Procurement.objects.get()


def test_edit_adds_changes_and_removes_unpaid_installments_by_id(world, client_for):
    procurement = _on_ma(world, client_for)
    first, second = _item_doc(procurement).get_sorted_installments()
    form = _form_for(procurement)
    form["items-0-installments-0-due_date"] = "2026-04-30"  # แก้งวดแรก
    del form["items-0-installments-1-installment_id"]  # งวดที่สองถูกถอดออก (ยังไม่จ่าย)
    del form["items-0-installments-1-due_date"]
    form["items-0-installments-1-due_date"] = "2026-12-31"  # งวดใหม่

    assert _edit(client_for(world.admin), world, procurement, form).status_code == 302

    installments = _item_doc(procurement).get_sorted_installments()
    assert [i.due_date.date() for i in installments] == [datetime.date(2026, 4, 30), datetime.date(2026, 12, 31)]
    assert installments[0]._id == first._id and installments[1]._id != second._id


def test_edit_refuses_to_remove_a_paid_installment(world, client_for):
    procurement = _on_ma(world, client_for)
    item = _item_doc(procurement)
    paid = item.get_sorted_installments()[0]
    client_for(world.admin).post(
        f"/procurement/payment/{procurement.id}/items/{item.id}/installments/{paid._id}/pay?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-PAID-1"},
    )
    procurement = models.Procurement.objects.get(id=procurement.id)
    form = _form_for(procurement)
    form["items-0-installments-0-due_date"] = form["items-0-installments-1-due_date"]
    form["items-0-installments-0-installment_id"] = form["items-0-installments-1-installment_id"]
    del form["items-0-installments-1-installment_id"], form["items-0-installments-1-due_date"]

    response = _edit(client_for(world.admin), world, procurement, form)

    assert response.status_code == 200
    assert "งวดที่จ่ายแล้วลบไม่ได้" in response.get_data(as_text=True)
    after = _item_doc(procurement)
    assert len(after.installments) == 2 and after.get_installment(paid._id).is_paid()


def test_turning_toggle_off_with_a_paid_installment_is_refused(world, client_for):
    """ปิดแบ่งจ่ายแล้วงวดทั้งหมดถูกทิ้ง จึงห้ามเมื่อมีงวดที่จ่ายแล้ว (ประวัติการจ่ายจะหาย)"""
    procurement = _on_ma(world, client_for)
    item = _item_doc(procurement)
    paid = item.get_sorted_installments()[0]
    client_for(world.admin).post(
        f"/procurement/payment/{procurement.id}/items/{item.id}/installments/{paid._id}/pay?{_q(world.org)}",
        data={"paid_date": "2026-11-01", "payment_number": "PAY-PAID-1"},
    )
    procurement = models.Procurement.objects.get(id=procurement.id)
    form = _form_for(procurement)
    form.pop("items-0-installment_mode")

    response = _edit(client_for(world.admin), world, procurement, form)

    assert response.status_code == 200
    assert "ปิดการแบ่งจ่ายเป็นงวดไม่ได้" in response.get_data(as_text=True)
    after = _item_doc(procurement)
    assert after.installment_mode is True and len(after.installments) == 2 and after.get_installment(paid._id).is_paid()


def test_turning_toggle_off_drops_unpaid_installments(world, client_for):
    procurement = _on_ma(world, client_for)
    form = _form_for(procurement)
    form.pop("items-0-installment_mode")

    assert _edit(client_for(world.admin), world, procurement, form).status_code == 302

    after = _item_doc(procurement)
    assert after.installment_mode is False and list(after.installments) == []


def test_turning_toggle_off_with_two_paid_installments_is_refused(world, client_for):
    procurement = _on_ma(world, client_for)
    item = _item_doc(procurement)
    for installment in item.installments:
        client_for(world.admin).post(
            f"/procurement/payment/{procurement.id}/items/{item.id}/installments/{installment._id}/pay?{_q(world.org)}",
            data={"paid_date": "2026-11-01", "payment_number": f"PAY-{installment._id}"},
        )
    procurement = models.Procurement.objects.get(id=procurement.id)
    form = _form_for(procurement)
    form.pop("items-0-installment_mode")

    response = _edit(client_for(world.admin), world, procurement, form)

    assert response.status_code == 200
    assert "ปิดการแบ่งจ่ายเป็นงวดไม่ได้" in response.get_data(as_text=True)
    assert len(_item_doc(procurement).installments) == 2


def _legacy_item(world, due_count):
    now = datetime.datetime(2026, 12, 31)
    item = models.ProcurementItem(
        name="[TEST] เก่า",
        category="software",
        amount=Decimal("100.00"),
        start_date=datetime.datetime(2026, 1, 1),
        end_date=now,
        installments=[models.Installment(due_date=now - datetime.timedelta(days=30 * n)) for n in range(due_count)],
    )
    procurement = models.Procurement(
        name="[TEST] MA เก่า", company="x", total_amount=Decimal("100.00"), organization=world.org, created_by=world.admin
    )
    procurement.save_with_items([item])
    # เอกสารที่สร้างก่อนมี field installment_mode
    models.ProcurementItem._get_collection().update_many({}, {"$unset": {"installment_mode": ""}})
    return procurement


@pytest.mark.parametrize("due_count, checked", [(1, False), (3, True)])
def test_legacy_item_without_mode_derives_toggle_from_installment_count(world, client_for, due_count, checked):
    procurement = _legacy_item(world, due_count)

    html = client_for(world.admin).get(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}&item_id={_item_doc(procurement).id}").get_data(as_text=True)

    tag = re.search(r'<input[^>]*name="items-0-installment_mode"[^>]*>', html).group(0)
    assert ("checked" in tag) is checked


# ---------------------------------------------------------------------------
# ฟอร์มไม่มีช่องการจ่าย / ไม่มีปุ่มสร้างงวด
# ---------------------------------------------------------------------------


def test_form_rows_have_only_due_date_and_no_generate_controls(world, client_for, existing_ma):
    client = client_for(world.admin)
    pages = [
        client.get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True),
        client.get(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}&item_id={_item_doc(existing_ma).id}").get_data(as_text=True),
    ]

    for html in pages:
        for removed in ("paid_date", "payment_number", "paid_amount", "generate-installments", "generate-count", "สร้างวันครบกำหนดเท่า ๆ กัน"):
            assert removed not in html
        assert "installment_mode" in html and 'class="toggle' in html.replace("toggle toggle-primary", 'class="toggle')
        assert "เพิ่มงวด" in html


# ---------------------------------------------------------------------------
# ปุ่ม "จ่ายแล้ว" + ประวัติการกด
# ---------------------------------------------------------------------------


def test_pay_and_unpay_append_pay_log_with_who_and_when(world, client_for, existing_ma):
    client = client_for(world.responsible)
    before = datetime.datetime.now() - datetime.timedelta(seconds=5)

    _pay(client, world, existing_ma, paid_date="2026-11-01", payment_number="PAY-9", paid_amount="12.50")
    client.post(f"{_installment_url(existing_ma, 'unpay')}?{_q(world.org)}")
    _pay(client_for(world.admin), world, existing_ma, paid_date="2026-11-05")

    log = list(_first_installment(existing_ma).pay_log)
    assert [entry.action for entry in log] == ["paid", "unpaid", "paid"]
    assert [entry.by.id for entry in log] == [world.responsible.id, world.responsible.id, world.admin.id]
    assert all(entry.pressed_at >= before for entry in log)
    assert log[0].paid_date == datetime.datetime(2026, 11, 1) and log[0].payment_number == "PAY-9"
    assert log[0].paid_amount == Decimal("12.50")
    # ยกเลิก: เก็บวันที่จ่ายเดิมที่ถูกยกเลิกไว้ในประวัติ
    assert log[1].paid_date == datetime.datetime(2026, 11, 1)
    assert _first_installment(existing_ma).paid_date == datetime.datetime(2026, 11, 5)


def test_pay_is_post_only_and_for_editors_only(world, client_for, existing_ma):
    url = f"{_installment_url(existing_ma, 'pay')}?{_q(world.org)}"

    assert client_for(world.admin).get(url).status_code == 405
    _pay(client_for(world.head), world, existing_ma)  # เห็น MA ทั้งหน่วยงานแต่ไม่ใช่ผู้แก้ไข MA ได้

    installment = _first_installment(existing_ma)
    assert installment.paid_date is None and list(installment.pay_log) == []


def test_pay_of_other_org_ma_is_404_and_logs_nothing(world, client_for, existing_ma):
    url = f"{_installment_url(existing_ma, 'pay')}?{_q(world.other_org)}"

    response = client_for(world.admin_b).post(url, data={"paid_date": "2026-11-01"})

    assert response.status_code == 404
    assert list(_first_installment(existing_ma).pay_log) == []


def test_detail_page_shows_pay_log_newest_first_with_who_and_be_date(world, client_for, existing_ma):
    _pay(client_for(world.responsible), world, existing_ma, paid_date="2026-11-01")
    client_for(world.admin).post(f"{_installment_url(existing_ma, 'unpay')}?{_q(world.org)}")

    html = client_for(world.admin).get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)

    log_html = html.split("ประวัติการกด", 1)[1].split("</details>", 1)[0]
    assert log_html.index("ยกเลิกการจ่าย") < log_html.index("บันทึกจ่าย")
    assert "Responsible" in log_html and "Admin" in log_html
    assert re.search(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}", log_html)
    assert str(datetime.date.today().year + 543) in log_html
    assert "จ่ายแล้ว" in html  # ปุ่มบันทึกจ่ายของงวดที่ยังไม่จ่าย


def test_pay_modal_uses_readonly_thai_date_with_iso_value(world, client_for, existing_ma):
    html = client_for(world.admin).get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)

    modal = html.split('id="pay_modal_', 1)[1].split("</dialog>", 1)[0]
    today = datetime.date.today()
    from kampan.utils.template_filters import format_thai_date
    assert 'type="date"' not in modal
    assert f'value="{today.isoformat()}"' in modal
    assert format_thai_date(today) in modal


def test_edit_paid_installment_logs_edited_action_and_shows_label(world, client_for, existing_ma):
    # ครั้งที่ 1: บันทึกจ่าย
    resp1 = _pay(client_for(world.responsible), world, existing_ma, paid_date="2026-11-01", payment_number="INV-001")
    assert resp1.status_code == 302
    item = _item_doc(existing_ma)
    inst = item.installments[0]
    assert len(inst.pay_log) == 1
    assert inst.pay_log[0].action == "paid"

    # ครั้งที่ 2: แก้ไขการจ่าย (เช่น เปลี่ยนเลขที่เอกสาร)
    resp2 = _pay(client_for(world.admin), world, existing_ma, paid_date="2026-11-01", payment_number="INV-002", paid_amount="5000.00")
    assert resp2.status_code == 302

    # ตรวจสอบประวัติการกดใน DB
    item.reload()
    inst = item.installments[0]
    assert len(inst.pay_log) == 2
    assert inst.pay_log[1].action == "edited"
    assert inst.pay_log[1].payment_number == "INV-002"
    assert inst.pay_log[1].get_action_label() == "แก้ไขการบันทึก"

    # ตรวจสอบการแสดงผลในหน้าเว็บ
    html = client_for(world.admin).get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)
    assert "แก้ไขการบันทึก" in html
    assert "INV-002" in html
    assert "5,000" in html


# ---------------------------------------------------------------------------
# นำเข้า Excel + การเตือน
# ---------------------------------------------------------------------------


def test_no_payment_reminders_for_toggle_off_item_but_expiry_stays(world, client_for):
    _create(client_for(world.admin), world, ma_form([_item(amount="100000.00", end_date="2027-04-30")]))

    reminders = due_reminders(datetime.date(2027, 4, 30))

    assert [r for r in reminders if r.kind == "payment"] == []
    assert [(r.kind, r.offset) for r in reminders] == [("expiry", "due")]


def _payment_item_ma(world, create_ma, offsets, due=datetime.datetime(2027, 4, 30)):
    return create_ma(
        world.org,
        user=world.admin,
        items=[
            models.ProcurementItem(
                name="[TEST] งวด",
                category="software",
                amount=Decimal("1000.00"),
                start_date=datetime.datetime(2027, 1, 1),
                end_date=datetime.datetime(2027, 12, 31),
                responsible_by=[world.role_responsible],
                installment_mode=True,
                payment_reminder_offsets=offsets,
                installments=[models.Installment(due_date=due)],
            )
        ],
    )


def _payment_triggers(day):
    return [(r.trigger_date, r.offset) for r in due_reminders(day) if r.kind == "payment"]


def test_default_payment_offsets_are_empty_and_only_due_date_reminds(world, create_ma):
    assert models.DEFAULT_PAYMENT_REMINDER_OFFSETS == []
    _payment_item_ma(world, create_ma, offsets=[])

    assert _payment_triggers(datetime.date(2027, 4, 23)) == []  # 7 วันก่อน ไม่ได้ติ๊ก
    assert _payment_triggers(datetime.date(2027, 4, 30)) == [(datetime.date(2027, 4, 30), "due")]


@pytest.mark.parametrize("offset, days", [("7d", 7), ("5d", 5), ("3d", 3)])
def test_ticked_payment_offsets_add_extra_triggers(world, create_ma, offset, days):
    _payment_item_ma(world, create_ma, offsets=[offset])
    due = datetime.date(2027, 4, 30)

    assert _payment_triggers(due - datetime.timedelta(days=days)) == [(due - datetime.timedelta(days=days), offset)]
    assert _payment_triggers(due) == [(due, "due")]


def test_legacy_payment_offsets_are_readable_but_ignored(world, create_ma):
    _payment_item_ma(world, create_ma, offsets=["3m", "15d"])

    assert models.ProcurementItem.objects.get().payment_reminder_offsets == ["3m", "15d"]
    assert _payment_triggers(datetime.date(2027, 3, 30)) == []  # 3 เดือนก่อน ไม่ส่งแล้ว
    assert _payment_triggers(datetime.date(2027, 4, 15)) == []
    assert _payment_triggers(datetime.date(2027, 4, 30)) == [(datetime.date(2027, 4, 30), "due")]


def test_legacy_item_with_mode_off_and_stored_single_installment_has_no_payment(world, create_ma):
    ma = _payment_item_ma(world, create_ma, offsets=[])
    models.ProcurementItem.objects(procurement=ma).update(set__installment_mode=False)
    ma = models.Procurement.objects.get(id=ma.id)
    item = _item_doc(ma)

    assert item.get_payment_status() == "paid" and item.get_sorted_installments() == []
    assert item.get_installment_count() == 0 and item.get_next_unpaid_installment() is None
    assert _payment_triggers(datetime.date(2027, 4, 30)) == []
    assert ma.get_unpaid_installments() == [] and ma.pay_single_installments_on_renewal(world.admin) == 0


@pytest.mark.parametrize("periods, mode, count", [(1, False, 0), (4, True, 4)])
def test_excel_import_turns_installment_mode_on_only_when_more_than_one(world, gridfs_enabled, periods, mode, count):
    from kampan.utils import upload_files
    from test_ma_structure import _excel_row, _upload_document

    document = _upload_document(world, [_excel_row(**{"จำนวนงวด": periods, "วันที่สิ้นสุด": "31/12/2026"})])

    upload_files.save_ma_db(document, None, world.admin.id)

    item = models.ProcurementItem.objects.get()
    assert item.installment_mode is mode and len(item.installments) == count
