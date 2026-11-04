"""Cross-tenant (IDOR) tests for the inventory / checkout system (issue #41).

User A is a member of org A only and sends org A's ``organization_id`` together
with the id of an org B document. Every handler must answer 404 and leave org B
untouched.

Requests are made without an outer app_context so that flask-login's cached
``g._login_user`` never leaks from one logged-in user to the next.
"""

import io
from types import SimpleNamespace

import mongoengine as me
import pytest

from kampan import models
from kampan.web import redis_rq

LOGIN_PATH = "/login"
ALL_INVENTORY_ROLES = ["admin", "endorser", "head", "staff", "supervisor supplier"]


def _is_login_redirect(response):
    return response.status_code == 302 and LOGIN_PATH in response.headers["Location"]


def _make_tenant_data(organization, user, prefix):
    category = models.Category(name=f"{prefix} category", organization=organization)
    category.save()
    warehouse = models.Warehouse(name=f"{prefix} warehouse", organization=organization)
    warehouse.save()
    item_position = models.ItemPosition(
        description=f"{prefix} position",
        rack="R1",
        organization=organization,
        warehouse=warehouse,
    )
    item_position.save()
    supplier = models.Supplier(
        company_name=f"{prefix} supplier",
        person_name=f"{prefix} supplier",
        address="addr",
        organization=organization,
    )
    supplier.save()
    item = models.Item(
        name=f"{prefix} item",
        barcode_id=f"{prefix}-BC",
        status="active",
        organization=organization,
        categories=category,
    )
    item.save()
    registration = models.RegistrationItem(
        receipt_id=f"{prefix}-RC",
        status="pending",
        supplier=supplier,
        organization=organization,
        created_by=user,
    )
    registration.save()
    inventory = models.Inventory(
        registration=registration,
        warehouse=warehouse,
        organization=organization,
        item=item,
        set_=10,
        quantity=10,
        remain=10,
        status="active",
        created_by=user,
    )
    inventory.save()
    order = models.OrderItem(
        status="pending on admin",
        approval_status="pending",
        head_endorser=user,
        description=f"{prefix} order",
        created_by=user,
        organization=organization,
    )
    order.save()
    checkout = models.CheckoutItem(
        order=order,
        item=item,
        user=user,
        piece=2,
        quantity=2,
        organization=organization,
    )
    checkout.save()
    lost_break = models.LostBreakItem(
        status="pending",
        organization=organization,
        user=user,
        item=item,
        lost_from=inventory,
        warehouse=warehouse,
        quantity=1,
    )
    lost_break.save()
    return SimpleNamespace(
        category=category,
        warehouse=warehouse,
        item_position=item_position,
        supplier=supplier,
        item=item,
        registration=registration,
        inventory=inventory,
        order=order,
        checkout=checkout,
        lost_break=lost_break,
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
        a=_make_tenant_data(org_a, user_a, "A"),
        b=_make_tenant_data(org_b, user_b, "B"),
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


@pytest.fixture
def gridfs_enabled():
    import mongomock.gridfs

    mongomock.gridfs.enable_gridfs_integration()


def _put_image(item):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    buffer.seek(0)
    item.image.put(buffer, filename="pic.png", content_type="image/png")
    item.save()


def _db_snapshot():
    db = me.connection.get_db()
    return {
        name: sorted((repr(doc) for doc in db[name].find()))
        for name in db.list_collection_names()
        if not name.startswith("system.")
    }


# (method, url template, form data) — ``{b.<attr>}`` is an org B document,
# ``{org_a}`` is the organization the attacker legitimately belongs to.
FOREIGN_ID_REQUESTS = [
    # approve_orders.py
    ("GET", "/approve_orders/item_checkouts?order_id={b.order.id}", None),
    ("GET", "/approve_orders/{b.order.id}/endorser_approve", None),
    ("GET", "/approve_orders/{b.order.id}/endorser_denied", None),
    ("GET", "/approve_orders/{b.order.id}/endorser_approved_detail", None),
    ("GET", "/approve_orders/{b.order.id}/supervisor_supplier_approve", None),
    ("GET", "/approve_orders/{b.order.id}/supervisor_supplier_denied", None),
    ("GET", "/approve_orders/{b.order.id}/supervisor_supplier_approved_detail", None),
    ("GET", "/approve_orders/{b.order.id}/supervisor_supplier_approve_page", None),
    ("POST", "/approve_orders/{b.order.id}/supervisor_supplier_approve_page", {}),
    ("GET", "/approve_orders/{b.order.id}/admin_approve", None),
    ("GET", "/approve_orders/{b.order.id}/admin_denied", None),
    ("GET", "/approve_orders/{b.order.id}/admin_approved_detail", None),
    ("GET", "/approve_orders/{b.order.id}/admin_approve_page", None),
    (
        "POST",
        "/approve_orders/{b.order.id}/admin_approve_page",
        {"sent_item_date": "2026-01-01 10:00:00"},
    ),
    (
        "GET",
        "/approve_orders/{b.order.id}/change_quantity/organization/{org_a}?{b.checkout.id}=0",
        None,
    ),
    # item_checkouts.py
    ("GET", "/item_checkouts/order/{b.order.id}/catalogs", None),
    ("GET", "/item_checkouts/checkout?order_id={b.order.id}", None),
    (
        "POST",
        "/item_checkouts/checkout?order_id={b.order.id}",
        {"item": "{a.item.id}", "piece": "1", "created_date": "2026-01-01T10:00"},
    ),
    ("GET", "/item_checkouts/all-checkout?order_id={b.order.id}", None),
    ("GET", "/item_checkouts/checkout/{b.checkout.id}/edit", None),
    (
        "POST",
        "/item_checkouts/checkout/{b.checkout.id}/edit",
        {"item": "{b.item.id}", "piece": "5", "created_date": "2026-01-01T10:00"},
    ),
    ("GET", "/item_checkouts/checkout/{b.checkout.id}/delete", None),
    ("GET", "/item_checkouts/order/{b.order.id}/upload_file_items", None),
    # item_orders.py
    ("GET", "/item_orders/{b.order.id}/edit", None),
    (
        "POST",
        "/item_orders/{b.order.id}/edit",
        {"head_endorser": "{user_a}", "description": "hijacked"},
    ),
    ("GET", "/item_orders/{b.order.id}/delete", None),
    # email_templates.py
    ("GET", "/email_templates/order/{b.order.id}/send_email", None),
    # inventories.py
    ("GET", "/inventories/register?item_register_id={b.registration.id}", None),
    (
        "POST",
        "/inventories/register?item_register_id={b.registration.id}",
        {"item": "{a.item.id}", "warehouse": "{a.warehouse.id}", "set_": "1", "price": "1"},
    ),
    ("GET", "/inventories/{b.inventory.id}/edit", None),
    (
        "POST",
        "/inventories/{b.inventory.id}/edit",
        {"item": "{b.item.id}", "warehouse": "{b.warehouse.id}", "set_": "99", "price": "1"},
    ),
    ("GET", "/inventories/{b.inventory.id}/delete", None),
    ("GET", "/inventories/all-item?item_register_id={b.registration.id}", None),
    ("GET", "/inventories/item_register/{b.registration.id}/upload_file", None),
    # item_registers.py
    ("GET", "/item_registers/{b.registration.id}/edit", None),
    (
        "POST",
        "/item_registers/{b.registration.id}/edit",
        {"receipt_id": "hijacked", "supplier": "{b.supplier.id}"},
    ),
    ("GET", "/item_registers/{b.registration.id}/confirm_item_register", None),
    ("GET", "/item_registers/{b.registration.id}/delete_item_registers", None),
    # items.py
    ("GET", "/items/{b.item.id}/edit", None),
    (
        "POST",
        "/items/{b.item.id}/edit",
        {
            "name": "hijacked",
            "categories": "{b.category.id}",
            "item_format": "one to many",
            "set_": "1",
            "set_unit": "box",
            "piece_per_set": "1",
            "piece_unit": "piece",
            "minimum": "0",
        },
    ),
    ("GET", "/items/{b.item.id}/edit_active_item", None),
    ("GET", "/items/{b.item.id}/delete", None),
    ("GET", "/items/{b.item.id}/confirm", None),
    ("GET", "/items/{b.item.id}/detail", None),
    # lost_breaks.py
    ("GET", "/lost_breaks/{b.lost_break.id}/edit", None),
    (
        "POST",
        "/lost_breaks/{b.lost_break.id}/edit",
        {"item": "{b.item.id}", "set_": "0", "piece": "1", "description": "x"},
    ),
    ("GET", "/lost_breaks/{b.lost_break.id}/delete", None),
    ("GET", "/lost_breaks/{b.lost_break.id}/decide/approve", None),
    ("GET", "/lost_breaks/{b.lost_break.id}/decide/denied", None),
    # notifications.py
    ("GET", "/notifications/{b.item.id}/set_status", None),
    # warehouses.py
    ("GET", "/warehouses/{b.warehouse.id}/edit", None),
    ("POST", "/warehouses/{b.warehouse.id}/edit", {"name": "hijacked"}),
    ("GET", "/warehouses/{b.warehouse.id}/delete", None),
    # item_positions.py
    ("GET", "/item-positions/{b.item_position.id}/edit", None),
    (
        "POST",
        "/item-positions/{b.item_position.id}/edit",
        {"description": "hijacked", "rack": "R9", "warehouse": "{b.warehouse.id}"},
    ),
    ("GET", "/item-positions/{b.item_position.id}/delete", None),
    # categories.py
    ("GET", "/categories/{b.category.id}/edit", None),
    ("POST", "/categories/{b.category.id}/edit", {"name": "hijacked"}),
    ("GET", "/categories/{b.category.id}/delete", None),
]


def _fill(template, world):
    return template.format(
        a=world.a, b=world.b, org_a=world.org_a.id, user_a=world.user_a.id
    )


def _with_org(url, organization):
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}organization_id={organization.id}"


@pytest.mark.parametrize(
    "method,url,data",
    FOREIGN_ID_REQUESTS,
    ids=[f"{m} {u.split('?')[0]}" for m, u, _ in FOREIGN_ID_REQUESTS],
)
def test_foreign_org_object_returns_404_and_is_unchanged(world, client_for, no_enqueue, method, url, data):
    client = client_for(world.user_a)
    url = _with_org(_fill(url, world), world.org_a)
    form = {key: _fill(value, world) for key, value in (data or {}).items()}
    before = _db_snapshot()

    if method == "GET":
        response = client.get(url)
    else:
        response = client.post(url, data=form)

    assert response.status_code == 404
    assert _db_snapshot() == before
    assert no_enqueue == []


def test_foreign_org_item_image_returns_404(world, client_for, gridfs_enabled):
    _put_image(world.b.item)
    client = client_for(world.user_a)

    response = client.get(f"/items/{world.b.item.id}/picture/pic.png?organization_id={world.org_a.id}")

    assert response.status_code == 404


def test_foreign_org_inventory_bill_returns_404(world, client_for, gridfs_enabled):
    world.b.registration.bill.put(io.BytesIO(b"%PDF-1.4"), filename="bill.pdf", content_type="application/pdf")
    world.b.registration.save()
    client = client_for(world.user_a)

    response = client.get(f"/inventories/{world.b.inventory.id}/file?organization_id={world.org_a.id}")

    assert response.status_code == 404


def test_own_org_inventory_bill_ok(world, client_for, gridfs_enabled):
    world.a.registration.bill.put(io.BytesIO(b"%PDF-1.4"), filename="bill.pdf", content_type="application/pdf")
    world.a.registration.save()
    client = client_for(world.user_a)

    response = client.get(f"/inventories/{world.a.inventory.id}/file?organization_id={world.org_a.id}")

    assert response.status_code == 200
    assert response.data == b"%PDF-1.4"


def test_item_image_requires_login(world, app, gridfs_enabled):
    _put_image(world.a.item)
    client = app.test_client()

    response = client.get(f"/items/{world.a.item.id}/picture/pic.png?organization_id={world.org_a.id}")

    assert _is_login_redirect(response)


def test_item_image_own_org_ok(world, client_for, gridfs_enabled):
    _put_image(world.a.item)
    client = client_for(world.user_a)

    response = client.get(f"/items/{world.a.item.id}/picture/pic.png?organization_id={world.org_a.id}")

    assert response.status_code == 200
    assert response.mimetype == "image/png"


@pytest.mark.parametrize(
    "url",
    [
        "/approve_orders/not-an-id/admin_approve",
        "/approve_orders/item_checkouts?order_id=not-an-id",
        "/item_checkouts/checkout?order_id=not-an-id",
        "/item_checkouts/checkout/not-an-id/edit",
        "/item_orders/not-an-id/edit",
        "/email_templates/order/not-an-id/send_email",
        "/inventories/not-an-id/edit",
        "/inventories/all-item?item_register_id=not-an-id",
        "/item_registers/not-an-id/edit",
        "/items/not-an-id/edit",
        "/items/not-an-id/picture/pic.png",
        "/lost_breaks/not-an-id/decide/approve",
        "/notifications/not-an-id/set_status",
        "/warehouses/not-an-id/edit",
        "/item-positions/not-an-id/edit",
        "/categories/not-an-id/edit",
    ],
)
def test_invalid_object_id_returns_404(world, client_for, url):
    client = client_for(world.user_a)

    response = client.get(_with_org(url, world.org_a))

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# editing keeps the document in its own organization
# ---------------------------------------------------------------------------


def test_edit_own_item_keeps_organization(world, client_for):
    client = client_for(world.user_a)

    response = client.post(
        f"/items/{world.a.item.id}/edit?organization_id={world.org_a.id}",
        data={
            "name": "renamed",
            "categories": str(world.a.category.id),
            "item_format": "one to many",
            "set_": "1",
            "set_unit": "box",
            "piece_per_set": "1",
            "piece_unit": "piece",
            "minimum": "0",
        },
    )

    assert response.status_code == 302
    item = models.Item.objects.get(id=world.a.item.id)
    assert item.name == "renamed"
    assert item.organization.id == world.org_a.id


def test_member_of_two_orgs_cannot_move_item_by_switching_organization_id(world, client_for, assign_user_to_org):
    """เดิม handler แก้ไขตั้ง item.organization ตาม organization_id ที่ส่งมา ทำให้ย้ายของข้าม org ได้"""
    assign_user_to_org(world.user_a, world.org_b, roles=["admin"])
    client = client_for(world.user_a)

    response = client.post(
        f"/items/{world.a.item.id}/edit?organization_id={world.org_b.id}",
        data={
            "name": "moved",
            "categories": str(world.b.category.id),
            "item_format": "one to many",
            "set_": "1",
            "set_unit": "box",
            "piece_per_set": "1",
            "piece_unit": "piece",
            "minimum": "0",
        },
    )

    assert response.status_code == 404
    item = models.Item.objects.get(id=world.a.item.id)
    assert item.name == "A item"
    assert item.organization.id == world.org_a.id


@pytest.mark.parametrize(
    "url_template,data_template,model,attr",
    [
        (
            "/warehouses/{a.warehouse.id}/edit",
            {"name": "renamed"},
            models.Warehouse,
            "warehouse",
        ),
        (
            "/item_registers/{a.registration.id}/edit",
            {"receipt_id": "renamed", "supplier": "{a.supplier.id}"},
            models.RegistrationItem,
            "registration",
        ),
        (
            "/item_orders/{a.order.id}/edit",
            {"head_endorser": "{user_a}", "description": "renamed"},
            models.OrderItem,
            "order",
        ),
    ],
)
def test_edit_ignores_organization_posted_in_form(world, client_for, url_template, data_template, model, attr):
    """organization ต้องไม่มาจาก input ของ form แม้จะแก้ไขเอกสารของ org ตัวเอง"""
    client = client_for(world.user_a)
    data = {key: _fill(value, world) for key, value in data_template.items()}
    data["organization"] = str(world.org_b.id)

    response = client.post(_with_org(_fill(url_template, world), world.org_a), data=data)

    assert response.status_code in (200, 302)
    document = model.objects.get(id=getattr(world.a, attr).id)
    assert document.organization.id == world.org_a.id


# ---------------------------------------------------------------------------
# objects referenced through a form must belong to the viewing organization
# ---------------------------------------------------------------------------


def test_checkout_rejects_item_of_other_org(world, client_for):
    # ให้ใบเบิกของ A ยังเลือกวัสดุของ A ได้ dropdown จะได้ไม่ว่าง
    world.a.checkout.update(set__status="disactive")
    client = client_for(world.user_a)
    before = models.CheckoutItem.objects.count()

    response = client.post(
        f"/item_checkouts/checkout?order_id={world.a.order.id}&organization_id={world.org_a.id}",
        data={"item": str(world.b.item.id), "piece": "1", "created_date": "2026-01-01T10:00"},
    )

    assert response.status_code == 200
    assert models.CheckoutItem.objects.count() == before


def test_inventory_register_rejects_item_and_warehouse_of_other_org(world, client_for):
    client = client_for(world.user_a)
    before = models.Inventory.objects.count()

    response = client.post(
        f"/inventories/register?item_register_id={world.a.registration.id}&organization_id={world.org_a.id}",
        data={
            "item": str(world.b.item.id),
            "warehouse": str(world.b.warehouse.id),
            "set_": "1",
            "price": "1",
        },
    )

    assert response.status_code == 200
    assert models.Inventory.objects.count() == before


def test_item_register_rejects_supplier_of_other_org(world, client_for):
    client = client_for(world.user_a)
    before = models.RegistrationItem.objects.count()

    response = client.post(
        f"/item_registers/register?organization_id={world.org_a.id}",
        data={"receipt_id": "NEW", "supplier": str(world.b.supplier.id)},
    )

    assert response.status_code == 200
    assert models.RegistrationItem.objects.count() == before


def test_lost_break_add_rejects_item_of_other_org(world, client_for):
    client = client_for(world.user_a)
    before = models.LostBreakItem.objects.count()
    remain_before = models.Inventory.objects.get(id=world.b.inventory.id).remain

    response = client.post(
        f"/lost_breaks/add?organization_id={world.org_a.id}",
        data={"item": str(world.b.item.id), "set_": "0", "piece": "1", "description": "x"},
    )

    assert response.status_code == 200
    assert models.LostBreakItem.objects.count() == before
    assert models.Inventory.objects.get(id=world.b.inventory.id).remain == remain_before


def test_item_edit_ignores_category_of_other_org(world, client_for):
    client = client_for(world.user_a)

    response = client.post(
        f"/items/{world.a.item.id}/edit?organization_id={world.org_a.id}",
        data={
            "name": "renamed",
            "categories": str(world.b.category.id),
            "item_format": "one to many",
            "set_": "1",
            "set_unit": "box",
            "piece_per_set": "1",
            "piece_unit": "piece",
            "minimum": "0",
        },
    )

    assert response.status_code == 200
    item = models.Item.objects.get(id=world.a.item.id)
    assert item.categories.id == world.a.category.id


# ---------------------------------------------------------------------------
# dropdowns and lists show only the viewing organization's documents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url_template,own_attr,foreign_attr",
    [
        ("/item_registers/register", "a.supplier", "b.supplier"),
        ("/item_registers/{a.registration.id}/edit", "a.supplier", "b.supplier"),
        ("/lost_breaks/add", "a.item", "b.item"),
        ("/lost_breaks/{a.lost_break.id}/edit", "a.item", "b.item"),
        ("/item_checkouts/", "a.item", "b.item"),
        ("/item_checkouts/checkout?order_id={a.order.id}", "a.item", "b.item"),
        ("/item_checkouts/checkout/{a.checkout.id}/edit", "a.item", "b.item"),
        ("/inventories/", "a.item", "b.item"),
        ("/inventories/{a.inventory.id}/edit", "a.item", "b.item"),
    ],
)
def test_dropdown_lists_only_own_org(world, client_for, url_template, own_attr, foreign_attr):
    client = client_for(world.user_a)

    def _resolve(path):
        group, name = path.split(".")
        return getattr(getattr(world, group), name)

    # ทำให้ checkout ของ A ไม่ล็อกรายการวัสดุของ A ออกจาก dropdown หน้า checkout
    if url_template.startswith("/item_checkouts/checkout?"):
        world.a.checkout.update(set__status="disactive")

    response = client.get(_with_org(_fill(url_template, world), world.org_a))

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert str(_resolve(own_attr).id) in html
    assert str(_resolve(foreign_attr).id) not in html


@pytest.mark.parametrize("url", ["/lost_breaks/", "/lost_breaks/approve_page"])
def test_lost_break_lists_only_own_org(world, client_for, url):
    client = client_for(world.user_a)

    response = client.get(_with_org(url, world.org_a))

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert str(world.a.lost_break.id) in html
    assert str(world.b.lost_break.id) not in html


# ---------------------------------------------------------------------------
# own organization still works
# ---------------------------------------------------------------------------


def test_admin_approve_own_order_deducts_stock(world, client_for):
    client = client_for(world.user_a)

    response = client.get(f"/approve_orders/{world.a.order.id}/admin_approve?organization_id={world.org_a.id}")

    assert response.status_code == 302
    order = models.OrderItem.objects.get(id=world.a.order.id)
    assert order.status == "approved"
    assert models.Inventory.objects.get(id=world.a.inventory.id).remain == 8
    assert models.Inventory.objects.get(id=world.b.inventory.id).remain == 10
