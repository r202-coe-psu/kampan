"""ซ่อนระบบขอซื้อขอจ้าง + แหล่งเงิน (MAS) ด้วย PROCUREMENT_REQUISITION_ENABLED (#18)

ค่าตั้งต้นคือปิด (web app ไม่ได้โหลด default_settings.py) เมื่อปิด route ของขอซื้อขอจ้างต้องตอบ 404
และเมนู การ์ด หน้าแรกของ module ต้องพาไปหน้า MA แทน · เมื่อเปิดทุกอย่างต้องกลับมาเหมือนเดิม

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from kampan import models
from kampan.web import redis_rq
from kampan.web.views import switch_organization_next_url

FLAG = "PROCUREMENT_REQUISITION_ENABLED"
REQUISITION_LINKS = (
    "/procurement/requisitions/renewal_requested",
    "/procurement/requisition_timeline",  # รวม requisition_timeline_items (รายการสินค้า)
    "/admin/mas/",
)
REQUISITION_MENU_TEXTS = ("ระบบ MAS", "การอนุมัติรายการขอซื้อขอจ้าง", "รายการรอดำเนินการ")


@pytest.fixture
def set_flag(app, monkeypatch):
    def _set_flag(value):
        monkeypatch.setitem(app.config, FLAG, value)

    # เริ่มจากไม่มีค่าใน config เลย เหมือน web app ที่ไม่ได้โหลด default_settings.py
    monkeypatch.delitem(app.config, FLAG, raising=False)
    return _set_flag


@pytest.fixture
def mock_queue(monkeypatch):
    calls = []

    class _Queue:
        def enqueue(self, *args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(get_id=lambda: "fake-job")

    monkeypatch.setattr(redis_rq.redis_queue, "queue", _Queue(), raising=False)
    return calls


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, create_ma):
    org = create_org("[TEST] Org")
    division = models.Division(name="[TEST] ฝ่าย", organization=org)
    division.save()

    users = {}
    roles = {}
    for role_name in ("admin", "staff", "head", "manager"):
        user = create_user(role_name.capitalize(), "Member")
        role = assign_user_to_org(user, org, roles=[role_name])
        role.division = division
        role.save()
        users[role_name] = user
        roles[role_name] = role

    requisition = models.Requisition(
        requisition_code="0001/2569",
        organization=org,
        purchaser=roles["staff"],
        start_date=datetime.datetime(2026, 11, 1),
        items=[
            models.RequisitionItem(
                product_name="เครื่องพิมพ์",
                quantity=1,
                category="product",
                amount=Decimal("10000.00"),
            )
        ],
        created_by=users["staff"],
    )
    requisition.save()

    mas = models.MAS(
        organization=org,
        year=2569,
        mas_code="MAS-A",
        description="งบ A",
        direction="-",
        amount=Decimal("100000.00"),
        remaining_amount=Decimal("100000.00"),
        reservable_amount=Decimal("100000.00"),
    )
    mas.save()

    procurement = create_ma(
        org,
        user=users["admin"],
        name="[TEST] MA",
        status="pending",
        responsible=[roles["staff"]],
    )

    return SimpleNamespace(
        org=org,
        users=users,
        roles=roles,
        requisition=requisition,
        mas=mas,
        procurement=procurement,
    )


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        client = app.test_client()
        login_as(client, user)
        return client

    return _client_for


def _q(world):
    return f"organization_id={world.org.id}"


# ---------------------------------------------------------------------------
# flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [(None, False), (False, False), ("False", False), ("0", False), (True, True), ("True", True), ("1", True)],
)
def test_flag_value_from_config_or_env_string(app, set_flag, value, expected):
    from kampan.web import feature_flags

    if value is not None:
        set_flag(value)

    with app.app_context():
        assert feature_flags.is_requisition_enabled() is expected


# ---------------------------------------------------------------------------
# route gating
# ---------------------------------------------------------------------------

GATED_GET_PATHS = (
    "/procurement/requisitions/renewal_requested",
    "/procurement/requisitions/create",
    "/procurement/requisition_timeline",
    "/procurement/requisition_timeline_items/",
    "/admin/mas/",
    "/admin/upload_files/template/mas",
)


@pytest.mark.parametrize("path", GATED_GET_PATHS)
def test_requisition_pages_404_when_flag_off(world, client_for, set_flag, path):
    client = client_for(world.users["admin"])

    response = client.get(f"{path}?{_q(world)}")

    assert response.status_code == 404


@pytest.mark.parametrize("path", GATED_GET_PATHS)
def test_requisition_pages_open_when_flag_on(world, client_for, set_flag, path):
    set_flag(True)
    client = client_for(world.users["admin"])

    response = client.get(f"{path}?{_q(world)}")

    assert response.status_code == 200


@pytest.mark.parametrize("suffix", ("document", "download/all", "edit"))
def test_requisition_detail_routes_404_when_flag_off(world, client_for, set_flag, suffix):
    client = client_for(world.users["admin"])

    response = client.get(f"/procurement/requisitions/{world.requisition.id}/{suffix}?{_q(world)}")

    assert response.status_code == 404


def _approve(client, world, approver_role, **extra):
    return client.post(
        f"/procurement/requisitions/{world.requisition.id}/action?{_q(world)}",
        data={"approver_role": approver_role, "action": "approved", **extra},
    )


def test_requisition_action_404_when_flag_off_without_reserving_mas(world, client_for, set_flag, mock_queue):
    admin_approval = {
        "fund_ids": str(world.mas.id),
        f"fund_amounts[{world.mas.id}]": "10000.00",
        "manager": str(world.roles["manager"].id),
    }
    set_flag(True)
    _approve(client_for(world.users["head"]), world, "head")

    set_flag(False)
    response = _approve(client_for(world.users["admin"]), world, "admin", **admin_approval)

    assert response.status_code == 404
    world.mas.reload()
    assert models.Reservation.objects(requisition=world.requisition).count() == 0
    assert world.mas.reservable_amount == Decimal("100000.00")

    # คำขอเดียวกันนี้จองเงินได้จริงเมื่อเปิด flag แสดงว่า 404 ข้างบนมาจาก flag ไม่ใช่ข้อมูลไม่ครบ
    set_flag(True)
    _approve(client_for(world.users["admin"]), world, "admin", **admin_approval)

    world.mas.reload()
    assert models.Reservation.objects(requisition=world.requisition).count() == 1
    assert world.mas.reservable_amount == Decimal("90000.00")


def test_old_renewal_action_404_when_flag_off_and_ma_unchanged(world, client_for, set_flag):
    client = client_for(world.users["admin"])
    requisitions_before = models.Requisition.objects.count()

    response = client.post(f"/procurement/requisitions/{world.procurement.id}/renewal-requested?{_q(world)}")

    assert response.status_code == 404
    world.procurement.reload()
    assert world.procurement.status == "pending"
    assert models.Requisition.objects.count() == requisitions_before


def test_old_renewal_action_still_works_when_flag_on(world, client_for, set_flag):
    set_flag(True)
    client = client_for(world.users["admin"])

    response = client.post(f"/procurement/requisitions/{world.procurement.id}/renewal-requested?{_q(world)}")

    assert response.status_code == 302
    world.procurement.reload()
    assert world.procurement.status == "renewal-requested"


# ---------------------------------------------------------------------------
# MA pages stay open
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    (
        "/procurement/requisitions/non-renewal",
        "/procurement/products",
        "/procurement/products/create",
        "/procurement/payment/{procurement_id}",
        "/procurement/manuals",
        "/admin/upload_files/",
        "/admin/upload_files/create",
        "/admin/upload_files/template/ma",
    ),
)
def test_ma_pages_open_when_flag_off(world, client_for, set_flag, path):
    client = client_for(world.users["admin"])

    response = client.get(f"{path.format(procurement_id=world.procurement.id)}?{_q(world)}")

    assert response.status_code == 200


def test_non_renewal_action_works_when_flag_off(world, client_for, set_flag):
    client = client_for(world.users["admin"])

    response = client.post(f"/procurement/requisitions/{world.procurement.id}/non-renewal?{_q(world)}")

    assert response.status_code == 302
    world.procurement.reload()
    assert world.procurement.status == "disactive"


def test_products_index_requires_login(app, world, set_flag):
    response = app.test_client().get(f"/procurement/products?{_q(world)}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# ---------------------------------------------------------------------------
# sidebar / select_system / module home
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", ("admin", "staff", "head", "manager"))
def test_sidebar_hides_requisition_menus_when_flag_off(world, client_for, set_flag, role):
    html = client_for(world.users[role]).get(f"/procurement/products?{_q(world)}").get_data(as_text=True)

    for link in REQUISITION_LINKS:
        assert link not in html
    for text in REQUISITION_MENU_TEXTS:
        assert text not in html
    # เมนูของระบบ MA ยังอยู่ครบ
    for link in (
        "/procurement/products?",
        "/procurement/requisitions/non-renewal?",
        "/admin/upload_files/?",
        "/procurement/manuals",
        "/select_system?",
    ):
        assert link in html


@pytest.mark.parametrize("role", ("admin", "staff", "head", "manager"))
def test_sidebar_shows_requisition_menus_when_flag_on(world, client_for, set_flag, role):
    set_flag(True)

    html = client_for(world.users[role]).get(f"/procurement/products?{_q(world)}").get_data(as_text=True)

    for link in REQUISITION_LINKS:
        assert link in html
    for text in REQUISITION_MENU_TEXTS:
        assert text in html


def test_select_system_card_goes_to_ma_list_when_flag_off(world, client_for, set_flag):
    html = client_for(world.users["admin"]).get(f"/select_system?{_q(world)}").get_data(as_text=True)

    assert f'href="/procurement/products?{_q(world)}"' in html
    assert "ระบบจัดการสัญญา (MA)" in html
    assert "ระบบขอซื้อขอจ้าง" not in html
    assert "/procurement/requisitions/renewal_requested" not in html


def test_select_system_card_unchanged_when_flag_on(world, client_for, set_flag):
    set_flag(True)

    html = client_for(world.users["admin"]).get(f"/select_system?{_q(world)}").get_data(as_text=True)

    assert f'href="/procurement/requisitions/renewal_requested?{_q(world)}"' in html
    assert "ระบบขอซื้อขอจ้าง" in html
    assert "ระบบจัดการสัญญา (MA)" not in html


@pytest.mark.parametrize(
    "enabled, expected_path",
    [(False, "/procurement/products"), (True, "/procurement/requisitions/renewal_requested")],
)
@pytest.mark.parametrize("current_path", ("/procurement/requisitions/non-renewal", "/procurement/products"))
def test_switch_organization_lands_on_procurement_home(app, world, create_org, set_flag, enabled, expected_path, current_path):
    set_flag(enabled)
    other_org = create_org("[TEST] Other Org")

    with app.test_request_context(f"{current_path}?{_q(world)}"):
        next_url = switch_organization_next_url(other_org)

    assert next_url == f"{expected_path}?organization_id={other_org.id}"


# ---------------------------------------------------------------------------
# MA list / upload page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("enabled", (False, True))
def test_ma_detail_never_shows_old_renew_button(world, client_for, set_flag, enabled):
    """ปุ่ม "ยื่นขอต่ออายุ" เดิม (สร้างคำขอซื้อ) ถูกถอดออกจากหน้ารายละเอียด MA ไม่ว่า flag จะเป็นอะไร (#32 / คำตัดสินรอบ 3)"""
    set_flag(enabled)

    html = client_for(world.users["admin"]).get(f"/procurement/payment/{world.procurement.id}?{_q(world)}").get_data(as_text=True)

    assert f"/procurement/requisitions/{world.procurement.id}/renewal-requested" not in html
    assert f"/procurement/products/{world.procurement.id}/renew?" in html
    assert f"/procurement/requisitions/{world.procurement.id}/non-renewal" in html


@pytest.mark.parametrize("enabled", (False, True))
def test_upload_page_mas_template_button_follows_flag(world, client_for, set_flag, enabled):
    set_flag(enabled)

    html = client_for(world.users["admin"]).get(f"/admin/upload_files/?{_q(world)}").get_data(as_text=True)

    assert ("Template แหล่งเงิน (MAS)" in html) is enabled
    assert ("/admin/upload_files/template/mas" in html) is enabled
    assert "/admin/upload_files/template/ma?" in html


@pytest.mark.parametrize("enabled", (False, True))
def test_upload_form_mas_category_follows_flag(world, client_for, set_flag, enabled):
    set_flag(enabled)

    html = client_for(world.users["admin"]).get(f"/admin/upload_files/create?{_q(world)}").get_data(as_text=True)

    assert ('value="mas"' in html) is enabled
    assert 'value="ma"' in html


def test_processing_mas_document_refused_when_flag_off(world, client_for, set_flag, mock_queue):
    document = models.Document(
        organization=world.org,
        category="mas",
        status="waiting",
        created_by=world.users["admin"],
        updated_by=world.users["admin"],
    )
    document.save()

    response = client_for(world.users["admin"]).get(f"/admin/upload_files/{document.id}/process?{_q(world)}")

    assert response.status_code == 302
    document.reload()
    assert document.status == "failed"
    assert document.error_messages == ["ปิดการนำเข้าไฟล์แหล่งเงิน (MAS) แล้ว"]
    assert mock_queue == []


# ---------------------------------------------------------------------------
# MA ถูกสร้างจากหน้ารายการ MA เท่านั้น
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("enabled", (False, True))
def test_products_create_ignores_requisition_prefill(world, client_for, set_flag, enabled):
    set_flag(enabled)

    response = client_for(world.users["admin"]).get(
        f"/procurement/products/create?{_q(world)}&name=PrefillFromTimeline&company=PrefillCompany"
        "&asset_codes=PREFILL-AC&product_numbers=PREFILL-SN"
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for value in ("PrefillFromTimeline", "PrefillCompany", "PREFILL-AC", "PREFILL-SN"):
        assert value not in html
