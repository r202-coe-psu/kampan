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
