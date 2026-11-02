def test_user_roles_requires_admin(app, create_user, login_as):
    user = create_user("Regular", "User", roles=["user"])

    with app.test_client() as client:
        login_as(client, user)
        response = client.get("/users/")

    assert response.status_code == 302


def test_user_roles_filters_role_and_displays_role_label(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    staff = create_user("Staff", "User", roles=["staff"])
    student = create_user("Student", "User", roles=["student"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/users/?role=staff")

    body = response.data.decode()
    assert response.status_code == 200
    assert staff.email in body
    assert "พนักงาน" in body
    assert student.email not in body


def test_user_roles_searches_psu_display_name(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    user = create_user("Stored", "Name", roles=["user"])
    user.resources = {"psu": {"display_name_th": "ชื่อจาก PSU"}}
    user.save()

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/users/?name=%E0%B8%8A%E0%B8%B7%E0%B9%88%E0%B8%AD%E0%B8%88%E0%B8%B2%E0%B8%81+PSU")

    assert response.status_code == 200
    assert user.email in response.data.decode()


def test_user_roles_rejects_invalid_or_oversized_filters(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        invalid_role = client.get("/users/?role=unknown")
        oversized_name = client.get(f"/users/?name={'x' * 129}")

    assert invalid_role.status_code == 400
    assert oversized_name.status_code == 400


def test_user_roles_is_get_only(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.post("/users/", data={"role": "admin"})

    assert response.status_code == 405


def test_old_user_roles_url_redirects_to_users_page(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/admin/user-roles?role=staff")

    assert response.status_code == 301
    assert response.headers["Location"] == "/users/?role=staff"


def test_edit_roles_changes_only_roles(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    user = create_user("Target", "User", roles=["user"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.post(
            f"/users/{user.id}/edit-roles",
            data={"roles": ["supervisor"]},
        )

    user.reload()
    assert response.status_code == 302
    assert user.roles == ["supervisor"]
    assert user.first_name == "Target"
    assert user.username == "target_user"


def _role_counts(html):
    import re

    return {
        role: int(count)
        for role, count in re.findall(
            r'data-role="([^"]+)"[^>]*>\s*<span[^>]*>[^<]*</span>\s*<span[^>]*data-role-count>(\d+)</span>',
            html,
        )
    }


def test_user_dashboard_counts_each_role(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    create_user("Studenta", "User", roles=["student"])
    create_user("Studentb", "User", roles=["student", "staff"])
    create_user("Lecturer", "User", roles=["lecturer"])
    create_user("Legacy", "User", roles=["alumni"])
    nobody = create_user("Nobody", "User")
    nobody.roles = []
    nobody.save()

    with app.test_client() as client:
        login_as(client, admin)
        html = client.get("/users/").get_data(as_text=True)

    counts = _role_counts(html)
    assert counts["admin"] == 1
    assert counts["student"] == 2
    assert counts["staff"] == 1
    assert counts["lecturer"] == 1
    assert counts["supervisor"] == 0
    assert counts["alumni"] == 1
    assert counts["none"] == 1
    assert "data-total-users>6<" in html


def test_user_list_filters_users_without_role(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    nobody = create_user("Nobody", "User")
    nobody.roles = []
    nobody.save()

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/users/?role=none")

    html = response.get_data(as_text=True)
    table = html[html.index("<tbody>"):html.index("</tbody>")]
    assert response.status_code == 200
    assert nobody.email in table
    assert admin.email not in table


def test_edit_roles_offers_every_role_with_thai_labels(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    user = create_user("Target", "User", roles=["user"])

    with app.test_client() as client:
        login_as(client, admin)
        html = client.get(f"/users/{user.id}/edit-roles").get_data(as_text=True)

    for value, label in [
        ("admin", "ผู้ดูแลระบบ"),
        ("supervisor", "หัวหน้างาน"),
        ("user", "ผู้ใช้งาน"),
        ("staff", "พนักงาน"),
        ("student", "นักศึกษา"),
        ("lecturer", "อาจารย์"),
    ]:
        assert f'value="{value}"' in html
        assert label in html


def test_edit_roles_keeps_roles_not_in_form(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    user = create_user("Target", "User", roles=["alumni", "lecturer", "user"])

    with app.test_client() as client:
        login_as(client, admin)
        client.post(
            f"/users/{user.id}/edit-roles",
            data={"roles": ["student", "staff"]},
        )

    user.reload()
    assert user.roles == ["student", "staff", "alumni"]
