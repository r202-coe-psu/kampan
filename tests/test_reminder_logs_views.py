"""ประวัติการแจ้งเตือนในหน้ารายละเอียด MA + เพิ่ม log เอง (#30)

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org")
    other_org = create_org("[TEST] Org อื่น")

    def member(first_name, roles, organization=org):
        user = create_user(first_name, "Log")
        role = assign_user_to_org(user, organization, roles=roles)
        role.first_name = first_name
        role.last_name = "Log"
        role.save()
        return user, role

    admin, role_admin = member("Admin", ["admin"])
    creator, role_creator = member("Creator", ["staff"])
    responsible, role_responsible = member("Responsible", ["staff"])
    other_staff, role_other_staff = member("Other", ["staff"])
    head, role_head = member("Head", ["head"])
    admin_other, role_admin_other = member("AdminOther", ["admin"], organization=other_org)

    def ma(organization, name, responsible_by, created_by):
        procurement = models.Procurement(
            psu_disbursement_number="PSU-1",
            name=name,
            company="[TEST] บริษัท",
            organization=organization,
            total_amount=Decimal("100.00"),
            created_by=created_by,
        )
        items = [
            models.ProcurementItem(
                name=f"{name} รายการ {index}",
                category="software",
                start_date=datetime.datetime(2026, 1, 1),
                end_date=datetime.datetime(2026, 12, 31),
                amount=Decimal("50.00"),
                responsible_by=responsible_by,
                installments=[models.Installment(due_date=datetime.datetime(2026, 12, 31))],
            )
            for index in (1, 2)
        ]
        procurement.save_with_items(items)
        return procurement, procurement.get_items()

    procurement, (item1, item2) = ma(org, "[TEST] MA", [role_responsible], creator)
    other_procurement, (other_item, _) = ma(other_org, "[TEST] MA อื่น", [role_admin_other], admin_other)
    return SimpleNamespace(**locals())


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        return login_as(app.test_client(), user)

    return _client_for


def _detail_url(world, procurement=None, organization=None):
    procurement = procurement or world.procurement
    organization = organization or world.org
    return f"/procurement/payment/{procurement.id}?organization_id={organization.id}"


def _manual_url(world, procurement=None, item=None, organization=None):
    procurement = procurement or world.procurement
    item = item or world.item1
    organization = organization or world.org
    return f"/procurement/reminder_logs/{procurement.id}/items/{item.id}/manual?organization_id={organization.id}"


def _log(world, item, created, **fields):
    fields.setdefault("kind", "expiry")
    fields.setdefault("status", "sent")
    return models.ReminderLog(
        organization=item.organization,
        procurement=item.procurement,
        item=item,
        trigger_date=fields.pop("trigger_date", datetime.datetime(2026, 9, 30)),
        created_date=created,
        **fields,
    ).save()


def _section(html, item):
    """ส่วนของรายการย่อยนี้ในหน้ารายละเอียด (ตั้งแต่ id="item-<id>" จนถึงรายการถัดไป)"""
    start = html.index(f'id="item-{item.id}"')
    end = html.find('<section id="item-', start + 1)
    return html[start:] if end == -1 else html[start:end]


def test_history_lists_logs_of_each_item_newest_first(world, client_for):
    _log(world, world.item1, datetime.datetime(2026, 9, 1), recipients=["a@test.com"], note="ฉบับเก่า")
    _log(
        world,
        world.item1,
        datetime.datetime(2026, 10, 1),
        status="failed",
        recipients=["b@test.com"],
        error="ส่งไม่ถึง: b@test.com",
    )
    _log(world, world.item2, datetime.datetime(2026, 9, 15), kind="payment", note="ของรายการ 2")

    response = client_for(world.head).get(_detail_url(world))

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    first = _section(html, world.item1)
    assert "ประวัติการแจ้งเตือน" in first
    assert first.index("ส่งไม่ถึง: b@test.com") < first.index("ฉบับเก่า")
    assert "ส่งไม่สำเร็จ" in first and "ส่งแล้ว" in first
    assert "ของรายการ 2" not in first
    assert "ของรายการ 2" in _section(html, world.item2)


def test_history_empty_message(world, client_for):
    html = client_for(world.admin).get(_detail_url(world)).get_data(as_text=True)

    assert "ยังไม่มีประวัติการแจ้งเตือน" in _section(html, world.item1)


def test_history_of_ma_user_cannot_see_is_404(world, client_for):
    _log(world, world.item1, datetime.datetime(2026, 9, 1), note="ลับ")

    assert client_for(world.other_staff).get(_detail_url(world)).status_code == 404


def test_history_of_other_org_is_404(world, client_for):
    _log(world, world.other_item, datetime.datetime(2026, 9, 1), note="ของอีกหน่วยงาน")

    response = client_for(world.admin).get(_detail_url(world, world.other_procurement, world.org))

    assert response.status_code == 404


@pytest.mark.parametrize("who", ["admin", "creator", "responsible"])
def test_manual_log_by_user_who_can_edit(world, client_for, who):
    user = getattr(world, who)
    client = client_for(user)

    response = client.post(
        _manual_url(world),
        data={"contact_date": "28/05/2570", "recipients": "คุณสมชาย", "note": "โทรแจ้งแล้ว"},
    )

    assert response.status_code == 302
    assert f"/procurement/payment/{world.procurement.id}" in response.headers["Location"]
    log = models.ReminderLog.objects.get()
    assert (log.kind, log.status, log.note) == ("manual", "manual", "โทรแจ้งแล้ว")
    assert log.trigger_date == datetime.datetime(2027, 5, 28)
    assert log.recipients == ["คุณสมชาย"]
    assert log.created_by.id == user.id
    assert log.item.id == world.item1.id and log.organization.id == world.org.id
    assert log.dedupe_key is None
    html = client.get(_detail_url(world)).get_data(as_text=True)
    assert "บันทึกเอง" in _section(html, world.item1) and f"{who.capitalize()}" in _section(html, world.item1)


def test_two_manual_logs_same_day_are_both_saved(world, client_for):
    models.ReminderLog.ensure_indexes()
    client = client_for(world.admin)

    for note in ("โทรครั้งแรก", "โทรครั้งที่สอง"):
        client.post(_manual_url(world), data={"contact_date": "28/05/2570", "note": note})

    assert models.ReminderLog.objects(kind="manual").count() == 2


def test_manual_log_refused_for_viewer_who_cannot_edit(world, client_for):
    response = client_for(world.head).post(_manual_url(world), data={"contact_date": "28/05/2570", "note": "x"})

    assert response.status_code == 302
    assert models.ReminderLog.objects.count() == 0


def test_manual_log_by_user_who_cannot_see_ma_is_404(world, client_for):
    response = client_for(world.other_staff).post(_manual_url(world), data={"contact_date": "28/05/2570", "note": "x"})

    assert response.status_code == 404
    assert models.ReminderLog.objects.count() == 0


def test_manual_log_cross_tenant_is_404(world, client_for):
    client = client_for(world.admin)

    response = client.post(
        _manual_url(world, world.other_procurement, world.other_item, world.org),
        data={"contact_date": "28/05/2570", "note": "x"},
    )
    # item ของ org B แต่ MA ของ org A ก็ไม่ได้
    mixed = client.post(
        _manual_url(world, world.procurement, world.other_item, world.org),
        data={"contact_date": "28/05/2570", "note": "x"},
    )

    assert response.status_code == 404 and mixed.status_code == 404
    assert models.ReminderLog.objects.count() == 0
    # URL เดียวกันกับ item ของ org A ใช้ได้จริง (ไม่ได้ 404 เพราะยิงผิด route)
    ok = client.post(_manual_url(world), data={"contact_date": "28/05/2570", "note": "x"})
    assert ok.status_code == 302 and models.ReminderLog.objects.count() == 1


def test_manual_log_get_is_405(world, client_for):
    assert client_for(world.admin).get(_manual_url(world)).status_code == 405


@pytest.mark.parametrize(
    "data",
    [
        {"contact_date": "28/05/2570", "note": ""},
        {"contact_date": "30/02/2570", "note": "x"},
        {"contact_date": "28/05/2027", "note": "x"},
        {"contact_date": "", "note": "x"},
    ],
)
def test_manual_log_invalid_input_saves_nothing(world, client_for, data):
    response = client_for(world.admin).post(_manual_url(world), data=data)

    assert response.status_code == 302
    assert models.ReminderLog.objects.count() == 0


def test_manual_log_button_hidden_from_viewer(world, client_for):
    viewer_html = client_for(world.head).get(_detail_url(world)).get_data(as_text=True)
    editor_html = client_for(world.admin).get(_detail_url(world)).get_data(as_text=True)

    assert "/manual?" not in viewer_html
    assert "/manual?" in editor_html
