import pytest
from flask import session
from kampan import models


def test_user_is_member_of(app, create_org, create_user, assign_user_to_org):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        user = create_user("Alice", "Tester")

        assign_user_to_org(user, org_a, roles=["staff"], status="active")

        assert user.is_member_of(org_a) is True
        assert user.is_member_of(org_b) is False


def test_user_is_member_of_disactive(app, create_org, create_user, assign_user_to_org):
    with app.app_context():
        org_a = create_org("Org A")
        user = create_user("Alice", "Disactive")

        assign_user_to_org(user, org_a, roles=["staff"], status="disactive")

        assert user.is_member_of(org_a) is False


def test_user_get_organization_roles_isolated_per_org(app, create_org, create_user, assign_user_to_org):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        user = create_user("Bob", "Tester")

        assign_user_to_org(user, org_a, roles=["admin"])
        assign_user_to_org(user, org_b, roles=["staff"])

        assert user.get_organization_roles(org_a) == ["admin"]
        assert user.get_organization_roles(org_b) == ["staff"]
        assert user.has_organization_roles("admin", organization=org_a) is True
        assert user.has_organization_roles("admin", organization=org_b) is False


def test_global_admin_has_full_org_access(app, create_org, create_user):
    with app.app_context():
        org = create_org("Org X")
        admin_user = create_user("Super", "Admin", roles=["admin"])

        assert admin_user.is_member_of(org) is True
        assert admin_user.has_organization_roles("any_role", organization=org) is True


def test_get_selectable_organizations(app, create_org, create_user, assign_user_to_org):
    with app.app_context():
        org_a = create_org("Org A")
        org_b = create_org("Org B")
        org_c = create_org("Org C")
        user = create_user("David", "User")
        admin = create_user("Admin", "User", roles=["admin"])

        assign_user_to_org(user, org_a)
        assign_user_to_org(user, org_b)

        user_orgs = user.get_selectable_organizations()
        assert len(user_orgs) == 2
        assert org_a in user_orgs
        assert org_b in user_orgs
        assert org_c not in user_orgs

        admin_orgs = admin.get_selectable_organizations()
        assert len(admin_orgs) == 3


def test_switch_organization_endpoint(app, create_org, create_user, assign_user_to_org):
    with app.test_client() as client:
        with app.app_context():
            org_a = create_org("Org Alpha")
            org_b = create_org("Org Beta")
            org_c = create_org("Org Gamma")
            user = create_user("Charlie", "MultiOrg")

            assign_user_to_org(user, org_a, roles=["staff"])
            assign_user_to_org(user, org_b, roles=["admin"])

            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True

            # Switch to Org B (which user belongs to) -> 302 redirect to select_system for Org B
            response = client.get(f"/switch_organization?organization_id={org_b.id}")
            assert response.status_code == 302
            assert f"organization_id={org_b.id}" in response.location

            reloaded_user = models.User.objects(id=user.id).first()
            assert reloaded_user.user_setting.current_organization == org_b

            # Switch to Org C (which user does NOT belong to) -> abort(403) -> 302 redirect to login
            response_denied = client.get(f"/switch_organization?organization_id={org_c.id}")
            assert response_denied.status_code == 302
            assert "/login" in response_denied.location
