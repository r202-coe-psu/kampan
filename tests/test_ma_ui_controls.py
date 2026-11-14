"""ตัวควบคุมของหน้า MA: dropdown DaisyUI แทน <select>, ปฏิทิน พ.ศ., ไม่มีช่องรูปภาพ และไม่มี native control"""

import datetime
from decimal import Decimal
import re

import pytest

from kampan import models
from test_ma_structure import (  # noqa: F401
    _q,
    client_for,
    existing_ma,
    ma_form,
    world,
    _create,
    _item,
    _two_item_form,
)


def _strip_templates(html):
    return re.sub(r"<template.*?</template>", "", html, flags=re.S)


def test_dropdown_select_renders_hidden_input_selected_label_and_menu(app):
    from flask import render_template_string

    from wtforms import Form, SelectField

    class Demo(Form):
        kind = SelectField("ประเภท", choices=[("a", "ตัวเลือก เอ"), ("b", "ตัวเลือก บี")], default="b")

    with app.test_request_context():
        form = Demo()
        html = render_template_string(
            "{% from '/base/html-renderer.html' import dropdown_select %}{{ dropdown_select(form.kind, required=True) }}",
            form=form,
        )

    assert "<select" not in html
    assert re.search(r'<input type="hidden" name="kind" id="kind" value="b"', html)
    assert re.search(r'<span data-dd-label[^>]*>ตัวเลือก บี</span>', html)
    assert html.count("data-value=") == 2
    assert re.search(r'data-value="b" aria-selected="true"\s+class="[^"]*menu-active[^"]*"', html)
    assert 'role="listbox"' in html and 'aria-haspopup="listbox"' in html and "select-error" not in html


def test_dropdown_select_error_and_disabled_states(app):
    from flask import render_template_string

    from wtforms import Form, SelectField

    class Demo(Form):
        kind = SelectField("ประเภท", choices=[("a", "เอ")])

    with app.test_request_context():
        form = Demo()
        form.kind.errors = ["ค่าไม่ถูกต้อง"]
        html = render_template_string(
            "{% from '/base/html-renderer.html' import dropdown_select %}{{ dropdown_select(form.kind, disabled=True) }}",
            form=form,
        )

    assert "select-error" in html and "ค่าไม่ถูกต้อง" in html
    assert re.search(r'<input type="hidden"[^>]* disabled', html) and re.search(r"data-dd-button[^>]* disabled", html)


def test_invalid_category_post_shows_error_style_on_dropdown(world, client_for):
    data = _two_item_form(world)
    data["items-0-category"] = "not-a-category"

    response = _create(client_for(world.admin), world, data)

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    button = re.search(r'id="dd-button-items-0-category"[^>]*class="([^"]*)"', html).group(1)
    assert "select-error" in button
    assert models.Procurement.objects.count() == 0


def test_dropdown_posts_the_original_field_value(world, client_for):
    data = _two_item_form(world)

    assert _create(client_for(world.admin), world, data).status_code == 302

    first = models.ProcurementItem.objects.order_by("id").first()
    assert first.category == "intangible" and first.reminder_kind == "license"


def _item_edit_url(world, procurement):
    return f"/procurement/products/{procurement.id}/edit?{_q(world.org)}&item_id={procurement.get_items()[0].id}"


def test_calendar_shows_buddhist_year_label_and_th_locale_but_posts_iso(world, client_for, existing_ma):
    html = client_for(world.admin).get(_item_edit_url(world, existing_ma)).get_data(as_text=True)

    page = _strip_templates(html)
    item = existing_ma.get_items()[0]
    end = item.end_date
    assert f'value="{end.strftime("%Y-%m-%d")}"' in page
    assert f"{end.day:02d}/{end.month:02d}/{end.year + 543}" in page
    assert page.count('data-buddhist="1"') >= 3
    assert 'locale="th-TH"' in page
    # ไม่มีปีค.ศ. แบบ dd/mm/yyyy ในป้ายของ date picker
    assert f"{end.day:02d}/{end.month:02d}/{end.year}<" not in page


def test_image_upload_is_gone_from_the_form_but_existing_images_are_kept(world, client_for, existing_ma):
    client = client_for(world.admin)

    for url in (f"/procurement/products/create?{_q(world.org)}", f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"):
        html = client.get(url).get_data(as_text=True)
        assert 'type="file"' not in html and "multipart/form-data" not in html and 'name="image"' not in html

    detail = client.get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)
    assert "รูปภาพ" not in detail and "edit_image" not in detail
    assert client.get(f"/procurement/products/{existing_ma.id}/edit_image?{_q(world.org)}").status_code == 404
    # ข้อมูลเดิมไม่ถูกลบ: field ยังอยู่ใน model
    assert "image" in models.Procurement._fields


def test_posting_an_image_to_the_form_is_ignored(world, client_for):
    import io

    data = _two_item_form(world)
    data["image"] = (io.BytesIO(b"\x89PNG"), "x.png")

    response = client_for(world.admin).post(
        f"/procurement/products/create?{_q(world.org)}", data=data, content_type="multipart/form-data"
    )

    assert response.status_code == 302
    assert not models.Procurement.objects.get(parent_procurement=None).image


@pytest.mark.parametrize(
    "path",
    [
        "/procurement/products/create?{q}",
        "/procurement/products/{id}/edit?{q}",
        "/procurement/products/{id}/renew?{q}",
        "/procurement/payment/{id}?{q}",
        "/procurement/products?{q}",
        "/procurement/requisitions/non-renewal?{q}",
        "/admin/upload_files/create?{q}",
    ],
)
def test_rendered_ma_pages_have_no_native_select_or_date_input(world, client_for, existing_ma, path):
    client = client_for(world.admin)
    existing_ma.reload()
    response = client.get(path.format(id=existing_ma.id, q=_q(world.org)))

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "<select" not in html and 'type="date"' not in html
    # control ที่เหลือต้องใช้ class ของ DaisyUI (checkbox / file / ช่องข้อความ)
    page = _strip_templates(html)
    for match in re.finditer(r"<input\b[^>]*>", page):
        tag = match.group(0)
        kind = re.search(r'type="([^"]+)"', tag)
        kind = kind.group(1) if kind else "text"
        if kind in ("hidden", "radio") or "drawer-toggle" in tag:
            continue
        if kind == "checkbox":
            assert re.search(r'class="[^"]*\b(checkbox|toggle)\b', tag) or "drawer-toggle" in tag, tag
        elif kind == "file":
            assert "file-input" in tag, tag
        elif kind == "submit" or kind == "button":
            continue
        else:
            # ช่องข้อความมี class input เอง หรืออยู่ใน <label class="input ..."> (ช่องค้นหา)
            wrapper = page[max(0, match.start() - 160) : match.start()]
            assert re.search(r'class="[^"]*\binput\b', tag) or re.search(r'<label class="input\b[^>]*>[^<]*(<i[^>]*></i>)?\s*$', wrapper), tag
    for tag in re.findall(r"<textarea\b[^>]*>", html):
        assert "textarea" in tag, tag


def test_create_ma_item_division_selection_removed_and_auto_derived(world, client_for):
    client = client_for(world.creator)  # creator has division_it
    # 1. Open create form: verify responsible_divisions checkboxes are NOT present
    response = client.get(f"/procurement/products/create?{_q(world.org)}")
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'name="items-0-responsible_divisions"' not in html
    assert 'name="items-__I__-responsible_divisions"' not in html

    # 2. Submit MA: responsible_divisions automatically follows responsible_by member's division
    data = ma_form([
        _item(
            amount="30000.00",
            name="[TEST] Auto Division Item",
            responsible_by=[str(world.role_creator.id)],
        )
    ], total_amount="30000.00", psu="PSU-AUTO-DIV")
    create_res = _create(client, world, data)
    assert create_res.status_code == 302

    item = models.ProcurementItem.objects.get(name="[TEST] Auto Division Item")
    assert [d.id for d in item.responsible_divisions] == [world.division_it.id]
    assert item.has_custom_responsible_divisions is False

    # 3. Edit page also does not render division selector
    edit_html = client.get(_item_edit_url(world, item.procurement)).get_data(as_text=True)
    assert 'name="items-0-responsible_divisions"' not in edit_html


def test_responsible_by_shows_selected_members_in_form(world, client_for):
    client = client_for(world.creator)
    # 1. On create form, the creator is pre-selected by default and displayed in selected-members box
    res = client.get(f"/procurement/products/create?{_q(world.org)}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "ผู้รับผิดชอบที่เลือกแล้ว:" in html
    assert f'data-member-id="{world.role_creator.id}"' in html
    assert world.role_creator.display_user_fullname() in html
    assert 'data-action="deselect-member"' in html
    assert 'data-action="clear-all-members"' in html

    # 2. Create MA with two responsible members
    data = ma_form([
        _item(
            amount="50000.00",
            name="[TEST] Multi Member MA",
            responsible_by=[str(world.role_creator.id), str(world.role_admin.id)],
        )
    ], total_amount="50000.00", psu="PSU-MULTI-RESP")
    create_res = _create(client, world, data)
    assert create_res.status_code == 302

    item = models.ProcurementItem.objects.get(name="[TEST] Multi Member MA")
    assert len(item.responsible_by) == 2

    # 3. On edit form, both members are shown in selected-members box
    edit_html = client.get(_item_edit_url(world, item.procurement)).get_data(as_text=True)
    assert f'data-member-id="{world.role_creator.id}"' in edit_html
    assert f'data-member-id="{world.role_admin.id}"' in edit_html
    assert world.role_creator.display_user_fullname() in edit_html
    assert world.role_admin.display_user_fullname() in edit_html


def test_create_ma_duplicates_child_procurements_with_parent_reference(world, client_for):
    client = client_for(world.admin)
    data = ma_form([
        _item(
            amount="40000.00",
            name="[TEST] Sub-item Alpha",
            responsible_by=[str(world.role_creator.id)],
        ),
        _item(
            amount="60000.00",
            name="[TEST] Sub-item Beta",
            responsible_by=[str(world.role_admin.id)],
        ),
    ], total_amount="100000.00", name="[TEST] Master Contract", company="[TEST] Mega Corp", psu="PSU-PARENT-CHILD")
    res = _create(client, world, data)
    assert res.status_code == 302

    # Master procurement
    master = models.Procurement.objects.get(psu_disbursement_number="PSU-PARENT-CHILD", parent_procurement=None)
    assert master.name == "[TEST] Master Contract"
    assert master.total_amount == Decimal("100000.00")
    assert master.has_child_procurements() is True

    # Children
    children = master.get_child_procurements()
    assert len(children) == 2
    assert [c.name for c in children] == ["[TEST] Sub-item Alpha", "[TEST] Sub-item Beta"]
    assert [c.total_amount for c in children] == [Decimal("40000.00"), Decimal("60000.00")]
    assert all(c.company == "[TEST] Mega Corp" for c in children)
    assert all(c.psu_disbursement_number == "PSU-PARENT-CHILD" for c in children)
    assert all(c.parent_procurement.id == master.id for c in children)

    # Master detail page shows children
    master_html = client.get(f"/procurement/payment/{master.id}?{_q(world.org)}").get_data(as_text=True)
    assert f"{master.name} แยกเป็น {len(children)} รายการย่อย" in master_html
    assert "[TEST] Sub-item Alpha" in master_html

    # Child detail page shows link to master
    child_html = client.get(f"/procurement/payment/{children[0].id}?{_q(world.org)}").get_data(as_text=True)
    assert "เป็นสัญญาย่อยที่แยกมาจากสัญญาหลัก" in child_html
    assert master.name in child_html

    # Products table shows child items separated and excludes master container
    table_html = client.get(f"/procurement/products?{_q(world.org)}").get_data(as_text=True)
    assert "ชื่อโครงการ" in table_html
    assert master.name in table_html
    # ป้าย "สัญญาย่อย" ไม่แสดงในตารางแล้ว ปุ่มแสดงงวดการจ่ายอยู่ในคอลัมน์ชื่อโครงการแทน
    assert "สัญญาย่อย" not in table_html.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
    assert "การจ่ายเงิน (จ่ายครั้งเดียวก่อนสิ้นสุด)" in table_html
    assert "สัญญาย่อยของ:" not in table_html
    assert "[TEST] Sub-item Alpha" in table_html
    assert "[TEST] Sub-item Beta" in table_html
    assert "สัญญาหลัก (2 สัญญาย่อย)" not in table_html


def test_payment_reminder_visibility_based_on_installment_mode(world, client_for):
    client = client_for(world.admin)

    # 1. Non-installment mode:
    # Form: container has 'hidden' class
    create_html = client.get(f"/procurement/products/create?{_q(world.org)}").get_data(as_text=True)
    assert 'class="payment-reminder-container hidden" data-payment-reminder>' in create_html

    # Create MA without installments
    data_no_inst = ma_form([
        _item(
            amount="10000.00",
            installment_mode="",  # False / off
        )
    ], total_amount="10000.00", psu="PSU-NO-INST")
    res = _create(client, world, data_no_inst)
    assert res.status_code == 302

    ma_no_inst = models.Procurement.objects.get(psu_disbursement_number="PSU-NO-INST")
    item_no_inst = ma_no_inst.get_items()[0]
    assert item_no_inst.pays_in_installments() is False
    assert item_no_inst.payment_reminder_offsets == []

    # Detail page does NOT show "เตือนจ่ายงวดล่วงหน้า"
    detail_html = client.get(f"/procurement/payment/{ma_no_inst.id}?{_q(world.org)}").get_data(as_text=True)
    assert "เตือนหมดอายุล่วงหน้า" in detail_html
    assert "เตือนจ่ายงวดล่วงหน้า" not in detail_html

    # 2. Installment mode:
    # Create MA with installments
    data_inst = ma_form([
        _item(
            amount="20000.00",
            installment_mode="y",
            payment_reminder_offsets=["1m", "15d"],
            installments=[{"due_date": "2026-06-30"}, {"due_date": "2026-12-31"}],
        )
    ], total_amount="20000.00", psu="PSU-WITH-INST")
    res_inst = _create(client, world, data_inst)
    assert res_inst.status_code == 302

    ma_inst = models.Procurement.objects.get(psu_disbursement_number="PSU-WITH-INST")
    item_inst = ma_inst.get_items()[0]
    assert item_inst.pays_in_installments() is True
    assert item_inst.payment_reminder_offsets == ["1m", "15d"]

    # Detail page DOES show "เตือนจ่ายงวดล่วงหน้า"
    detail_inst_html = client.get(f"/procurement/payment/{ma_inst.id}?{_q(world.org)}").get_data(as_text=True)
    assert "เตือนหมดอายุล่วงหน้า" in detail_inst_html
    assert "เตือนจ่ายงวดล่วงหน้า" in detail_inst_html

    # Edit form for installment mode: container does not have hidden class
    edit_html = client.get(_item_edit_url(world, ma_inst)).get_data(as_text=True)
    assert 'class="payment-reminder-container" data-payment-reminder>' in edit_html


def test_edit_buttons_in_detail_page(world, client_for, existing_ma):
    item = existing_ma.get_items()[0]
    edit_url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"
    item_edit_url = f"{edit_url}&amp;item_id={item.id}"
    detail_url = f"/procurement/payment/{existing_ma.id}?{_q(world.org)}"
    # 1. Editor (admin or responsible) sees edit buttons
    editor_client = client_for(world.admin)
    detail_html = editor_client.get(detail_url).get_data(as_text=True)
    assert item_edit_url in detail_html  # "แก้ไข" ของรายการ -> โหมดแก้รายการเดียว
    assert edit_url in detail_html  # "แก้ไข MA" -> โหมดแก้เฉพาะหัว

    # Item edit form shows only that item; header edit form has no item cards
    edit_form_html = editor_client.get(f"{edit_url}&item_id={item.id}").get_data(as_text=True)
    assert f'id="item-{item.id}"' in edit_form_html
    assert 'data-action="remove-item"' not in edit_form_html and 'data-action="add-item"' not in edit_form_html
    header_html = editor_client.get(edit_url).get_data(as_text=True)
    assert 'name="items-0-name"' not in header_html

    # 2. Viewer (head without edit rights) cannot see edit buttons
    viewer_client = client_for(world.head)
    viewer_detail = viewer_client.get(detail_url).get_data(as_text=True)
    assert f"/procurement/products/{existing_ma.id}/edit" not in viewer_detail


def test_non_renewal_workflow_from_detail_page(world, client_for, existing_ma):
    client = client_for(world.admin)
    products_url = f"/procurement/products?{_q(world.org)}"
    detail_url = f"/procurement/payment/{existing_ma.id}?{_q(world.org)}"
    non_renewal_url = f"/procurement/requisitions/non-renewal?{_q(world.org)}"

    # 1. ตารางรายการ MA ไม่มีปุ่มขอต่ออายุ
    assert "request-renewal" not in client.get(products_url).get_data(as_text=True)

    # 2. หน้ารายละเอียดมีปุ่ม + modal ยืนยัน ไม่ต่ออายุ
    detail_html = client.get(detail_url).get_data(as_text=True)
    assert 'id="non_renewal_modal"' in detail_html
    assert f"/procurement/requisitions/{existing_ma.id}/non-renewal" in detail_html

    # 3. กดยืนยัน: redirect กลับหน้ารายละเอียด และสถานะเป็น disactive
    response = client.post(f"/procurement/requisitions/{existing_ma.id}/non-renewal?{_q(world.org)}")
    assert response.status_code == 302
    assert f"/procurement/payment/{existing_ma.id}" in response.headers["Location"]
    existing_ma.reload()
    assert existing_ma.status == "disactive"

    # 4. ขึ้นหน้าไม่ต่ออายุ และปุ่มหายจากหน้ารายละเอียด
    assert existing_ma.name in client.get(non_renewal_url).get_data(as_text=True)
    assert 'id="non_renewal_modal"' not in client.get(detail_url).get_data(as_text=True)


def test_detail_page_non_renewal_button_visibility(world, client_for, existing_ma):
    detail_url = f"/procurement/payment/{existing_ma.id}?{_q(world.org)}"

    # pending + ผู้แก้ไขได้: เห็นปุ่ม
    existing_ma.status = "pending"
    existing_ma.save()
    html = client_for(world.admin).get(detail_url).get_data(as_text=True)
    assert 'id="non_renewal_modal"' in html and "ไม่ต่ออายุ" in html

    # ผู้ดูที่แก้ไม่ได้: ไม่เห็น
    viewer_html = client_for(world.head).get(detail_url).get_data(as_text=True)
    assert 'id="non_renewal_modal"' not in viewer_html

    # active: ไม่เห็นแม้เป็นผู้แก้ไข
    existing_ma.status = "active"
    existing_ma.save()
    active_html = client_for(world.admin).get(detail_url).get_data(as_text=True)
    assert 'id="non_renewal_modal"' not in active_html


def test_products_table_sub_items_toggle_and_quick_pay(world, client_for, existing_ma):
    client = client_for(world.admin)
    products_url = f"/procurement/products?{_q(world.org)}"

    # 1. Products page has toggle button and sub-items expandable row
    html = client.get(products_url).get_data(as_text=True)
    assert f'id="btn_toggle_{existing_ma.id}"' in html
    assert f'id="sub_items_{existing_ma.id}"' in html
    assert "การจ่ายเงิน (จ่ายครั้งเดียวก่อนสิ้นสุด)" in html
    # ไม่ได้ติ๊ก "แบ่งจ่ายเป็นงวด": ไม่แสดงเป็นงวด
    assert "จ่ายแล้ว 0/1 งวด" not in html
    assert "งวดที่ 1" not in html.split("<tbody>", 1)[-1].split("</tbody>", 1)[0]
    assert "รายการย่อย (1)" not in html
    item = existing_ma.get_items()[0]
    assert item.name in html

    # 2. Quick-pay an installment with next url
    installment = item.installments[0]
    pay_url = f"/procurement/payment/{existing_ma.id}/items/{item.id}/installments/{installment._id}/pay?{_q(world.org)}"
    pay_res = client.post(
        pay_url,
        data={
            "paid_date": "2026-11-05",
            "payment_number": "PAY-QUICK-001",
            "paid_amount": "50000.00",
            "next": products_url,
        },
    )
    # Redirects back to next_url (products)
    assert pay_res.status_code == 302
    assert pay_res.headers["Location"] == products_url

    # Check products table reflects paid status and chevron size
    updated_html = client.get(products_url).get_data(as_text=True)
    assert "จ่ายครบแล้ว" in updated_html or "จ่ายแล้ว" in updated_html
    assert "PAY-QUICK-001" in updated_html
    assert f'id="caret_{existing_ma.id}"' in updated_html
    assert "text-[10px]" in updated_html

    # Check unpay confirmation modal is present with CSRF token
    unpay_modal_id = f"quick_unpay_{item.id}_{installment._id}"
    assert f'id="{unpay_modal_id}"' in updated_html
    assert "ยืนยันยกเลิกการบันทึกจ่าย" in updated_html
    modal_part = updated_html.split(f'id="{unpay_modal_id}"', 1)[1].split("</dialog>", 1)[0]
    token_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', modal_part)
    assert token_match is not None
    token = token_match.group(1)

    # 3. Quick-unpay from products table with CSRF token
    unpay_url = f"/procurement/payment/{existing_ma.id}/items/{item.id}/installments/{installment._id}/unpay?{_q(world.org)}"
    unpay_res = client.post(
        unpay_url,
        data={
            "csrf_token": token,
            "next": products_url,
        },
        follow_redirects=True,
    )
    assert unpay_res.status_code == 200
    final_html = unpay_res.get_data(as_text=True)
    assert "ยกเลิกการบันทึกจ่ายงวดแล้ว" in final_html


def test_search_select_field_rendering(app):
    from flask import render_template_string
    from wtforms import Form, SelectField

    class Demo(Form):
        account_code = SelectField("ผังบัญชี", choices=[("", "- ไม่ระบุ -"), ("12030201", "12030201 อาคาร")])

    with app.test_request_context():
        form = Demo()
        html = render_template_string(
            "{% from 'procurement/macros/ma_form.html' import search_select_field %}{{ search_select_field(form.account_code, wrapper_class='md:col-span-2') }}",
            form=form,
        )

    assert "search-select-box" in html
    assert "search-select-input" in html
    assert "search-select-menu" in html
    assert "ph-magnifying-glass" in html
    assert "ph-caret-down" in html
    assert "search-select-clear" in html
    assert "md:col-span-2" in html
    assert "menu w-full" in html
    assert "search-select-option" in html


def test_create_ma_has_draft_button(world, client_for):
    client = client_for(world.admin)
    res = client.get(f"/procurement/products/create?{_q(world.org)}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert 'name="action" value="draft"' in html
    assert 'id="draft_btn"' in html
    assert "บันทึกแบบร่าง" in html
    assert 'name="action" value="save"' in html
    assert 'id="submit_btn"' in html
    assert "บันทึก MA" in html


def test_create_ma_save_as_draft(world, client_for):
    client = client_for(world.admin)
    form_data = _two_item_form(world)
    form_data["action"] = "draft"
    res = _create(client, world, form_data)
    assert res.status_code == 302

    procurement = models.Procurement.objects.get(parent_procurement=None)
    assert procurement.status == "draft"

    children = list(models.Procurement.objects(parent_procurement=procurement))
    assert len(children) == 2
    for child in children:
        assert child.status == "draft"

    # Drafts are no longer rows of the table: they are offered from the "เพิ่ม MA" menu
    index_res = client.get(f"/procurement/products?{_q(world.org)}")
    assert index_res.status_code == 200
    index_html = index_res.get_data(as_text=True)
    assert "แบบร่างที่ค้างอยู่" in index_html
    target_id = str(procurement.id)
    assert f"/procurement/products/{target_id}/edit" in index_html
    assert f"/procurement/products/{children[0].id}/edit" not in index_html
    assert f"modal_delete_draft_{target_id}" in index_html
    assert f"/procurement/payment/{target_id}" not in index_html
    assert 'class="badge badge-warning' not in index_html.split("<tbody>", 1)[-1]

    # Check that payment detail redirects to edit
    detail_res = client.get(f"/procurement/payment/{procurement.id}?{_q(world.org)}")
    assert detail_res.status_code == 302
    assert f"/procurement/products/{procurement.id}/edit" in detail_res.headers["Location"]

    # Back button of a draft goes to the list like cancel (payment detail would redirect straight back to edit)
    edit_html = client.get(f"/procurement/products/{procurement.id}/edit?{_q(world.org)}").get_data(as_text=True)
    list_url = f"/procurement/products?organization_id={world.org.id}"
    assert f'href="{list_url}"' in edit_html
    assert f'href="/procurement/payment/{procurement.id}?organization_id={world.org.id}"' not in edit_html

    # Check that renew redirects to edit
    renew_res = client.get(f"/procurement/products/{procurement.id}/renew?{_q(world.org)}")
    assert renew_res.status_code == 302
    assert f"/procurement/products/{procurement.id}/edit" in renew_res.headers["Location"]


def test_delete_draft_procurement(world, client_for):
    client = client_for(world.admin)
    form_data = _two_item_form(world)
    form_data["action"] = "draft"
    _create(client, world, form_data)

    procurement = models.Procurement.objects.get(parent_procurement=None)
    assert procurement.status == "draft"
    proc_id = str(procurement.id)

    # Delete draft via POST
    del_res = client.post(
        f"/procurement/products/{proc_id}/delete?{_q(world.org)}",
        follow_redirects=True,
    )
    assert del_res.status_code == 200
    assert "ลบแบบร่าง" in del_res.get_data(as_text=True)

    # Verify completely deleted from database
    assert models.Procurement.objects(id=proc_id).count() == 0
    assert models.Procurement.objects(parent_procurement=procurement).count() == 0
    assert models.ProcurementItem.objects(procurement=proc_id).count() == 0


def test_cannot_delete_active_procurement(world, client_for):
    client = client_for(world.admin)
    form_data = _two_item_form(world)
    form_data["action"] = "save"
    _create(client, world, form_data)

    procurement = models.Procurement.objects.get(parent_procurement=None)
    assert procurement.status == "active"
    proc_id = str(procurement.id)

    # Attempt to delete active MA
    del_res = client.post(
        f"/procurement/products/{proc_id}/delete?{_q(world.org)}",
        follow_redirects=True,
    )
    assert del_res.status_code == 200
    assert "สามารถลบได้เฉพาะรายการที่เป็นแบบร่างเท่านั้น" in del_res.get_data(as_text=True)
    assert models.Procurement.objects(id=proc_id).count() == 1


def test_save_draft_with_incomplete_fields(world, client_for):
    client = client_for(world.admin)
    form_data = {
        "name": "[TEST] Draft Incomplete Project",
        "action": "draft",
        "items-0-name": "[TEST] Item 1",
        "items-0-category": "ma",
        "items-0-amount": "5000.00",
        "items-0-quantity": "1",
    }
    res = _create(client, world, form_data)
    assert res.status_code == 302

    procurement = models.Procurement.objects.get(name="[TEST] Draft Incomplete Project")
    assert procurement.status == "draft"
    assert procurement.psu_disbursement_number == ""
    assert procurement.company == "-"
    assert procurement.total_amount == Decimal("5000.00")
    items = procurement.get_items()
    assert len(items) == 1
    assert items[0].start_date is None
    assert items[0].end_date is None


def test_edit_draft_to_active(world, client_for):
    client = client_for(world.admin)
    form_data = _two_item_form(world)
    form_data["action"] = "draft"
    res = _create(client, world, form_data)
    assert res.status_code == 302

    procurement = models.Procurement.objects.get(parent_procurement=None)
    assert procurement.status == "draft"

    # Edit and publish with action="save"
    edit_data = _two_item_form(world)
    edit_data["action"] = "save"
    edit_data["version"] = procurement.get_version()
    edit_res = client.post(
        f"/procurement/products/{procurement.id}/edit?{_q(world.org)}",
        data=edit_data,
        follow_redirects=True,
    )
    assert edit_res.status_code == 200
    procurement.reload()
    assert procurement.status == "active"
    for child in models.Procurement.objects(parent_procurement=procurement):
        assert child.status == "active"


def test_installment_table_shows_due_amount_column(world, client_for):
    client = client_for(world.admin)
    form_data = _two_item_form(world)
    form_data["action"] = "save"
    res = _create(client, world, form_data)
    assert res.status_code == 302

    # Check products table
    idx = client.get(f"/procurement/products?{_q(world.org)}")
    assert idx.status_code == 200
    assert "ยอดที่ต้องจ่าย (บาท)" in idx.text

    # Check payment detail page
    parent = models.Procurement.objects.get(parent_procurement=None)
    pay = client.get(f"/procurement/payment/{parent.id}?{_q(world.org)}")
    assert pay.status_code == 200
    assert "ยอดที่ต้องจ่าย (บาท)" in pay.text





