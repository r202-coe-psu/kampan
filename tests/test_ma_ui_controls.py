"""ตัวควบคุมของหน้า MA: dropdown DaisyUI แทน <select>, ปฏิทิน พ.ศ., ไม่มีช่องรูปภาพ และไม่มี native control"""

import datetime
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
    assert re.search(r'data-value="b" aria-selected="true"\s+class="menu-active"', html)
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


def test_calendar_shows_buddhist_year_label_and_th_locale_but_posts_iso(world, client_for, existing_ma):
    html = client_for(world.admin).get(f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}").get_data(as_text=True)

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
    assert not models.Procurement.objects.get().image


@pytest.mark.parametrize(
    "path",
    [
        "/procurement/products/create?{q}",
        "/procurement/products/{id}/edit?{q}",
        "/procurement/products/{id}/renew?{q}",
        "/procurement/payment/{id}?{q}",
        "/procurement/products?{q}",
        "/procurement/requisitions?{q}",
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
    edit_html = client.get(f"/procurement/products/{item.procurement.id}/edit?{_q(world.org)}").get_data(as_text=True)
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
    edit_html = client.get(f"/procurement/products/{item.procurement.id}/edit?{_q(world.org)}").get_data(as_text=True)
    assert f'data-member-id="{world.role_creator.id}"' in edit_html
    assert f'data-member-id="{world.role_admin.id}"' in edit_html
    assert world.role_creator.display_user_fullname() in edit_html
    assert world.role_admin.display_user_fullname() in edit_html


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
    edit_html = client.get(f"/procurement/products/{ma_inst.id}/edit?{_q(world.org)}").get_data(as_text=True)
    assert 'class="payment-reminder-container" data-payment-reminder>' in edit_html


def test_edit_buttons_in_detail_and_requisition_pages(world, client_for, existing_ma):
    item = existing_ma.get_items()[0]
    edit_url = f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}"
    item_edit_url = f"{edit_url}#item-{item.id}"
    detail_url = f"/procurement/payment/{existing_ma.id}?{_q(world.org)}"
    requisition_url = f"/procurement/requisitions?{_q(world.org)}"

    # 1. Editor (admin or responsible) sees edit buttons
    editor_client = client_for(world.admin)
    detail_html = editor_client.get(detail_url).get_data(as_text=True)
    assert item_edit_url in detail_html
    assert edit_url in detail_html

    req_html = editor_client.get(requisition_url).get_data(as_text=True)
    assert edit_url in req_html

    # Edit form anchors to item id
    edit_form_html = editor_client.get(edit_url).get_data(as_text=True)
    assert f'id="item-{item.id}"' in edit_form_html

    # 2. Viewer (head without edit rights) cannot see edit buttons
    viewer_client = client_for(world.head)
    viewer_detail = viewer_client.get(detail_url).get_data(as_text=True)
    assert f"/procurement/products/{existing_ma.id}/edit" not in viewer_detail

    viewer_req = viewer_client.get(requisition_url).get_data(as_text=True)
    assert f"/procurement/products/{existing_ma.id}/edit" not in viewer_req


def test_renewal_request_and_non_renewal_workflow(world, client_for, existing_ma):
    client = client_for(world.admin)
    products_url = f"/procurement/products?{_q(world.org)}"
    requisitions_url = f"/procurement/requisitions?{_q(world.org)}"
    non_renewal_url = f"/procurement/requisitions/non-renewal?{_q(world.org)}"

    # 1. On products page, existing_ma has request-renewal button & modal
    products_html = client.get(products_url).get_data(as_text=True)
    assert f"modal_request_renewal_{existing_ma.id}" in products_html
    assert f"/procurement/products/{existing_ma.id}/request-renewal" in products_html

    # In requisitions page initially, existing_ma (status 'pending') is shown
    # Let's change existing_ma to 'active'
    existing_ma.status = "active"
    existing_ma.save()

    # When active, it is NOT in requisitions page (only renewal-requested or pending are shown)
    req_html_before = client.get(requisitions_url).get_data(as_text=True)
    assert existing_ma.name not in req_html_before

    # 2. Request renewal from products page
    req_post = client.post(
        f"/procurement/products/{existing_ma.id}/request-renewal?{_q(world.org)}",
        follow_redirects=True,
    )
    assert req_post.status_code == 200
    existing_ma.reload()
    assert existing_ma.status == "renewal-requested"

    # Now it appears in requisitions page with "ต่ออายุ" and "ไม่ต่ออายุ" buttons
    req_html_after = client.get(requisitions_url).get_data(as_text=True)
    assert existing_ma.name in req_html_after
    assert f"delete_modal_{existing_ma.id}" in req_html_after
    assert "ไม่ต่ออายุ" in req_html_after

    # 3. Mark non-renewal
    non_renew_res = client.post(
        f"/procurement/requisitions/{existing_ma.id}/non-renewal?{_q(world.org)}",
        follow_redirects=True,
    )
    assert non_renew_res.status_code == 200
    existing_ma.reload()
    assert existing_ma.status == "disactive"

    # Now it is NOT in requisitions, but IS in non-renewal page
    req_html_final = client.get(requisitions_url).get_data(as_text=True)
    assert existing_ma.name not in req_html_final

    non_renew_html = client.get(non_renewal_url).get_data(as_text=True)
    assert existing_ma.name in non_renew_html


def test_products_table_sub_items_toggle_and_quick_pay(world, client_for, existing_ma):
    client = client_for(world.admin)
    products_url = f"/procurement/products?{_q(world.org)}"

    # 1. Products page has toggle button and sub-items expandable row
    html = client.get(products_url).get_data(as_text=True)
    assert f'id="btn_toggle_{existing_ma.id}"' in html
    assert f'id="sub_items_{existing_ma.id}"' in html
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


