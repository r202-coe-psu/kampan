"""Follow-up fixes for the inventory / checkout approval flow.

- อัปโหลดไฟล์รายการเบิกต้องค้นวัสดุเฉพาะในหน่วยงานของใบเบิก
- เลขลำดับใบเบิก (ordinal_number) นับแยกตามหน่วยงาน
- อนุมัติ / ไม่อนุมัติต้องเป็น POST และกันการกดซ้ำ (ตัด stock ครั้งเดียว)
- หน้าเพิ่มรายการเบิกไม่ 500 เมื่อไม่มีวัสดุเหลือให้เลือก

Requests are made without an outer app_context so that flask-login's cached
``g._login_user`` never leaks from one logged-in user to the next.
"""

import io
import re
from types import SimpleNamespace

import pandas
import pytest
from flask_login import login_user

from kampan import models
from kampan.utils import item_checkouts as item_checkout_utils
from kampan.web import redis_rq
from kampan.web.views import approve_orders as approve_views

ALL_INVENTORY_ROLES = ["admin", "endorser", "head", "staff", "supervisor supplier"]
ALREADY_PROCESSED = "รายการนี้ดำเนินการไปแล้ว"


def _make_item(organization, user, name, remain=10):
    item = models.Item(
        name=name,
        barcode_id=f"{name}-BC",
        status="active",
        organization=organization,
    )
    item.save()
    inventory = models.Inventory(
        organization=organization,
        item=item,
        set_=remain,
        quantity=remain,
        remain=remain,
        status="active",
        created_by=user,
    )
    inventory.save()
    return item, inventory


def _make_order(organization, user, item=None, piece=2, status="pending on admin"):
    order = models.OrderItem(
        status=status,
        approval_status="pending",
        head_endorser=user,
        description=f"order {status}",
        created_by=user,
        organization=organization,
    )
    order.save()
    checkout = None
    if item:
        checkout = models.CheckoutItem(
            order=order,
            item=item,
            user=user,
            piece=piece,
            quantity=piece,
            organization=organization,
        )
        checkout.save()
    return order, checkout


def _make_tenant(organization, user, prefix):
    item, inventory = _make_item(organization, user, f"{prefix} item")
    order, checkout = _make_order(organization, user, item)
    return SimpleNamespace(
        item=item, inventory=inventory, order=order, checkout=checkout
    )


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org_a = create_org("Org A")
    org_b = create_org("Org B")
    user_a = create_user("UserA", "Alpha")
    user_b = create_user("UserB", "Beta")
    assign_user_to_org(user_a, org_a, roles=ALL_INVENTORY_ROLES)
    assign_user_to_org(user_b, org_b, roles=ALL_INVENTORY_ROLES)
    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        user_a=user_a,
        user_b=user_b,
        a=_make_tenant(org_a, user_a, "A"),
        b=_make_tenant(org_b, user_b, "B"),
    )


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        client = app.test_client()
        login_as(client, user)
        return client

    return _client_for


@pytest.fixture(autouse=True)
def no_enqueue(monkeypatch):
    """Replace the RQ enqueue used by views so no Redis is needed."""
    calls = []

    class _Job:
        def get_id(self):
            return "job"

    class _Queue:
        def enqueue(self, *args, **kwargs):
            calls.append((args, kwargs))
            return _Job()

    monkeypatch.setattr(redis_rq.redis_queue, "queue", _Queue(), raising=False)
    return calls


def _excel(rows):
    buffer = io.BytesIO()
    pandas.DataFrame(rows, columns=["ชื่อ", "จำนวน"]).to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def _remain(inventory):
    return models.Inventory.objects.get(id=inventory.id).remain


def _reload(document):
    return type(document).objects.get(id=document.id)


# ---------------------------------------------------------------------------
# 1. upload checkout file: item lookup scoped to the order's organization
# ---------------------------------------------------------------------------


def _process_upload(app, user, rows, organization, order):
    with app.test_request_context():
        login_user(user)
        return item_checkout_utils.process_items_upload_file(
            _excel(rows), organization, order
        )


def test_upload_item_name_only_in_other_org_is_row_error(app, world):
    """เดิมค้นวัสดุด้วยชื่ออย่างเดียว แล้วดึง CheckoutItem ของ org B มาใส่ใบเบิกของ A"""
    before_a = models.CheckoutItem.objects(order=world.a.order).count()

    errors = _process_upload(
        app, world.user_a, [["B item", 3]], world.org_a, world.a.order
    )

    assert errors and "B item" in errors[0]
    assert models.CheckoutItem.objects(order=world.a.order).count() == before_a
    checkout_b = _reload(world.b.checkout)
    assert checkout_b.order.id == world.b.order.id
    assert checkout_b.organization.id == world.org_b.id
    assert checkout_b.piece == 2


def test_upload_same_name_in_both_orgs_uses_own_org_item(app, world):
    # สร้างของ B ก่อน ให้ query ที่ไม่กรอง org เจอของ B ก่อน
    shared_b, _ = _make_item(world.org_b, world.user_b, "Shared")
    shared_a, _ = _make_item(world.org_a, world.user_a, "Shared")
    order_a, _ = _make_order(world.org_a, world.user_a, status="pending")

    errors = _process_upload(app, world.user_a, [["Shared", 4]], world.org_a, order_a)

    assert errors == []
    checkouts = list(models.CheckoutItem.objects(order=order_a))
    assert len(checkouts) == 1
    assert checkouts[0].item.id == shared_a.id
    assert checkouts[0].organization.id == world.org_a.id
    assert checkouts[0].piece == 4
    assert not models.CheckoutItem.objects(item=shared_b).count()


def test_upload_does_not_take_checkout_from_another_order(app, world):
    """เดิม CheckoutItem.objects(item=item).first() ดึงรายการเบิกของใบเบิกอื่นมาใส่"""
    new_order, _ = _make_order(world.org_a, world.user_a, status="pending")

    errors = _process_upload(app, world.user_a, [["A item", 1]], world.org_a, new_order)

    assert errors == []
    original = _reload(world.a.checkout)
    assert original.order.id == world.a.order.id
    assert original.piece == 2
    created = models.CheckoutItem.objects(order=new_order).get()
    assert created.id != world.a.checkout.id
    assert created.piece == 1


def test_upload_route_rejects_other_org_item_name(world, client_for):
    order_a, _ = _make_order(world.org_a, world.user_a, status="pending")
    client = client_for(world.user_a)

    response = client.post(
        f"/item_checkouts/order/{order_a.id}/upload_file_items"
        f"?organization_id={world.org_a.id}",
        data={"upload_file": (_excel([["B item", 3]]), "items.xlsx")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "B item" in response.data.decode("utf-8")
    assert models.CheckoutItem.objects(order=order_a).count() == 0
    assert _reload(world.b.checkout).order.id == world.b.order.id


def test_upload_route_adds_own_org_item(world, client_for):
    order_a, _ = _make_order(world.org_a, world.user_a, status="pending")
    client = client_for(world.user_a)

    response = client.post(
        f"/item_checkouts/order/{order_a.id}/upload_file_items"
        f"?organization_id={world.org_a.id}",
        data={"upload_file": (_excel([["A item", 3]]), "items.xlsx")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    created = models.CheckoutItem.objects(order=order_a).get()
    assert created.item.id == world.a.item.id
    assert created.piece == 3


# ---------------------------------------------------------------------------
# 2. ordinal number per organization
# ---------------------------------------------------------------------------


def _admin_approve(client, order, organization, **kwargs):
    return client.post(
        f"/approve_orders/{order.id}/admin_approve?organization_id={organization.id}",
        **kwargs,
    )


def test_ordinal_number_is_counted_per_organization(world, client_for):
    client_a = client_for(world.user_a)
    client_b = client_for(world.user_b)
    second_a, _ = _make_order(world.org_a, world.user_a, world.a.item, piece=1)

    _admin_approve(client_a, world.a.order, world.org_a)
    _admin_approve(client_b, world.b.order, world.org_b)
    _admin_approve(client_a, second_a, world.org_a)

    assert _reload(world.a.order).ordinal_number == "1"
    assert _reload(world.b.order).ordinal_number == "1"
    assert _reload(second_a).ordinal_number == "2"


def test_ordinal_number_continues_from_highest_in_organization(world, client_for):
    legacy, _ = _make_order(world.org_a, world.user_a, status="approved")
    legacy.update(set__ordinal_number="41")
    other_org, _ = _make_order(world.org_b, world.user_b, status="approved")
    other_org.update(set__ordinal_number="99")

    _admin_approve(client_for(world.user_a), world.a.order, world.org_a)

    assert _reload(world.a.order).ordinal_number == "42"


# ---------------------------------------------------------------------------
# 3. state changes are POST-only and claimed atomically
# ---------------------------------------------------------------------------


STATE_CHANGING_URLS = [
    "/approve_orders/{order}/endorser_approve",
    "/approve_orders/{order}/endorser_denied",
    "/approve_orders/{order}/supervisor_supplier_approve",
    "/approve_orders/{order}/supervisor_supplier_denied",
    "/approve_orders/{order}/admin_approve",
    "/approve_orders/{order}/admin_denied",
    "/approve_orders/{order}/change_quantity/organization/{org}",
]


@pytest.mark.parametrize("url", STATE_CHANGING_URLS)
def test_state_changing_get_is_not_allowed(world, client_for, url, no_enqueue):
    client = client_for(world.user_a)
    url = url.format(order=world.a.order.id, org=world.org_a.id)

    response = client.get(f"{url}?organization_id={world.org_a.id}&reason=x")

    assert response.status_code == 405
    order = _reload(world.a.order)
    assert order.status == "pending on admin"
    assert _remain(world.a.inventory) == 10
    assert no_enqueue == []


def test_admin_approve_twice_deducts_stock_once(world, client_for):
    client = client_for(world.user_a)

    first = _admin_approve(client, world.a.order, world.org_a)
    second = _admin_approve(client, world.a.order, world.org_a, follow_redirects=True)

    assert first.status_code == 302
    assert _reload(world.a.order).status == "approved"
    assert _remain(world.a.inventory) == 8
    assert ALREADY_PROCESSED in second.data.decode("utf-8")
    assert _reload(world.a.checkout).inventories == [world.a.inventory]


def test_admin_approve_with_stale_order_objects_claims_once(app, world):
    """จำลองกดพร้อมกัน: โหลดใบเบิกไว้ 2 ชุดก่อนอนุมัติทั้งคู่"""
    stale_1 = _reload(world.a.order)
    stale_2 = _reload(world.a.order)

    with app.app_context():
        first = approve_views.approve_order_by_admin(stale_1)
        second = approve_views.approve_order_by_admin(stale_2)

    assert first is None
    assert second == ALREADY_PROCESSED
    assert _remain(world.a.inventory) == 8


def test_admin_approve_page_twice_sends_email_once(world, client_for, no_enqueue):
    client = client_for(world.user_a)
    url = (
        f"/approve_orders/{world.a.order.id}/admin_approve_page"
        f"?organization_id={world.org_a.id}"
    )

    first = client.post(url, data={"sent_item_date": "2026-01-01T10:00"})
    second = client.post(
        url, data={"sent_item_date": "2026-02-02T10:00"}, follow_redirects=True
    )

    assert first.status_code == 302
    order = _reload(world.a.order)
    assert order.status == "approved"
    assert order.sent_item_date.strftime("%Y-%m-%d") == "2026-01-01"
    assert _remain(world.a.inventory) == 8
    assert len(no_enqueue) == 1
    assert ALREADY_PROCESSED in second.data.decode("utf-8")


def test_admin_approve_insufficient_stock_changes_nothing(world, client_for):
    world.a.checkout.update(set__piece=11, set__quantity=11)
    client = client_for(world.user_a)

    response = _admin_approve(client, world.a.order, world.org_a, follow_redirects=True)

    assert "จำนวนที่เลือกมากกว่าจำนวนวัสดุที่มี" in response.data.decode("utf-8")
    assert _reload(world.a.order).status == "pending on admin"
    assert _remain(world.a.inventory) == 10


def test_admin_approve_rolls_back_when_stock_disappears_midway(
    app, world, monkeypatch
):
    """ผ่านการเช็คยอดก่อน claim แล้ว แต่ stock ถูกตัดไปพร้อมกันก่อนตัดจริง"""
    second_item, second_inventory = _make_item(world.org_a, world.user_a, "A2", 1)
    models.CheckoutItem(
        order=world.a.order,
        item=second_item,
        user=world.user_a,
        piece=5,
        quantity=5,
        organization=world.org_a,
    ).save()
    monkeypatch.setattr(models.Item, "get_amount_pieces", lambda self: 1000)

    with app.app_context():
        error = approve_views.approve_order_by_admin(_reload(world.a.order))

    assert error == "จำนวนที่เลือกมากกว่าจำนวนวัสดุที่มี"
    order = _reload(world.a.order)
    assert order.status == "pending on admin"
    assert order.approval_status == "pending"
    assert _remain(world.a.inventory) == 10
    assert _remain(second_inventory) == 1


def test_deny_after_approve_is_refused(world, client_for):
    client = client_for(world.user_a)
    _admin_approve(client, world.a.order, world.org_a)

    response = client.post(
        f"/approve_orders/{world.a.order.id}/admin_denied"
        f"?organization_id={world.org_a.id}",
        data={"reason": "late"},
        follow_redirects=True,
    )

    assert ALREADY_PROCESSED in response.data.decode("utf-8")
    order = _reload(world.a.order)
    assert order.status == "approved"
    assert order.remark == ""
    assert _reload(world.a.checkout).status == "active"
    assert _remain(world.a.inventory) == 8


def test_admin_deny_sets_reason_and_denies_checkouts(world, client_for):
    client = client_for(world.user_a)

    response = client.post(
        f"/approve_orders/{world.a.order.id}/admin_denied"
        f"?organization_id={world.org_a.id}",
        data={"reason": "ของหมด"},
    )

    assert response.status_code == 302
    order = _reload(world.a.order)
    assert order.status == "admin denied"
    assert order.approval_status == "admin denied"
    assert order.remark == "ของหมด"
    assert _reload(world.a.checkout).status == "denied"


def test_endorser_approve_twice_moves_and_emails_once(world, client_for, no_enqueue):
    order, _ = _make_order(world.org_a, world.user_a, world.a.item, status="confirmed")
    client = client_for(world.user_a)
    url = (
        f"/approve_orders/{order.id}/endorser_approve"
        f"?organization_id={world.org_a.id}"
    )

    client.post(url)
    second = client.post(url, follow_redirects=True)

    assert _reload(order).status == "pending on supervisor supplier"
    assert len(no_enqueue) == 1
    assert ALREADY_PROCESSED in second.data.decode("utf-8")


def test_supervisor_approve_twice_moves_and_emails_once(world, client_for, no_enqueue):
    order, _ = _make_order(
        world.org_a, world.user_a, world.a.item, status="pending on supervisor supplier"
    )
    client = client_for(world.user_a)
    url = (
        f"/approve_orders/{order.id}/supervisor_supplier_approve"
        f"?organization_id={world.org_a.id}"
    )

    client.post(url, data={"reason": "ok"})
    second = client.post(url, data={"reason": "again"}, follow_redirects=True)

    order = _reload(order)
    assert order.status == "pending on admin"
    assert order.remark == "ok"
    assert len(no_enqueue) == 1
    assert ALREADY_PROCESSED in second.data.decode("utf-8")


def test_endorser_deny_after_endorser_approve_is_refused(world, client_for):
    order, checkout = _make_order(
        world.org_a, world.user_a, world.a.item, status="confirmed"
    )
    client = client_for(world.user_a)
    client.post(
        f"/approve_orders/{order.id}/endorser_approve?organization_id={world.org_a.id}"
    )

    client.post(
        f"/approve_orders/{order.id}/endorser_denied?organization_id={world.org_a.id}",
        data={"reason": "no"},
    )

    assert _reload(order).status == "pending on supervisor supplier"
    assert _reload(checkout).status == "active"


def test_change_quantity_post_updates_only_while_pending_on_supervisor(
    world, client_for
):
    order, checkout = _make_order(
        world.org_a, world.user_a, world.a.item, status="pending on supervisor supplier"
    )
    client = client_for(world.user_a)
    url = (
        f"/approve_orders/{order.id}/change_quantity/organization/{world.org_a.id}"
        f"?organization_id={world.org_a.id}"
    )

    client.post(url, data={str(checkout.id): "5"})
    assert _reload(checkout).piece == 5

    order.update(set__status="pending on admin")
    client.post(url, data={str(checkout.id): "1"})
    assert _reload(checkout).piece == 5


# ---------------------------------------------------------------------------
# 4. checkout page with no selectable items
# ---------------------------------------------------------------------------


def test_checkout_page_with_no_items_left_renders(world, client_for):
    """วัสดุทุกชิ้นของ org A อยู่ในใบเบิกนี้แล้ว dropdown จึงว่าง (เดิม 500)"""
    world.a.order.update(set__status="pending")
    client = client_for(world.user_a)

    response = client.get(
        f"/item_checkouts/checkout?order_id={world.a.order.id}"
        f"&organization_id={world.org_a.id}"
    )

    assert response.status_code == 200
    assert "ไม่มีวัสดุให้เลือกเบิก" in response.data.decode("utf-8")


def test_checkout_post_with_no_items_left_does_not_save(world, client_for):
    world.a.order.update(set__status="pending")
    client = client_for(world.user_a)
    before = models.CheckoutItem.objects.count()

    response = client.post(
        f"/item_checkouts/checkout?order_id={world.a.order.id}"
        f"&organization_id={world.org_a.id}",
        data={
            "item": str(world.a.item.id),
            "piece": "1",
            "created_date": "2026-01-01T10:00",
        },
    )

    assert response.status_code == 200
    assert models.CheckoutItem.objects.count() == before


@pytest.mark.parametrize(
    "status,detail,action",
    [
        ("confirmed", "endorser_approved_detail", "endorser_approve"),
        ("confirmed", "endorser_approved_detail", "endorser_denied"),
        (
            "pending on supervisor supplier",
            "supervisor_supplier_approved_detail",
            "supervisor_supplier_approve",
        ),
        (
            "pending on supervisor supplier",
            "supervisor_supplier_approved_detail",
            "supervisor_supplier_denied",
        ),
        (
            "pending on supervisor supplier",
            "supervisor_supplier_approved_detail",
            "change_quantity",
        ),
        ("pending on admin", "admin_approved_detail", "admin_denied"),
    ],
)
def test_detail_page_posts_state_changes(world, client_for, status, detail, action):
    world.a.order.update(set__status=status)
    client = client_for(world.user_a)

    response = client.get(
        f"/approve_orders/{world.a.order.id}/{detail}?organization_id={world.org_a.id}"
    )

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    action_url = f"/approve_orders/{world.a.order.id}/{action}"
    match = re.search(rf'action="{re.escape(action_url)}[?/]', html)
    assert match
    form_tag = html[: match.start()].rsplit("<form", 1)[1]
    assert 'method="POST"' in form_tag
    assert not re.search(rf'href="{re.escape(action_url)}[?/]', html)


# ---------------------------------------------------------------------------
# 4. issue #50: lost_breaks / inventories / item_checkouts state changes
# ---------------------------------------------------------------------------


def _make_lost_break(world, tenant="a", quantity=3, status="pending"):
    org = world.org_a if tenant == "a" else world.org_b
    user = world.user_a if tenant == "a" else world.user_b
    t = world.a if tenant == "a" else world.b
    return models.LostBreakItem(
        organization=org,
        user=user,
        item=t.item,
        lost_from=t.inventory,
        quantity=quantity,
        status=status,
    ).save()


def _decide(client, lost_break, org, choice):
    return client.post(
        f"/lost_breaks/{lost_break.id}/decide/{choice}?organization_id={org.id}"
    )


def test_lost_break_decide_get_is_not_allowed(world, client_for):
    lost = _make_lost_break(world)

    response = client_for(world.user_a).get(
        f"/lost_breaks/{lost.id}/decide/approve?organization_id={world.org_a.id}"
    )

    assert response.status_code == 405
    assert _reload(lost).status == "pending"
    assert _remain(world.a.inventory) == 10


def test_lost_break_approve_twice_changes_stock_once(world, client_for):
    lost = _make_lost_break(world, quantity=3)
    client = client_for(world.user_a)

    _decide(client, lost, world.org_a, "approve")
    _decide(client, lost, world.org_a, "approve")

    assert _reload(lost).status == "active"
    assert _remain(world.a.inventory) == 13


def test_lost_break_denied_after_approve_does_not_touch_stock(world, client_for):
    lost = _make_lost_break(world, quantity=3)
    client = client_for(world.user_a)

    _decide(client, lost, world.org_a, "approve")
    _decide(client, lost, world.org_a, "denied")

    assert _reload(lost).status == "active"
    assert _remain(world.a.inventory) == 13


def test_lost_break_decide_invalid_choice_is_404(world, client_for):
    lost = _make_lost_break(world)

    response = _decide(client_for(world.user_a), lost, world.org_a, "whatever")

    assert response.status_code == 404
    assert _reload(lost).status == "pending"


def test_lost_break_decide_other_org_is_404(world, client_for):
    lost_b = _make_lost_break(world, tenant="b")

    response = _decide(client_for(world.user_a), lost_b, world.org_a, "approve")

    assert response.status_code == 404
    assert _reload(lost_b).status == "pending"
    assert _remain(world.b.inventory) == 10


def test_lost_break_delete_get_not_allowed_and_post_scoped(world, client_for):
    lost = _make_lost_break(world)
    lost_b = _make_lost_break(world, tenant="b")
    client = client_for(world.user_a)

    get_response = client.get(
        f"/lost_breaks/{lost.id}/delete?organization_id={world.org_a.id}"
    )
    other_org = client.post(
        f"/lost_breaks/{lost_b.id}/delete?organization_id={world.org_a.id}"
    )
    own = client.post(f"/lost_breaks/{lost.id}/delete?organization_id={world.org_a.id}")

    assert get_response.status_code == 405
    assert other_org.status_code == 404
    assert _reload(lost_b).status == "pending"
    assert own.status_code == 302
    assert _reload(lost).status == "disactive"


def test_lost_break_delete_rejects_approved(world, client_for):
    lost = _make_lost_break(world, status="active")

    client_for(world.user_a).post(
        f"/lost_breaks/{lost.id}/delete?organization_id={world.org_a.id}"
    )

    assert _reload(lost).status == "active"


def test_lost_break_add_without_inventory_flashes_instead_of_500(world, client_for):
    world.a.inventory.update(set__remain=0)

    response = client_for(world.user_a).post(
        f"/lost_breaks/add?organization_id={world.org_a.id}",
        data={
            "item": str(world.a.item.id),
            "set_": 0,
            "piece": 1,
            "description": "x",
        },
    )

    assert response.status_code == 302
    assert models.LostBreakItem.objects.count() == 0


def test_inventory_delete_get_not_allowed(world, client_for):
    response = client_for(world.user_a).get(
        f"/inventories/{world.a.inventory.id}/delete?organization_id={world.org_a.id}"
    )

    assert response.status_code == 405


def _inventory_with_bill(world):
    register = models.RegistrationItem(organization=world.org_a, receipt_id="R1").save()
    world.a.inventory.update(set__registration=register)
    return register


def test_inventory_delete_other_org_is_404(world, client_for):
    _inventory_with_bill(world)

    response = client_for(world.user_a).post(
        f"/inventories/{world.b.inventory.id}/delete?organization_id={world.org_a.id}"
    )

    assert response.status_code == 404
    assert _reload(world.b.inventory).status == "active"


def test_inventory_delete_refused_when_stock_already_used(world, client_for):
    _inventory_with_bill(world)
    world.a.inventory.update(set__remain=7)

    client_for(world.user_a).post(
        f"/inventories/{world.a.inventory.id}/delete?organization_id={world.org_a.id}"
    )

    assert _reload(world.a.inventory).status == "active"


def test_inventory_delete_refused_when_checkout_references_it(world, client_for):
    _inventory_with_bill(world)
    world.a.checkout.update(push__inventories=world.a.inventory)

    client_for(world.user_a).post(
        f"/inventories/{world.a.inventory.id}/delete?organization_id={world.org_a.id}"
    )

    assert _reload(world.a.inventory).status == "active"


def test_inventory_delete_unused_succeeds(world, client_for):
    _inventory_with_bill(world)

    response = client_for(world.user_a).post(
        f"/inventories/{world.a.inventory.id}/delete?organization_id={world.org_a.id}"
    )

    assert response.status_code == 302
    assert _reload(world.a.inventory).status == "disactive"


def _pending_order_checkout(world):
    order, checkout = _make_order(
        world.org_a, world.user_a, world.a.item, status="pending"
    )
    return order, checkout


def test_checkout_delete_get_not_allowed(world, client_for):
    order, checkout = _pending_order_checkout(world)

    response = client_for(world.user_a).get(
        f"/item_checkouts/checkout/{checkout.id}/delete?organization_id={world.org_a.id}"
    )

    assert response.status_code == 405
    assert _reload(checkout).status != "disactive"


def test_checkout_delete_pending_order_and_other_org(world, client_for):
    order, checkout = _pending_order_checkout(world)
    client = client_for(world.user_a)

    other = client.post(
        f"/item_checkouts/checkout/{world.b.checkout.id}/delete"
        f"?organization_id={world.org_a.id}"
    )
    own = client.post(
        f"/item_checkouts/checkout/{checkout.id}/delete"
        f"?organization_id={world.org_a.id}"
    )

    assert other.status_code == 404
    assert _reload(world.b.checkout).status != "disactive"
    assert own.status_code == 302
    assert _reload(checkout).status == "disactive"


@pytest.mark.parametrize("status", ["confirmed", "approved", "pending on admin"])
def test_checkout_delete_rejected_when_order_not_pending(world, client_for, status):
    order, checkout = _make_order(world.org_a, world.user_a, world.a.item, status=status)

    client_for(world.user_a).post(
        f"/item_checkouts/checkout/{checkout.id}/delete"
        f"?organization_id={world.org_a.id}"
    )

    assert _reload(checkout).status != "disactive"


@pytest.mark.parametrize("status", ["confirmed", "approved", "pending on admin"])
def test_checkout_edit_and_add_rejected_when_order_not_pending(
    world, client_for, status
):
    order, checkout = _make_order(world.org_a, world.user_a, world.a.item, status=status)
    client = client_for(world.user_a)

    edit = client.post(
        f"/item_checkouts/checkout/{checkout.id}/edit"
        f"?organization_id={world.org_a.id}",
        data={"item": str(world.a.item.id), "piece": 9},
    )
    add = client.post(
        f"/item_checkouts/checkout?organization_id={world.org_a.id}"
        f"&order_id={order.id}",
        data={"item": str(world.a.item.id), "piece": 1},
    )

    assert edit.status_code == 302 and add.status_code == 302
    assert _reload(checkout).piece == 2
    assert models.CheckoutItem.objects(order=order).count() == 1


def test_checkout_uses_session_organization_not_query(world, client_for):
    order, _ = _make_order(world.org_a, world.user_a, status="pending")

    client_for(world.user_a).post(
        f"/item_checkouts/checkout?organization_id={world.org_a.id}"
        f"&order_id={order.id}",
        data={"item": str(world.a.item.id), "piece": 1},
    )

    created = models.CheckoutItem.objects(order=order).get()
    assert created.organization.id == world.org_a.id


def test_ordinal_number_counter_is_atomic_and_unique(world):
    numbers = [
        approve_views.get_next_ordinal_number(world.org_a) for _ in range(5)
    ]

    assert numbers == ["1", "2", "3", "4", "5"]
    assert approve_views.get_next_ordinal_number(world.org_b) == "1"
