"""ตั้งค่าการเตือนของรายการย่อยในฟอร์ม MA (#28, #29) และการ copy ตอนต่ออายุ (#32)

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
import re
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models

DEFAULTS = ["3m", "2m", "1m", "15d", "7d"]


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
    assert _checked_values(html, "items-0-payment_reminder_offsets") == DEFAULTS
    # รายการย่อยที่เพิ่มด้วยปุ่ม (template) ก็ติ๊กค่าเริ่มต้น
    assert _checked_values(html, "items-__I__-expiry_reminder_offsets") == DEFAULTS


def test_create_saves_checked_offsets_custom_days_and_thai_dates(world, client):
    response = _create(
        client,
        world,
        _form(
            world,
            expiry_reminder_offsets=["6m", "1m"],
            payment_reminder_offsets=["7d"],
            **{
                "reminder_offsets_days-0": "45",
                "reminder_offsets_days-3": "10",
                "reminder_offsets_days-4": "",
                "custom_reminder_dates-0": "28/05/2570",
                "custom_reminder_dates-2": "1/4/2571",
            },
        ),
    )

    assert response.status_code == 302, response.get_data(as_text=True)
    item = models.ProcurementItem.objects.get()
    assert item.expiry_reminder_offsets == ["6m", "1m"]
    assert item.payment_reminder_offsets == ["7d"]
    assert item.reminder_offsets_days == [45, 10]
    assert item.custom_reminder_dates == [datetime.datetime(2027, 5, 28), datetime.datetime(2028, 4, 1)]


def test_unchecking_all_offsets_is_kept(world, client):
    response = _create(client, world, _form(world))

    assert response.status_code == 302
    item = models.ProcurementItem.objects.get()
    assert item.expiry_reminder_offsets == [] and item.payment_reminder_offsets == []


@pytest.mark.parametrize(
    "days, message",
    [
        (["0"], "จำนวนวันเตือนต้องเป็นจำนวนเต็ม 1–730 (0)"),
        (["731"], "จำนวนวันเตือนต้องเป็นจำนวนเต็ม 1–730 (731)"),
        (["-5"], "จำนวนวันเตือนต้องเป็นจำนวนเต็ม 1–730 (-5)"),
        (["abc"], "จำนวนวันเตือนต้องเป็นจำนวนเต็ม 1–730 (abc)"),
        (["45", "45"], "จำนวนวันเตือนซ้ำ (45)"),
    ],
)
def test_invalid_custom_days_rejected(world, client, days, message):
    data = _form(world, **{f"reminder_offsets_days-{index}": value for index, value in enumerate(days)})

    response = _create(client, world, data)

    assert response.status_code == 200
    assert message in response.get_data(as_text=True)
    assert models.ProcurementItem.objects.count() == 0


@pytest.mark.parametrize(
    "dates, message",
    [
        (["30/02/2570"], "ไม่มีวันที่นี้ในปฏิทิน (30/02/2570)"),
        (["28/05/2027"], "กรุณากรอกปีเป็น พ.ศ. (28/05/2027)"),
        (["2027-05-28"], "รูปแบบวันที่ต้องเป็น วว/ดด/ปปปป (พ.ศ.) (2027-05-28)"),
        (["28/05/2570", "28/5/2570"], "วันที่เตือนซ้ำ"),
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
            payment_reminder_offsets=["1m", "7d"],
            **{"reminder_offsets_days-0": "45", "custom_reminder_dates-0": "28/05/2570"},
        ),
    )
    procurement = models.Procurement.objects.get()

    html = client.get(
        f"/procurement/products/{procurement.id}/edit?organization_id={world.org.id}"
    ).get_data(as_text=True)

    assert _checked_values(html, "items-0-expiry_reminder_offsets") == ["2m"]
    assert _checked_values(html, "items-0-payment_reminder_offsets") == ["1m", "7d"]
    assert _input_values(html, "items-0-reminder_offsets_days") == ["45"]
    assert _input_values(html, "items-0-custom_reminder_dates") == ["28/05/2570"]


def test_detail_page_shows_reminder_settings(world, client):
    _create(
        client,
        world,
        _form(
            world,
            expiry_reminder_offsets=["2m"],
            **{"reminder_offsets_days-0": "45", "custom_reminder_dates-0": "28/05/2570"},
        ),
    )
    procurement = models.Procurement.objects.get()

    html = client.get(f"/procurement/payment/{procurement.id}?organization_id={world.org.id}").get_data(as_text=True)

    assert "ตั้งค่าการเตือน" in html
    assert "2 เดือน" in html and "45 วัน" in html and "28/05/2570" in html


def test_renew_copies_offsets_and_custom_days_but_not_custom_dates(world, client):
    old = models.Procurement(
        psu_disbursement_number="PSU-OLD",
        name="[TEST] MA เดิม",
        company="[TEST] บริษัท",
        organization=world.org,
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
                payment_reminder_offsets=["15d"],
                reminder_offsets_days=[45],
                custom_reminder_dates=[datetime.datetime(2025, 6, 1)],
                installments=[models.Installment(due_date=datetime.datetime(2025, 12, 31))],
            )
        ]
    )

    html = client.get(f"/procurement/products/{old.id}/renew?organization_id={world.org.id}").get_data(as_text=True)

    assert _checked_values(html, "items-0-expiry_reminder_offsets") == ["6m"]
    assert _checked_values(html, "items-0-payment_reminder_offsets") == ["15d"]
    assert _input_values(html, "items-0-reminder_offsets_days") == ["45"]
    assert _input_values(html, "items-0-custom_reminder_dates") == []
