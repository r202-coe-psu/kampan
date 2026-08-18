import pytest
from flask import g
from werkzeug.exceptions import Forbidden

from kampan import models
from kampan.web import acl


def test_acl_resolve_organization_valid(app, create_org, create_user, assign_user_to_org):
    with app.test_client() as client:
        with app.app_context():
            org = create_org("Org Test")
            user = create_user("John", "Doe")
            assign_user_to_org(user, org, roles=["staff"])

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True

            # Request with valid organization_id in query params
            response = client.get(f"/accounts?organization_id={org.id}")
            assert response.status_code in (200, 302)


def test_acl_resolve_organization_denied(app, create_org, create_user):
    with app.test_client() as client:
        with app.app_context():
            org_unauthorized = create_org("Secret Org")
            user = create_user("Outsider", "User")

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True

            # Accessing an org the user is not a member of -> triggers 403 / redirect
            response = client.get(f"/accounts?organization_id={org_unauthorized.id}")
            # abort(403) redirects to login due to unauthorized_callback
            assert response.status_code == 302
            assert "/login" in response.location


def test_organization_roles_required_decorator(app, create_org, create_user, assign_user_to_org):
    with app.test_request_context("/test-route?organization_id=some_id"):
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        user = create_user("Alice", "AdminInA")

        assign_user_to_org(user, org_a, roles=["admin"])
        assign_user_to_org(user, org_b, roles=["staff"])

        # Decorator test
        @acl.organization_roles_required("admin")
        def protected_view():
            return "SUCCESS"

        # Mock current_user & g.organization for Org A (Admin)
        from flask_login import login_user
        login_user(user)

        g.organization = org_a
        g.organization_denied = False
        assert protected_view() == "SUCCESS"

        # Org B (Staff, not Admin) -> Forbidden
        g.organization = org_b
        g.organization_denied = False
        with pytest.raises(Forbidden):
            protected_view()

        # Denied org -> Forbidden
        g.organization_denied = True
        with pytest.raises(Forbidden):
            protected_view()
