import datetime

from kampan import models


def test_procurement_payment_cross_tenant_isolation(app, create_org, create_user, assign_user_to_org, create_ma):
    """Ensure user from Org A cannot access or pay a procurement belonging to Org B."""
    with app.test_client() as client:
        with app.app_context():
            org_a = create_org("Org A")
            org_b = create_org("Org B")
            user_a = create_user("UserA", "MemberA")
            assign_user_to_org(user_a, org_a, roles=["admin"])

            # Procurement belonging to Org B (สร้างโดย user_a จึงผ่านกติกา created_by ถ้าหลุด scope)
            procurement_b = create_ma(org_b, name="Org B Contract", user=user_a)
            item_b = procurement_b.get_items()[0]
            installment_b = item_b.installments[0]

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user_a.id)
                sess["_fresh"] = True

            # Attempt to access Org B procurement while in context of Org A
            # Should abort 404 because of scoping (id=procurement_id, organization=g.organization)
            response_view = client.get(f"/procurement/payment/{procurement_b.id}?organization_id={org_a.id}")
            assert response_view.status_code == 404

            pay_url = (
                f"/procurement/payment/{procurement_b.id}/items/{item_b.id}"
                f"/installments/{installment_b._id}/pay?organization_id={org_a.id}"
            )
            response_pay = client.post(pay_url, data={"paid_date": datetime.date.today().isoformat()})
            assert response_pay.status_code == 404

            item_b.reload()
            assert item_b.installments[0].paid_date is None
            assert models.ProcurementItem.objects(organization=org_b).count() == 1


def test_procurement_manual_authorized(app, create_org, create_user, assign_user_to_org):
    """Ensure authorized user can view the procurement manual with organization_id param."""
    with app.test_client() as client, app.app_context():
        org = create_org("Procurement Org")
        user = create_user("ProcUser", "Staff")
        assign_user_to_org(user, org, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get(f"/procurement/manuals?organization_id={org.id}")
        assert response.status_code == 200
        assert "คู่มือการใช้งาน" in response.data.decode("utf-8")


def test_procurement_manual_default_org(app, create_org, create_user, assign_user_to_org):
    """Ensure authorized user can view manual using their default organization without query arg."""
    with app.test_client() as client, app.app_context():
        org = create_org("Procurement Org")
        user = create_user("ProcUser", "Staff")
        assign_user_to_org(user, org, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get("/procurement/manuals")
        assert response.status_code == 200
        assert "คู่มือการใช้งาน" in response.data.decode("utf-8")


def test_procurement_manual_unauthenticated(app, create_org):
    """Ensure unauthenticated user is redirected or denied access."""
    with app.test_client() as client, app.app_context():
        org = create_org("Procurement Org")
        response = client.get(f"/procurement/manuals?organization_id={org.id}")
        assert response.status_code in [302, 401, 403]


def test_procurement_manual_unauthorized_org(app, create_org, create_user, assign_user_to_org):
    """Ensure user from Org A cannot access Org B's manual."""
    with app.test_client() as client, app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        user_a = create_user("UserA", "MemberA")
        assign_user_to_org(user_a, org_a, roles=["staff"])

        with client.session_transaction() as sess:
            sess["_user_id"] = str(user_a.id)
            sess["_fresh"] = True

        response = client.get(f"/procurement/manuals?organization_id={org_b.id}")
        assert response.status_code == 403
