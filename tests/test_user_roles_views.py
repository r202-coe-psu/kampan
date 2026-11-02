def test_user_roles_requires_admin(app, create_user, login_as):
    user = create_user("Regular", "User", roles=["user"])

    with app.test_client() as client:
        login_as(client, user)
        response = client.get("/organizations/system/users/")

    assert response.status_code == 302


def test_user_roles_filters_role_and_displays_role_label(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    staff = create_user("Staff", "User", roles=["staff"])
    student = create_user("Student", "User", roles=["student"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/organizations/system/users/?role=staff")

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
        response = client.get("/organizations/system/users/?name=%E0%B8%8A%E0%B8%B7%E0%B9%88%E0%B8%AD%E0%B8%88%E0%B8%B2%E0%B8%81+PSU")

    assert response.status_code == 200
    assert user.email in response.data.decode()


def test_user_roles_rejects_invalid_or_oversized_filters(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        invalid_role = client.get("/organizations/system/users/?role=unknown")
        oversized_name = client.get(f"/organizations/system/users/?name={'x' * 129}")

    assert invalid_role.status_code == 400
    assert oversized_name.status_code == 400


def test_user_roles_is_get_only(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.post("/organizations/system/users/", data={"role": "admin"})

    assert response.status_code == 405


def test_old_user_roles_url_redirects_to_organization_module(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.get("/admin/user-roles?role=staff")

    assert response.status_code == 301
    assert response.headers["Location"] == "/organizations/system/users/?role=staff"


def test_edit_roles_changes_only_roles(app, create_user, login_as):
    admin = create_user("Admin", "User", roles=["admin"])
    user = create_user("Target", "User", roles=["user"])

    with app.test_client() as client:
        login_as(client, admin)
        response = client.post(
            f"/organizations/system/users/{user.id}/edit-roles",
            data={"roles": ["supervisor"]},
        )

    user.reload()
    assert response.status_code == 302
    assert user.roles == ["supervisor"]
    assert user.first_name == "Target"
    assert user.username == "target_user"

