"""Cross-tenant (IDOR) tests for the procurement module (issue #42).

Requests are made without an outer app_context so that flask-login's cached
``g._login_user`` never leaks from one logged-in user to the next.
"""

import datetime
import io
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from kampan import models
from kampan.utils import export_file as export_utils
from kampan.web import redis_rq

LOGIN_PATH = "/login"


def _is_login_redirect(response):
    return response.status_code == 302 and LOGIN_PATH in response.headers["Location"]


def _make_procurement(organization, user, name="MA contract", status="pending", responsible=None):
    """MA 1 หัว + 1 รายการย่อย (ยอดตรงกัน) ผู้รับผิดชอบอยู่ที่รายการย่อย"""
    now = datetime.datetime.now()
    procurement = models.Procurement(
        psu_disbursement_number="PSU-1",
        name=name,
        company="Vendor Co.",
        organization=organization,
        status=status,
        total_amount=Decimal("1000.00"),
        created_by=user,
        last_updated_by=user,
    )
    procurement.save_with_items(
        [
            models.ProcurementItem(
                name=name,
                category="product",
                amount=Decimal("1000.00"),
                start_date=now,
                end_date=now + datetime.timedelta(days=30),
                responsible_by=responsible or [],
                installments=[models.Installment(due_date=now + datetime.timedelta(days=30))],
            )
        ]
    )
    return procurement


def _make_requisition(organization, purchaser, user, code):
    requisition = models.Requisition(
        requisition_code=code,
        organization=organization,
        purchaser=purchaser,
        start_date=datetime.datetime.now(),
        items=[
            models.RequisitionItem(
                product_name="Laptop",
                category="product",
                amount=Decimal("100.00"),
                quantity=1,
            )
        ],
        fund=[],
        created_by=user,
        last_updated_by=user,
    )
    requisition.save()
    return requisition


def _make_timeline(organization, requisition, purchaser, user, status="active", completed=False):
    timeline = models.RequisitionTimeline(
        organization=organization,
        requisition=requisition,
        purchaser=purchaser,
        status=status,
        created_by=user,
        progress=[models.requisition_timeline.Progress(progress_status="completed", created_by=user)]
        if completed
        else [models.requisition_timeline.Progress(progress_status="request_created", created_by=user)],
    )
    timeline.save()
    return timeline


def _make_timeline_item(organization, timeline, requisition, code):
    item = models.RequisitionTimelineItem(
        organization=organization,
        running_number=1,
        requisition_timeline=timeline,
        requisition=requisition,
        requisition_item_id=requisition.items[0]._id,
        requisition_item="Laptop",
        insurance_start_date="2026-01-01",
        insurance_end_date="2027-01-01",
        seller="Seller",
        serial_number="SN-" + code,
        requisition_item_code=code,
        location="Room 1",
        status="active",
    )
    item.save()
    return item


@pytest.fixture(autouse=True)
def requisition_enabled(app, monkeypatch):
    """ขอซื้อขอจ้างปิดอยู่โดยค่าตั้งต้น (#18) เทสต์ในไฟล์นี้ทดสอบ flow ตอนเปิดใช้"""
    monkeypatch.setitem(app.config, "PROCUREMENT_REQUISITION_ENABLED", True)


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    """Two organizations, each with an admin, plus one cross-org member."""
    org_a = create_org("Org A")
    org_b = create_org("Org B")

    admin_a = create_user("AdminA", "Alpha")
    admin_a2 = create_user("AdminA2", "Alpha")
    admin_b = create_user("AdminB", "Beta")
    member_b = create_user("MemberB", "Beta")

    role_admin_a = assign_user_to_org(admin_a, org_a, roles=["admin"])
    role_admin_a2 = assign_user_to_org(admin_a2, org_a, roles=["admin"])
    role_admin_b = assign_user_to_org(admin_b, org_b, roles=["admin"])
    role_member_b = assign_user_to_org(member_b, org_b, roles=["staff"])
    for role, name in (
        (role_admin_a, "Anna"),
        (role_admin_a2, "Amy"),
        (role_admin_b, "Bob"),
        (role_member_b, "Bella"),
    ):
        role.first_name = name
        role.save()

    return SimpleNamespace(
        org_a=org_a,
        org_b=org_b,
        admin_a=admin_a,
        admin_a2=admin_a2,
        admin_b=admin_b,
        member_b=member_b,
        role_admin_a=role_admin_a,
        role_admin_a2=role_admin_a2,
        role_admin_b=role_admin_b,
        role_member_b=role_member_b,
    )


@pytest.fixture
def client_for(app, login_as):
    def _client_for(user):
        client = app.test_client()
        login_as(client, user)
        return client

    return _client_for


@pytest.fixture
def no_enqueue(monkeypatch):
    """Replace the RQ enqueue used by views so no Redis is needed."""
    calls = []

    class _Queue:
        def enqueue(self, *args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(get_id=lambda: "fake-job")

    monkeypatch.setattr(redis_rq.redis_queue, "queue", _Queue(), raising=False)
    return calls


# ---------------------------------------------------------------------------
# non_renewal / renewal_requested
# ---------------------------------------------------------------------------


def test_non_renewal_action_other_org_procurement_404_and_unchanged(world, client_for):
    procurement_b = _make_procurement(world.org_b, world.admin_b)
    client = client_for(world.admin_a)

    response = client.post(f"/procurement/requisitions/{procurement_b.id}/non-renewal?organization_id={world.org_a.id}")

    assert response.status_code == 404
    procurement_b.reload()
    assert procurement_b.status == "pending"


def test_renewal_requested_action_other_org_procurement_404_no_requisition(world, client_for):
    procurement_b = _make_procurement(world.org_b, world.admin_b)
    client = client_for(world.admin_a)

    response = client.post(
        f"/procurement/requisitions/{procurement_b.id}/renewal-requested?organization_id={world.org_a.id}"
    )

    assert response.status_code == 404
    procurement_b.reload()
    assert procurement_b.status == "pending"
    assert models.Requisition.objects.count() == 0


@pytest.mark.parametrize("suffix", ["non-renewal", "renewal-requested"])
def test_state_changing_actions_reject_get(world, client_for, suffix):
    procurement_a = _make_procurement(world.org_a, world.admin_a)
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisitions/{procurement_a.id}/{suffix}?organization_id={world.org_a.id}")

    assert response.status_code == 405
    procurement_a.reload()
    assert procurement_a.status == "pending"
    assert models.Requisition.objects.count() == 0


def test_non_renewal_action_own_org_post_changes_status(world, client_for):
    procurement_a = _make_procurement(world.org_a, world.admin_a)
    client = client_for(world.admin_a)

    response = client.post(f"/procurement/requisitions/{procurement_a.id}/non-renewal?organization_id={world.org_a.id}")

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == "disactive"
    assert procurement_a.last_updated_by.id == world.admin_a.id


def test_non_renewal_action_organization_id_from_form_body(world, client_for):
    """The confirm button posts organization_id in the URL; a form field works too."""
    procurement_a = _make_procurement(world.org_a, world.admin_a)
    client = client_for(world.admin_a)

    response = client.post(
        f"/procurement/requisitions/{procurement_a.id}/non-renewal",
        data={"organization_id": str(world.org_a.id)},
    )

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == "disactive"


def test_renewal_requested_action_own_org_post_creates_requisition(world, client_for):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[world.role_admin_a])
    client = client_for(world.admin_a)

    response = client.post(
        f"/procurement/requisitions/{procurement_a.id}/renewal-requested?organization_id={world.org_a.id}"
    )

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == "renewal-requested"
    requisitions = models.Requisition.objects()
    assert requisitions.count() == 1
    assert requisitions[0].organization.id == world.org_a.id
    assert requisitions[0].purchaser.id == world.role_admin_a.id


@pytest.mark.parametrize("path", ["/procurement/requisitions/non-renewal", "/procurement/requisitions/renewal_requested"])
def test_list_pages_still_get(world, client_for, path):
    client = client_for(world.admin_a)

    response = client.get(f"{path}?organization_id={world.org_a.id}")

    assert response.status_code == 200


def test_index_template_renders_post_forms_with_organization(world, client_for):
    procurement_a = _make_procurement(world.org_a, world.admin_a)
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisitions?organization_id={world.org_a.id}&expiration_date_range=3_months")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    action = f"/procurement/requisitions/{procurement_a.id}/non-renewal?organization_id={world.org_a.id}"
    assert f'action="{action}"' in html
    # ปุ่มต่ออายุเดิมที่สร้างคำขอซื้อถูกถอดออกจากหน้า MA (#32) ต่ออายุไปที่ฟอร์มสร้าง MA ใหม่แทน
    assert "/renewal-requested" not in html
    assert f'href="/procurement/products/{procurement_a.id}/renew?organization_id={world.org_a.id}"' in html


# ---------------------------------------------------------------------------
# create_or_edit: committee / purchaser
# ---------------------------------------------------------------------------


def _requisition_form(committee_member, purchaser=None):
    return {
        "organization_id": "",
        "purchaser": purchaser or "-",
        "phone": "0812345678",
        "start_date": "2026-12-01",
        "reason": "need it",
        "items-0-product_name": "Laptop",
        "items-0-quantity": "1",
        "items-0-category": "product",
        "items-0-amount": "100.00",
        "items-0-currency": "unit",
        "committees-0-member": str(committee_member),
        "committees-0-committee_type": "procurement",
        "committees-0-committee_position": "member",
    }


def test_create_requisition_rejects_committee_from_other_org(world, client_for, no_enqueue):
    client = client_for(world.admin_a)
    data = _requisition_form(world.role_member_b.id)
    data["organization_id"] = str(world.org_a.id)

    response = client.post(f"/procurement/requisitions/create?organization_id={world.org_a.id}", data=data)

    assert response.status_code == 200  # form re-rendered with an error
    assert models.Requisition.objects.count() == 0
    assert no_enqueue == []


def test_create_requisition_rejects_pending_committee_member(world, client_for, no_enqueue, create_user, assign_user_to_org):
    pending_user = create_user("PendingA", "Alpha")
    pending_role = assign_user_to_org(pending_user, world.org_a, roles=["staff"], status="pending")
    client = client_for(world.admin_a)
    data = _requisition_form(pending_role.id)
    data["organization_id"] = str(world.org_a.id)

    response = client.post(f"/procurement/requisitions/create?organization_id={world.org_a.id}", data=data)

    assert response.status_code == 200
    assert models.Requisition.objects.count() == 0


def test_create_requisition_accepts_active_committee_in_same_org(world, client_for, no_enqueue):
    client = client_for(world.admin_a)
    data = _requisition_form(world.role_admin_a2.id)
    data["organization_id"] = str(world.org_a.id)

    response = client.post(f"/procurement/requisitions/create?organization_id={world.org_a.id}", data=data)

    assert response.status_code == 302
    requisitions = models.Requisition.objects()
    assert requisitions.count() == 1
    assert requisitions[0].organization.id == world.org_a.id
    assert requisitions[0].purchaser.id == world.role_admin_a.id
    assert [c.member.id for c in requisitions[0].committees] == [world.role_admin_a2.id]


def test_create_form_choices_exclude_other_org_members(world, client_for):
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisitions/create?organization_id={world.org_a.id}")

    html = response.data.decode("utf-8")
    assert str(world.role_admin_a2.id) in html
    assert str(world.role_member_b.id) not in html
    assert str(world.role_admin_b.id) not in html


# ---------------------------------------------------------------------------
# details_specified
# ---------------------------------------------------------------------------


def _timeline_for(org, admin_user, admin_role, code):
    requisition = _make_requisition(org, admin_role, admin_user, code)
    timeline = _make_timeline(org, requisition, admin_role, admin_user)
    return requisition, timeline


def test_details_specified_other_org_timeline_404_on_get(world, client_for):
    _, timeline_b = _timeline_for(world.org_b, world.admin_b, world.role_admin_b, "0001/2569")
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisition_timeline/{timeline_b.id}/details_specified?organization_id={world.org_a.id}")

    assert response.status_code == 404


def test_details_specified_other_org_timeline_404_on_post_and_unchanged(world, client_for):
    requisition_b, timeline_b = _timeline_for(world.org_b, world.admin_b, world.role_admin_b, "0001/2569")
    client = client_for(world.admin_a)
    item_id = str(requisition_b.items[0]._id)

    response = client.post(
        f"/procurement/requisition_timeline/{timeline_b.id}/details_specified?organization_id={world.org_a.id}",
        data={
            "project_name": "hijacked",
            "items-0-item_id": item_id,
            "items-0-product_name": "hijacked",
            "items-0-quantity": "1",
            "items-0-amount": "1",
        },
    )

    assert response.status_code == 404
    requisition_b.reload()
    timeline_b.reload()
    assert requisition_b.project_name != "hijacked"
    assert requisition_b.items[0].product_name == "Laptop"
    assert [p.progress_status for p in timeline_b.progress] == ["request_created"]


def test_details_specified_own_org_get_ok(world, client_for):
    _, timeline_a = _timeline_for(world.org_a, world.admin_a, world.role_admin_a, "0002/2569")
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisition_timeline/{timeline_a.id}/details_specified?organization_id={world.org_a.id}")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# ExportFile download + export scoping
# ---------------------------------------------------------------------------


@pytest.fixture
def gridfs_enabled():
    import mongomock.gridfs

    mongomock.gridfs.enable_gridfs_integration()


def _make_export_file(user, organization=None, content=b"xlsx-bytes"):
    export = models.ExportFile(
        file_name="export.xlsx",
        type_="requisition_items_export",
        status="completed",
        created_by=user,
        organization=organization,
    )
    export.file.put(io.BytesIO(content), filename="export.xlsx", content_type="application/octet-stream")
    export.save()
    return export


def test_download_exported_file_other_admin_gets_404(world, client_for, gridfs_enabled):
    export = _make_export_file(world.admin_a, world.org_a)
    client = client_for(world.admin_a2)

    response = client.get(
        f"/procurement/requisition_timeline_items/download_exported_excel/{export.id}?organization_id={world.org_a.id}"
    )

    assert response.status_code == 404


def test_download_exported_file_other_org_gets_404_even_for_owner(world, client_for, gridfs_enabled, assign_user_to_org):
    assign_user_to_org(world.admin_a, world.org_b, roles=["admin"])
    export = _make_export_file(world.admin_a, world.org_a)
    client = client_for(world.admin_a)

    # owner asks for the file while viewing a different org they administrate
    response = client.get(
        f"/procurement/requisition_timeline_items/download_exported_excel/{export.id}?organization_id={world.org_b.id}"
    )

    assert response.status_code == 404


def test_download_exported_file_owner_ok(world, client_for, gridfs_enabled):
    export = _make_export_file(world.admin_a, world.org_a, content=b"hello")
    client = client_for(world.admin_a)

    response = client.get(
        f"/procurement/requisition_timeline_items/download_exported_excel/{export.id}?organization_id={world.org_a.id}"
    )

    assert response.status_code == 200
    assert response.data == b"hello"


def test_download_exported_file_legacy_without_organization_owner_gets_404(world, client_for, gridfs_enabled):
    """ไฟล์เก่าที่ไม่มี organization มีข้อมูลทุกหน่วยงานปน แม้เจ้าของก็โหลดไม่ได้ ต้อง export ใหม่"""
    export = _make_export_file(world.admin_a, organization=None, content=b"legacy")
    assert export.organization is None
    client = client_for(world.admin_a)

    response = client.get(
        f"/procurement/requisition_timeline_items/download_exported_excel/{export.id}?organization_id={world.org_a.id}"
    )

    assert response.status_code == 404


def test_export_modal_hides_legacy_file_without_organization(world, client_for, gridfs_enabled):
    legacy = _make_export_file(world.admin_a, organization=None, content=b"legacy")
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisition_timeline_items/export_excel_modal?organization_id={world.org_a.id}")

    assert response.status_code == 200
    assert str(legacy.id) not in response.data.decode("utf-8")


def test_download_exported_file_legacy_other_admin_gets_404(world, client_for, gridfs_enabled):
    export = _make_export_file(world.admin_a, organization=None)
    client = client_for(world.admin_a2)

    response = client.get(
        f"/procurement/requisition_timeline_items/download_exported_excel/{export.id}?organization_id={world.org_a.id}"
    )

    assert response.status_code == 404


def test_download_exported_file_invalid_id_404(world, client_for):
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisition_timeline_items/download_exported_excel/not-an-id?organization_id={world.org_a.id}")

    assert response.status_code == 404


def test_export_excel_enqueues_with_organization_id(world, client_for, no_enqueue):
    client = client_for(world.admin_a)

    response = client.post(f"/procurement/requisition_timeline_items/export_excel?organization_id={world.org_a.id}")

    assert response.status_code == 302
    assert len(no_enqueue) == 1
    args = no_enqueue[0][1]["args"]
    assert args[-1] == str(world.org_a.id)
    assert isinstance(args[-1], str)


def test_export_modal_download_link_carries_organization_id(world, client_for, gridfs_enabled):
    export = _make_export_file(world.admin_a, world.org_a)
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/requisition_timeline_items/export_excel_modal?organization_id={world.org_a.id}")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert f"/download_exported_excel/{export.id}?organization_id={world.org_a.id}" in html


def test_export_for_org_a_excludes_org_b_timelines(world, gridfs_enabled):
    req_a, timeline_a = _timeline_for(world.org_a, world.admin_a, world.role_admin_a, "0010/2569")
    req_b, timeline_b = _timeline_for(world.org_b, world.admin_b, world.role_admin_b, "0011/2569")
    for timeline in (timeline_a, timeline_b):
        timeline.progress.append(models.requisition_timeline.Progress(progress_status="completed"))
        timeline.save()
    _make_timeline_item(world.org_a, timeline_a, req_a, "CODE-A")
    _make_timeline_item(world.org_b, timeline_b, req_b, "CODE-B")

    today = datetime.date.today()
    export_utils.requisition_timeline_items_export(
        world.admin_a,
        start_date=(today - datetime.timedelta(days=1)).isoformat(),
        end_date=(today + datetime.timedelta(days=1)).isoformat(),
        organization_id=str(world.org_a.id),
    )

    export = models.ExportFile.objects(created_by=world.admin_a, type_="requisition_items_export").get()
    assert export.organization.id == world.org_a.id
    workbook = load_workbook(io.BytesIO(export.file.read()))
    cells = {str(cell.value) for row in workbook.active.iter_rows() for cell in row if cell.value is not None}
    assert "CODE-A" in cells
    assert "CODE-B" not in cells
    assert "SN-CODE-B" not in cells


def test_export_does_not_overwrite_legacy_or_other_org_file(world, gridfs_enabled):
    legacy = _make_export_file(world.admin_a, organization=None, content=b"legacy")
    other_org = _make_export_file(world.admin_a, world.org_b, content=b"orgb")

    export_utils.requisition_timeline_items_export(world.admin_a, organization_id=str(world.org_a.id))

    assert models.ExportFile.objects(created_by=world.admin_a).count() == 3
    assert legacy.reload().file.read() == b"legacy"
    assert other_org.reload().file.read() == b"orgb"


def test_export_requires_known_organization(world):
    with pytest.raises(ValueError):
        export_utils.requisition_timeline_items_export(world.admin_a, organization_id=None)


# ---------------------------------------------------------------------------
# products
# ---------------------------------------------------------------------------


def test_products_index_requires_login(app):
    response = app.test_client().get("/procurement/products")

    assert _is_login_redirect(response)


def test_products_image_requires_login(world, app, gridfs_enabled):
    procurement_a = _procurement_with_image(world.org_a, world.admin_a)

    response = app.test_client().get(f"/procurement/products/{procurement_a.id}/picture/pic.png")

    assert _is_login_redirect(response)


def test_products_index_logged_in_ok(world, client_for):
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/products?organization_id={world.org_a.id}")

    assert response.status_code == 200


def _procurement_with_image(organization, user):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    buffer.seek(0)
    procurement = _make_procurement(organization, user)
    procurement.image.put(buffer, filename="pic.png", content_type="image/png")
    procurement.save()
    return procurement


def test_products_image_other_org_404(world, client_for, gridfs_enabled):
    procurement_b = _procurement_with_image(world.org_b, world.admin_b)
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/products/{procurement_b.id}/picture/pic.png?organization_id={world.org_a.id}")

    assert response.status_code == 404


def test_products_image_own_org_ok(world, client_for, gridfs_enabled):
    procurement_a = _procurement_with_image(world.org_a, world.admin_a)
    client = client_for(world.admin_a)

    response = client.get(f"/procurement/products/{procurement_a.id}/picture/pic.png?organization_id={world.org_a.id}")

    assert response.status_code == 200
    assert response.mimetype == "image/png"


# ---------------------------------------------------------------------------
# renewal / non-renewal ต้องเปลี่ยนได้เฉพาะ MA ที่ pending (กันกดซ้ำ / ยิงตรง)
# ---------------------------------------------------------------------------


def test_renewal_requested_action_double_submit_creates_one_requisition(world, client_for):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[world.role_admin_a])
    client = client_for(world.admin_a)
    url = f"/procurement/requisitions/{procurement_a.id}/renewal-requested?organization_id={world.org_a.id}"

    first = client.post(url)
    second = client.post(url)

    assert first.status_code == 302
    assert second.status_code == 302
    assert models.Requisition.objects.count() == 1
    procurement_a.reload()
    assert procurement_a.status == "renewal-requested"


@pytest.mark.parametrize("status", ["active", "disactive", "renewal-requested"])
def test_renewal_requested_action_rejects_non_pending(world, client_for, status):
    procurement_a = _make_procurement(world.org_a, world.admin_a, status=status, responsible=[world.role_admin_a])
    client = client_for(world.admin_a)

    response = client.post(
        f"/procurement/requisitions/{procurement_a.id}/renewal-requested?organization_id={world.org_a.id}"
    )

    assert response.status_code == 302
    assert models.Requisition.objects.count() == 0
    procurement_a.reload()
    assert procurement_a.status == status


@pytest.mark.parametrize("status", ["active"])
def test_non_renewal_action_rejects_non_pending(world, client_for, status):
    procurement_a = _make_procurement(world.org_a, world.admin_a, status=status)
    client = client_for(world.admin_a)

    response = client.post(f"/procurement/requisitions/{procurement_a.id}/non-renewal?organization_id={world.org_a.id}")

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == status


def test_renewal_requested_action_failed_requisition_restores_pending(world, client_for, monkeypatch):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[world.role_admin_a])
    client = client_for(world.admin_a)

    def _boom(self, *args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(models.Requisition, "save", _boom)
    with pytest.raises(RuntimeError):
        client.post(f"/procurement/requisitions/{procurement_a.id}/renewal-requested?organization_id={world.org_a.id}")

    procurement_a.reload()
    assert procurement_a.status == "pending"


# ---------------------------------------------------------------------------
# สิทธิ์ต่ออายุ / ไม่ต่ออายุ: admin ทุก MA ในหน่วยงาน · staff เฉพาะ MA ที่ตัวเองรับผิดชอบ · role อื่นไม่ได้
# ---------------------------------------------------------------------------


@pytest.fixture
def org_a_members(world, create_user, assign_user_to_org):
    staff = create_user("StaffA", "Alpha")
    other_staff = create_user("OtherStaffA", "Alpha")
    head = create_user("HeadA", "Alpha")
    manager = create_user("ManagerA", "Alpha")
    return SimpleNamespace(
        staff=staff,
        other_staff=other_staff,
        head=head,
        manager=manager,
        role_staff=assign_user_to_org(staff, world.org_a, roles=["staff"]),
        role_other_staff=assign_user_to_org(other_staff, world.org_a, roles=["staff"]),
        role_head=assign_user_to_org(head, world.org_a, roles=["head"]),
        role_manager=assign_user_to_org(manager, world.org_a, roles=["manager"]),
    )


def test_renewal_requested_action_staff_responsible_ok(world, client_for, org_a_members):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[org_a_members.role_staff])
    client = client_for(org_a_members.staff)

    response = client.post(
        f"/procurement/requisitions/{procurement_a.id}/renewal-requested?organization_id={world.org_a.id}"
    )

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == "renewal-requested"
    assert models.Requisition.objects.count() == 1


def test_non_renewal_action_staff_responsible_ok(world, client_for, org_a_members):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[org_a_members.role_staff])
    client = client_for(org_a_members.staff)

    response = client.post(f"/procurement/requisitions/{procurement_a.id}/non-renewal?organization_id={world.org_a.id}")

    assert response.status_code == 302
    procurement_a.reload()
    assert procurement_a.status == "disactive"


@pytest.mark.parametrize("who", ["other_staff", "head", "manager"])
@pytest.mark.parametrize("suffix", ["non-renewal", "renewal-requested"])
def test_renewal_actions_refuse_users_without_permission(world, client_for, org_a_members, who, suffix):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[org_a_members.role_staff])
    client = client_for(getattr(org_a_members, who))

    response = client.post(f"/procurement/requisitions/{procurement_a.id}/{suffix}?organization_id={world.org_a.id}")

    # หน้า MA ใช้กติกาการมองเห็น (#31): staff ที่ไม่ได้รับผิดชอบมองไม่เห็น MA จึงได้ 404
    cannot_see = who == "other_staff" and suffix == "non-renewal"
    assert response.status_code == (404 if cannot_see else 302)
    procurement_a.reload()
    assert procurement_a.status == "pending"
    assert models.Requisition.objects.count() == 0


@pytest.mark.parametrize("who, sees_buttons", [("admin", True), ("staff", True), ("head", False), ("manager", False)])
def test_index_shows_renewal_buttons_only_to_permitted_users(world, client_for, org_a_members, who, sees_buttons):
    procurement_a = _make_procurement(world.org_a, world.admin_a, responsible=[org_a_members.role_staff])
    user = world.admin_a if who == "admin" else getattr(org_a_members, who)
    client = client_for(user)

    response = client.get(f"/procurement/requisitions?organization_id={world.org_a.id}")

    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert (f"/procurement/products/{procurement_a.id}/renew?" in html) is sees_buttons
    assert (f"delete_modal_{procurement_a.id}').showModal()" in html) is sees_buttons


@pytest.mark.parametrize("status", ["//evil.example.com", "/\\evil.example.com", "https://evil.example.com"])
def test_pay_installment_rejects_external_next_url(world, client_for, status):
    from kampan.web.views.procurement import payment

    assert payment._safe_next_url(status, "/ok") == "/ok"
    assert payment._safe_next_url("/procurement/products?x=1", "/ok") == "/procurement/products?x=1"


def test_requisitions_default_filter_includes_expired(world, client_for):
    expired = _make_procurement(world.org_a, world.admin_a, name="Expired MA")
    models.ProcurementItem.objects(procurement=expired).update(
        set__end_date=datetime.datetime.now() - datetime.timedelta(days=10)
    )
    client = client_for(world.admin_a)
    base = f"/procurement/requisitions?organization_id={world.org_a.id}"

    default_html = client.get(base).data.decode("utf-8")
    three_months_html = client.get(base + "&expiration_date_range=3_months").data.decode("utf-8")

    assert "Expired MA" in default_html
    assert "Expired MA" not in three_months_html


@pytest.mark.parametrize(
    "path,status",
    [("/procurement/requisitions", "pending"), ("/procurement/requisitions/non-renewal", "disactive")],
)
def test_renewal_lists_show_sub_contracts_not_parent(world, client_for, path, status):
    """สัญญาหลักที่แยกสัญญาย่อยแล้วเป็นแค่ข้อมูลอ้างอิง หน้ารายการแสดงเฉพาะสัญญาย่อย"""
    parent = _make_procurement(world.org_a, world.admin_a, name="Parent MA", status=status)
    child = _make_procurement(world.org_a, world.admin_a, name="Child MA", status=status)
    child.parent_procurement = parent
    child.save()
    client = client_for(world.admin_a)

    html = client.get(f"{path}?organization_id={world.org_a.id}").data.decode("utf-8")

    assert "Child MA" in html
    assert "Parent MA" not in html


def test_products_list_has_no_request_renewal(world, client_for):
    """ไม่มีขั้นตอนขอต่ออายุแล้ว MA ที่ใกล้หมดอายุไปอยู่ในหน้ารายการใกล้หมดอายุเอง"""
    active = _make_procurement(world.org_a, world.admin_a, name="Active MA", status="active")
    client = client_for(world.admin_a)

    html = client.get(f"/procurement/products?organization_id={world.org_a.id}").data.decode("utf-8")
    response = client.post(f"/procurement/products/{active.id}/request-renewal?organization_id={world.org_a.id}")

    assert "request-renewal" not in html
    assert response.status_code in (404, 405)
    active.reload()
    assert active.status == "active"


def test_renew_links_warn_when_unpaid_installments_exist(world, client_for):
    """ต่ออายุแล้ว MA เดิมถูกปิดและหยุดเตือน จึงเตือนก่อนถ้ายังมีงวดที่ไม่ได้บันทึกจ่าย"""
    unpaid = _make_procurement(world.org_a, world.admin_a, name="Unpaid MA", status="pending")
    single = _make_procurement(world.org_a, world.admin_a, name="Single MA", status="pending")
    models.ProcurementItem.objects(procurement=unpaid).update(
        set__installments=[
            models.Installment(due_date=datetime.datetime.now() + datetime.timedelta(days=10), amount=Decimal("500.00")),
            models.Installment(due_date=datetime.datetime.now() + datetime.timedelta(days=100), amount=Decimal("500.00")),
        ]
    )
    paid = _make_procurement(world.org_a, world.admin_a, name="Paid MA", status="pending")
    models.ProcurementItem.objects(procurement=paid).update(
        set__installments=[models.Installment(due_date=datetime.datetime.now(), paid_date=datetime.datetime.now())]
    )
    client = client_for(world.admin_a)
    org = world.org_a.id

    unpaid_detail = client.get(f"/procurement/payment/{unpaid.id}?organization_id={org}").data.decode("utf-8")
    paid_detail = client.get(f"/procurement/payment/{paid.id}?organization_id={org}").data.decode("utf-8")
    listing = client.get(f"/procurement/requisitions?organization_id={org}").data.decode("utf-8")

    assert f'id="renew_check_{unpaid.id}"' in unpaid_detail
    # modal เตือน: บันทึกจ่ายด้วยยอดเต็มของงวดเป็นค่าตั้งต้น
    assert 'name="paid_amount" value="500.00"' in unpaid_detail.split(f'id="renew_check_{unpaid.id}"', 1)[1]
    assert f'data-renew-check="renew_check_{unpaid.id}"' in unpaid_detail
    assert f"/installments/" in unpaid_detail and "/pay?" in unpaid_detail
    assert f'id="renew_check_{paid.id}"' not in paid_detail
    assert f'id="renew_check_{unpaid.id}"' in listing
    assert f'id="renew_check_{paid.id}"' not in listing
    # รายการที่มีงวดเดียว ต่ออายุ = จ่ายงวดนั้น จึงไม่ต้องเตือน
    assert f'id="renew_check_{single.id}"' not in listing


def test_split_item_with_one_installment_is_warned_not_paid_by_renewal(world, client_for):
    """ติ๊ก "แบ่งจ่ายเป็นงวด" แม้มีงวดเดียวก็ไม่ใช่จ่ายครั้งเดียว ต้องเตือนและไม่บันทึกจ่ายให้ตอนต่ออายุ"""
    split = _make_procurement(world.org_a, world.admin_a, name="Split MA", status="pending")
    models.ProcurementItem.objects(procurement=split).update(set__installment_mode=True)
    client = client_for(world.admin_a)

    html = client.get(f"/procurement/payment/{split.id}?organization_id={world.org_a.id}").data.decode("utf-8")
    assert f'id="renew_check_{split.id}"' in html
    split = models.Procurement.objects(id=split.id).get()  # โหลดใหม่ (get_items เก็บ cache ไว้)
    assert [row[1] for row in split.get_unpaid_installments()] == [1]
    assert split.pay_single_installments_on_renewal(world.admin_a) == 0
    assert not any(item.installments[0].is_paid() for item in split.get_items())


def test_pay_modals_default_paid_amount_to_due_amount(world, client_for):
    """ยอดที่จ่ายจริงตั้งต้นเป็นยอดที่ต้องจ่าย (ใช้ได้ทั้งหน้ารายละเอียดและตารางรายการ MA)"""
    procurement = _make_procurement(world.org_a, world.admin_a, name="Amount MA", status="active")
    client = client_for(world.admin_a)
    org = world.org_a.id

    detail = client.get(f"/procurement/payment/{procurement.id}?organization_id={org}").data.decode("utf-8")
    listing = client.get(f"/procurement/products?organization_id={org}").data.decode("utf-8")

    assert 'name="paid_amount"' in detail and 'value="1000.00"' in detail.split('name="paid_amount"', 1)[1][:300]
    assert 'value="1000.00"' in listing.split('name="paid_amount"', 1)[1][:300]


def test_list_edit_button_opens_the_sub_item_when_ma_has_one_item(world, client_for):
    """MA ที่มีรายการย่อยเดียว (เช่น สัญญาย่อย) กดแก้ไขจากรายการแล้วไปแก้รายการย่อยนั้นโดยตรง"""
    single = _make_procurement(world.org_a, world.admin_a, name="Single MA", status="pending")
    (item,) = single.get_items()
    client = client_for(world.admin_a)
    org = world.org_a.id

    for path in ("/procurement/products", "/procurement/requisitions"):
        html = client.get(f"{path}?organization_id={org}").data.decode("utf-8")
        assert f"/procurement/products/{single.id}/edit?" in html
        assert f"item_id={item.id}" in html


def test_list_edit_button_stays_header_only_for_multi_item_ma(world, client_for):
    multi = _make_procurement(world.org_a, world.admin_a, name="Multi MA", status="active")
    extra = models.ProcurementItem(
        name="Second", category="product", amount=Decimal("500.00"),
        start_date=datetime.datetime.now(), end_date=datetime.datetime.now() + datetime.timedelta(days=30),
        installments=[models.Installment(due_date=datetime.datetime.now() + datetime.timedelta(days=30))],
    )
    multi.total_amount = Decimal("1500.00")
    multi.save_with_items([*multi.get_items(), extra])
    client = client_for(world.admin_a)

    html = client.get(f"/procurement/products?organization_id={world.org_a.id}").data.decode("utf-8")

    assert f"/procurement/products/{multi.id}/edit?" in html
    assert "item_id=" not in html
