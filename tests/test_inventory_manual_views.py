import pytest
from kampan import models


def test_inventory_manual_authorized_with_org_id(app, create_org, create_user, assign_user_to_org):
    """Ensure authorized user can view the inventory manual with organization_id param."""
    with app.test_client() as client, app.app_context():
        org = create_org("Inventory Test Org")
        user = create_user("InvStaff", "User")
        assign_user_to_org(user, org, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get(f"/inventories/manual?organization_id={org.id}")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "คู่มือการใช้งาน ระบบเบิกวัสดุและคลังพัสดุ" in html
        assert "Inventory Test Org" in html


def test_inventory_manual_authorized_default_org(app, create_org, create_user, assign_user_to_org):
    """Ensure authorized user can view inventory manual using session context organization."""
    with app.test_client() as client, app.app_context():
        org = create_org("Default Org")
        user = create_user("DefaultUser", "Staff")
        assign_user_to_org(user, org, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get("/inventories/manual")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "คู่มือการใช้งาน ระบบเบิกวัสดุและคลังพัสดุ" in html


def test_inventory_manual_unauthenticated(app, create_org):
    """Ensure unauthenticated user is redirected or denied access."""
    with app.test_client() as client, app.app_context():
        org = create_org("Public Org")
        response = client.get(f"/inventories/manual?organization_id={org.id}")
        assert response.status_code in [302, 401, 403]


def test_inventory_manual_cross_tenant_isolation(app, create_org, create_user, assign_user_to_org):
    """Ensure user from Org A cannot access Org B's manual."""
    with app.test_client() as client, app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        user_a = create_user("UserA", "MemberA")
        assign_user_to_org(user_a, org_a, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)
            sess["_fresh"] = True

        response = client.get(f"/inventories/manual?organization_id={org_b.id}")
        assert response.status_code == 403


def test_inventory_manual_content_sections(app, create_org, create_user, assign_user_to_org):
    """Ensure template contains all key sections, TOC modules, and status summary."""
    with app.test_client() as client, app.app_context():
        org = create_org("Full Content Org")
        user = create_user("AdminUser", "Manager")
        assign_user_to_org(user, org, roles=["admin"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get(f"/inventories/manual?organization_id={org.id}")
        assert response.status_code == 200
        html = response.data.decode("utf-8")

        # Verify key headings and TOC items
        assert "สารบัญคู่มือ (23 โมดูล)" in html
        assert "ภาพรวมและบทบาทผู้ใช้งาน" in html
        assert "ขั้นตอนการทำงานภาพรวมทั้งระบบ" in html
        assert "1. แดชบอร์ดภาพรวมคลังวัสดุ" in html
        assert "13. คำสั่งเบิกวัสดุ (สร้างและติดตาม)" in html
        assert "18. พัสดุอนุมัติคำสั่งเบิกและตัดสต็อก (ขั้นที่ 3)" in html
        assert "ตารางสรุปสถานะคำสั่งเบิกและขั้นตอนดำเนินงาน" in html
