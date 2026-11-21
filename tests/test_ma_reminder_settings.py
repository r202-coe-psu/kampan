"""ตั้งค่าการเตือนของรายการย่อยในฟอร์ม MA (#28, #29) และการ copy ตอนต่ออายุ (#32)

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models

DEFAULTS = ["3m", "2m", "1m", "15d", "7d", "3d"]


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org")
    admin = create_user("Admin", "Settings")
    role_admin = assign_user_to_org(admin, org, roles=["admin"])
    return SimpleNamespace(org=org, admin=admin, role_admin=role_admin)


@pytest.fixture
def client(app, login_as, world):
    return login_as(app.test_client(), world.admin)


def _form(world, **item_fields):
    data = {
        "psu_disbursement_number": "PSU-1",
        "name": "[TEST] MA",
        "company": "[TEST] บริษัท",
        "total_amount": "100.00",
        "items-0-name": "[TEST] License",
        "items-0-category": "software",
        "items-0-start_date": "2026-01-01",
        "items-0-end_date": "2027-12-31",
        "items-0-amount": "100.00",
        "items-0-reminder_kind": "ma",
        "items-0-responsible_by": [str(world.role_admin.id)],
        "items-0-installments-0-due_date": "2027-12-31",
    }
    data.update({f"items-0-{key}": value for key, value in item_fields.items()})
    return data


def _create(client, world, data):
    return client.post(f"/procurement/products/create?organization_id={world.org.id}", data=data)


def _checked_values(html, name):
    values = []
    for tag in re.findall(rf'<input[^>]*name="{re.escape(name)}"[^>]*>', html):
        if re.search(r"\bchecked\b", tag):
            values.append(re.search(r'value="([^"]*)"', tag).group(1))
    return values


def _input_values(html, prefix):
    return [
        re.search(r'value="([^"]*)"', tag).group(1) if 'value="' in tag else ""
        for tag in re.findall(rf'<input[^>]*name="{re.escape(prefix)}-\d+"[^>]*>', html)
    ]


def test_create_form_checks_default_offsets_for_expiry_and_payment(world, client):
    html = client.get(f"/procurement/products/create?organization_id={world.org.id}").get_data(as_text=True)

    assert _checked_values(html, "items-0-expiry_reminder_offsets") == DEFAULTS
    # เตือนจ่ายงวดล่วงหน้า (7 / 5 / 3 วัน) ค่าเริ่มต้นไม่ติ๊ก (เตือนวันครบกำหนดเสมอ)
    assert _checked_values(html, "items-0-payment_reminder_offsets") == []
    assert re.findall(r'name="items-0-payment_reminder_offsets" value="(\w+)"', html) == ["7d", "5d", "3d"]
    # รายการย่อยที่เพิ่มด้วยปุ่ม (template) ก็ติ๊กค่าเริ่มต้น
    assert _checked_values(html, "items-__I__-expiry_reminder_offsets") == DEFAULTS


def test_create_saves_checked_offsets_and_thai_dates_ignoring_custom_days(world, client):
    response = _create(
        client,
        world,
        _form(
            world,
            expiry_reminder_offsets=["6m", "1m", "3d"],
            installment_mode="y",
            payment_reminder_offsets=["7d"],
            **{
                # ช่องกำหนดเองถูกนำออกจากฟอร์ม: ค่าที่ส่งมาถูกเมิน ไม่ถูกเก็บ
                "reminder_offsets_days-0": "45",
                "reminder_offsets_days-3": "10",
                "custom_reminder_dates-0": "2027-05-28",
                "custom_reminder_dates-2": "2028-04-01",  # แถวที่ 1 ว่าง (ยังไม่เลือกวัน) ถูกข้าม
            },
        ),
    )

    assert response.status_code == 302, response.get_data(as_text=True)
    item = models.ProcurementItem.objects.get()
    assert item.expiry_reminder_offsets == ["6m", "1m", "3d"]
    assert item.payment_reminder_offsets == ["7d"]
    assert item.reminder_offsets_days == []
    assert item.custom_reminder_dates == [datetime.datetime(2027, 5, 28), datetime.datetime(2028, 4, 1)]


def test_unchecking_all_offsets_is_kept(world, client):
    response = _create(client, world, _form(world))

    assert response.status_code == 302
    item = models.ProcurementItem.objects.get()
    assert item.expiry_reminder_offsets == [] and item.payment_reminder_offsets == []


@pytest.mark.parametrize(
    "dates, message",
    [
        (["2027-02-30"], "รูปแบบวันที่ไม่ถูกต้อง"),
        (["28/05/2570"], "รูปแบบวันที่ไม่ถูกต้อง"),
        (["2027-05-28", "2027-05-28"], "วันที่เตือนซ้ำ (28/05/2570)"),
    ],
)
def test_invalid_custom_dates_rejected(world, client, dates, message):
    data = _form(world, **{f"custom_reminder_dates-{index}": value for index, value in enumerate(dates)})

    response = _create(client, world, data)

    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    assert models.ProcurementItem.objects.count() == 0


def test_edit_form_shows_saved_settings_with_buddhist_year(world, client):
    _create(
        client,
        world,
        _form(
            world,
            expiry_reminder_offsets=["2m"],
            installment_mode="y",
            payment_reminder_offsets=["7d", "5d"],
            **{"custom_reminder_dates-0": "2027-05-28"},
        ),
    )
    procurement = models.Procurement.objects.get()

    item = models.ProcurementItem.objects(procurement=procurement).get()
    html = client.get(
        f"/procurement/products/{procurement.id}/edit?organization_id={world.org.id}&item_id={item.id}"
    ).get_data(as_text=True)

    assert _checked_values(html, "items-0-expiry_reminder_offsets") == ["2m"]
    assert _checked_values(html, "items-0-payment_reminder_offsets") == ["7d", "5d"]
    assert "reminder_offsets_days" not in html
    assert _input_values(html, "items-0-custom_reminder_dates") == ["2027-05-28"]
    assert "28/05/2570" in html  # ปฏิทินแสดงปี พ.ศ.


def test_detail_page_shows_reminder_settings(world, client):
    _create(
        client,
        world,
        _form(
            world,
            expiry_reminder_offsets=["2m"],
            **{"custom_reminder_dates-0": "2027-05-28"},
        ),
    )
    procurement = models.Procurement.objects.get()
    models.ProcurementItem.objects.update(set__reminder_offsets_days=[45])  # ค่าเดิมที่เคยกรอกไว้ก่อนนำช่องออก

    html = client.get(f"/procurement/payment/{procurement.id}?organization_id={world.org.id}").get_data(as_text=True)

    assert "ตั้งค่าการเตือน" in html
    assert "60 วัน" in html and "45 วัน" in html and "28/05/2570" in html


def test_renew_copies_offsets_but_not_custom_dates_and_offers_no_custom_days_box(world, client):
    old = models.Procurement(
        psu_disbursement_number="PSU-OLD",
        name="[TEST] MA เดิม",
        company="[TEST] บริษัท",
        organization=world.org,
        status="renewal-requested",
        renewal_request="renew",
        total_amount=Decimal("100.00"),
        created_by=world.admin,
    )
    old.save_with_items(
        [
            models.ProcurementItem(
                name="[TEST] License",
                category="software",
                start_date=datetime.datetime(2025, 1, 1),
                end_date=datetime.datetime(2025, 12, 31),
                amount=Decimal("100.00"),
                responsible_by=[world.role_admin],
                expiry_reminder_offsets=["6m"],
                installment_mode=True,
                payment_reminder_offsets=["5d"],
                reminder_offsets_days=[45],
                custom_reminder_dates=[datetime.datetime(2025, 6, 1)],
                installments=[models.Installment(due_date=datetime.datetime(2025, 12, 31))],
            )
        ]
    )

    html = client.get(f"/procurement/products/{old.id}/renew?organization_id={world.org.id}").get_data(as_text=True)

    assert _checked_values(html, "items-0-expiry_reminder_offsets") == ["6m"]
    assert _checked_values(html, "items-0-payment_reminder_offsets") == ["5d"]
    assert "reminder_offsets_days" not in html
    assert _input_values(html, "items-0-custom_reminder_dates") == []


def test_toggle_off_item_stores_no_payment_offsets_and_form_places_them_under_installments(world, client):
    _create(client, world, _form(world, payment_reminder_offsets=["7d"]))  # ไม่ได้เปิดแบ่งงวด: ช่องเตือนจ่ายไม่ถูกใช้
    item = models.ProcurementItem.objects.get()
    assert item.payment_reminder_offsets == []

    html = client.get(f"/procurement/products/create?organization_id={world.org.id}").get_data(as_text=True)
    page = re.sub(r"<template.*?</template>", "", html, flags=re.S)
    # ช่องเตือนจ่ายงวดอยู่ใต้ส่วนการจ่ายเงิน (ต่อจากปุ่มเพิ่มงวด) ไม่ได้อยู่ในส่วนตั้งค่าการแจ้งเตือน
    assert page.index("data-action=\"add-installment\"") < page.index("data-payment-offsets")
    assert page.index("data-payment-offsets") < page.index("ตั้งค่าการแจ้งเตือน")


# --- ปรับหน้าตั้งค่าการแจ้งเตือน (2026-11-16) -----------------------------------


def _create_page(client, world):
    html = client.get(f"/procurement/products/create?organization_id={world.org.id}").get_data(as_text=True)
    return re.sub(r"<template.*?</template>", "", html, flags=re.S)


def test_expiry_offsets_offer_3_days_after_7(world, client):
    page = _create_page(client, world)

    assert re.findall(r'name="items-0-expiry_reminder_offsets" value="(\w+)"', page) == [
        "6m", "5m", "4m", "3m", "2m", "1m", "15d", "7d", "3d",
    ]
    assert dict(models.REMINDER_OFFSET_CHOICES)["3d"] == "3 วัน"
    # ค่าเริ่มต้นติ๊ก 3 วันด้วย
    assert _checked_values(page, "items-0-expiry_reminder_offsets") == DEFAULTS


def test_custom_days_box_is_gone_from_the_form(world, client):
    page = _create_page(client, world)

    assert "reminder_offsets_days" not in page
    assert "กำหนดเอง" not in page and "1–730" not in page
    # วันที่เตือนเจาะจงยังอยู่
    assert "items-0-custom_reminder_dates" in page or "custom_reminder_dates" in page


def test_reminder_settings_section_is_open_by_default(world, client):
    page = _create_page(client, world)

    heading = page.index("ตั้งค่าการแจ้งเตือน")
    details_tag = re.match(r"<details[^>]*>", page[page.rindex("<details", 0, heading):]).group(0)
    assert re.search(r"\bopen\b", details_tag), details_tag


def test_expiry_offsets_use_the_same_pill_design_as_payment_offsets(world, client):
    page = _create_page(client, world)

    def block(marker):
        start = page.index(marker)
        return page[start : page.index("</div>", start)]

    expiry, payment = block("data-expiry-offsets"), block("data-payment-offsets")
    pill = 'class="flex items-center gap-2 py-1 px-3 rounded-full border border-base-300 cursor-pointer"'
    assert expiry.count(pill) == 9 and payment.count(pill) == 3
    # หัวข้อและคำอธิบายแบบเดียวกัน: ข้อความหัวข้อ + ตัวเลือกเป็นแคปซูล + คำอธิบายเล็กใต้ตัวเลือก
    assert "เตือนหมดอายุล่วงหน้า" in page and "ก่อนวันที่สิ้นสุดของรายการย่อย" in page


def test_disbursement_date_is_labelled_vanthi_beikjai(world, client):
    page = _create_page(client, world)

    assert re.search(r"วันที่เบิกจ่าย", page)
    assert not re.search(r">\s*ลงวันที่\s*<", page)


def test_category_choices_put_rental_right_under_service():
    assert [value for value, _ in models.MA_CATEGORY_CHOICES] == [
        "ma", "service", "rental", "software", "product",
    ]
    assert dict(models.MA_CATEGORY_CHOICES)["rental"] == "เช่า"


# --- เลขที่ ม.อ.เบิกจ่ายขึ้นต้นด้วย 011/ ไว้ให้ (2026-11-20) ---------------------


def _psu_input_value(html):
    tag = re.search(r'<input[^>]*name="psu_disbursement_number"[^>]*>', html).group(0)
    return re.search(r'value="([^"]*)"', tag).group(1)


def test_psu_number_field_starts_with_011_prefix(world, client):
    assert _psu_input_value(_create_page(client, world)) == "011/"


def test_prefix_only_psu_number_is_treated_as_empty_when_required(world, client):
    # รายการไม่แบ่งจ่ายเป็นงวด = จ่ายแล้วตอนสร้าง MA จึงต้องมีเลขที่จริง คำนำหน้าอย่างเดียวไม่พอ
    data = _form(world)
    data["psu_disbursement_number"] = "011/"

    response = _create(client, world, data)

    assert response.status_code == 200
    assert "กรุณากรอกเลขที่ ม.อ.เบิกจ่าย" in response.get_data(as_text=True)
    assert models.Procurement.objects.count() == 0


def test_full_psu_number_with_prefix_is_saved(world, client):
    data = _form(world)
    data["psu_disbursement_number"] = "011/2569-0001"

    assert _create(client, world, data).status_code == 302
    assert models.Procurement.objects.get(parent_procurement=None).psu_disbursement_number == "011/2569-0001"


def test_draft_with_prefix_only_stores_empty_psu_number(world, client):
    data = _form(world)
    data["psu_disbursement_number"] = "011/"
    data["action"] = "draft"

    assert _create(client, world, data).status_code == 302
    assert models.Procurement.objects.get(parent_procurement=None).psu_disbursement_number == ""


def test_custom_reminder_dates_use_a_calendar_picker_with_a_row_template(world, client):
    page = client.get(f"/procurement/products/create?organization_id={world.org.id}").get_data(as_text=True)

    template = page[page.index("list-row-template"):]
    template = template[: template.index("</template>")]
    assert "data-date-picker" in template and "data-buddhist" in template
    assert 'name="items-0-custom_reminder_dates-__ROW__"' in template
    assert 'placeholder="28/05/2570"' not in page  # ไม่ใช่ช่องพิมพ์ข้อความอีกแล้ว
