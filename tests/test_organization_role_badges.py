from flask import url_for

from kampan.models.organizations import ORGANIZATION_ROLES


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def test_role_items_pair_keys_with_labels(app, create_org, create_user, assign_user_to_org):
    org = create_org("Role Org")
    admin = create_user("Adminuser", "Role")
    org_user = assign_user_to_org(admin, org, roles=["admin", "supervisor supplier"])

    assert org_user.role_items() == [
        ("admin", dict(ORGANIZATION_ROLES)["admin"]),
        ("supervisor supplier", dict(ORGANIZATION_ROLES)["supervisor supplier"]),
    ]
    assert org_user.display_roles()


def test_members_page_renders_role_badges(app, create_org, create_user, assign_user_to_org):
    org = create_org("Role Org")
    admin = create_user("Adminuser", "Role")
    assign_user_to_org(admin, org, roles=["admin", "supervisor supplier"])

    with app.test_request_context():
        url = url_for("organizations.members.index", organization_id=str(org.id))

    with app.test_client() as client:
        _login(client, admin)
        html = client.get(url).get_data(as_text=True)

    assert "role-badge role-admin" in html
    assert "role-badge role-supervisor-supplier" in html
