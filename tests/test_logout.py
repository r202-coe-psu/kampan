"""ออกจากระบบ: POST + CSRF เท่านั้น และล้างทุกคีย์ใน session"""

import re

import pytest


@pytest.fixture
def logged_in(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org("[TEST] Logout Org")
    user = create_user("Logout", "Probe")
    assign_user_to_org(user, org, roles=["admin"])
    client = app.test_client()
    login_as(client, user)
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "psu"
        sess["uploaded_email_template_form"] = {"x": 1}
    return client, org


def _protected(client, org):
    return client.get(f"/procurement/products?organization_id={org.id}")


def test_logout_post_signs_out_and_clears_whole_session(logged_in):
    client, org = logged_in
    assert _protected(client, org).status_code == 200

    response = client.post("/logout")

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert dict(sess) == {}
    assert "/login" in _protected(client, org).headers["Location"]


def test_logout_get_is_not_allowed_and_keeps_the_session(logged_in):
    client, org = logged_in

    response = client.get("/logout")

    assert response.status_code == 405
    assert _protected(client, org).status_code == 200
    with client.session_transaction() as sess:
        assert sess["oauth_provider"] == "psu"


def test_logout_without_valid_csrf_token_is_refused(app, monkeypatch, logged_in):
    client, org = logged_in
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", True)

    response = client.post("/logout")

    assert response.status_code == 302
    assert "/select_system" in response.headers["Location"]
    monkeypatch.setitem(app.config, "WTF_CSRF_ENABLED", False)
    assert _protected(client, org).status_code == 200


def test_logout_requires_login(app):
    response = app.test_client().post("/logout")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_logout_is_post_only_and_clears_session(app, create_user, login_as):
    admin = create_user("Sysadmin", "Probe", roles=["admin"])
    client = app.test_client()
    login_as(client, admin)
    with client.session_transaction() as sess:
        sess["oauth_provider"] = "psu"

    assert client.get("/admin/logout").status_code == 405

    response = client.post("/admin/logout")

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert dict(sess) == {}


@pytest.mark.parametrize(
    "path",
    ("/select_system?organization_id={org}", "/procurement/products?organization_id={org}"),
)
def test_pages_render_logout_as_post_form_not_link(logged_in, path):
    client, org = logged_in

    html = client.get(path.format(org=org.id)).get_data(as_text=True)

    assert not re.search(r'<a[^>]+href="/logout"', html)
    assert re.search(r'<form[^>]+method="post"[^>]+action="/logout"', html)
    assert 'name="csrf_token"' in html
