import datetime
from decimal import Decimal
import pytest
from kampan import models


def create_test_procurement(organization, name="Test Procurement", status="active", user=None):
    procurement = models.Procurement(
        name=name,
        category="product",
        company="Test Vendor Co., Ltd.",
        organization=organization,
        status=status,
        amount=Decimal("1000.00"),
        period=1,
        start_date=datetime.datetime.now(),
        end_date=datetime.datetime.now() + datetime.timedelta(days=30),
        created_by=user,
        last_updated_by=user,
    )
    procurement.save()
    return procurement


def test_procurement_payment_cross_tenant_isolation(app, create_org, create_user, assign_user_to_org):
    """Ensure user from Org A cannot access or pay a procurement belonging to Org B."""
    with app.test_client() as client:
        with app.app_context():
            org_a = create_org("Org A")
            org_b = create_org("Org B")
            user_a = create_user("UserA", "MemberA")
            assign_user_to_org(user_a, org_a, roles=["staff"])

            # Procurement belonging to Org B
            procurement_b = create_test_procurement(org_b, name="Org B Contract", user=user_a)

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user_a.id)
                sess["_fresh"] = True

            # Attempt to access Org B procurement while in context of Org A
            # Should abort 404 because of scoping (id=procurement_id, organization=g.organization)
            response_view = client.get(f"/payment/{procurement_b.id}?organization_id={org_a.id}")
            assert response_view.status_code == 404

            response_pay = client.post(f"/payment/{procurement_b.id}/set_paid?organization_id={org_a.id}")
            assert response_pay.status_code == 404
