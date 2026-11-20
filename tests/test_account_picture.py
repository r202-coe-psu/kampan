import io

from PIL import Image


def make_image_bytes(fmt="PNG", size=(40, 40), color=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(client, data, filename="me.png", content_type="image/png"):
    return client.post(
        "/accounts/picture",
        data={"picture": (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


def test_user_can_upload_picture_and_it_is_served_as_image(app, create_user, login_as):
    user = create_user("Pic", "Owner")

    with app.test_client() as client:
        login_as(client, user)
        response = upload(client, make_image_bytes("PNG"))
        assert response.status_code == 302

        served = client.get(f"/accounts/{user.id}/picture")

    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_non_image_upload_is_refused_with_thai_error_and_nothing_stored(app, create_user, login_as):
    user = create_user("Bad", "File")

    with app.test_client() as client:
        login_as(client, user)
        response = upload(client, b"not an image at all", filename="me.png", content_type="image/png")
        followed = client.get(response.headers["Location"])
        served = client.get(f"/accounts/{user.id}/picture")

    assert "ไฟล์ที่เลือกไม่ใช่รูปภาพ" in followed.data.decode()
    assert served.status_code == 404


def test_oversized_image_upload_is_refused_with_thai_error_and_nothing_stored(app, create_user, login_as):
    user = create_user("Big", "File")
    # สุ่มพิกเซลให้ PNG บีบอัดไม่ได้ ขนาดจึงเกิน 2 MB จริง
    import os

    raw = Image.frombytes("RGB", (1000, 1000), os.urandom(3 * 1000 * 1000))
    buffer = io.BytesIO()
    raw.save(buffer, format="PNG")
    assert len(buffer.getvalue()) > 2 * 1024 * 1024

    with app.test_client() as client:
        login_as(client, user)
        response = upload(client, buffer.getvalue())
        followed = client.get(response.headers["Location"])
        served = client.get(f"/accounts/{user.id}/picture")

    assert "ไฟล์รูปภาพต้องมีขนาดไม่เกิน 2 MB" in followed.data.decode()
    assert served.status_code == 404


def test_upload_only_changes_the_logged_in_users_picture(app, create_user, login_as):
    owner = create_user("Own", "Er")
    other = create_user("Some", "Oneelse")

    with app.test_client() as client:
        login_as(client, owner)
        client.post(
            f"/accounts/picture?user_id={other.id}",
            data={
                "user_id": str(other.id),
                "picture": (io.BytesIO(make_image_bytes("PNG")), "me.png", "image/png"),
            },
            content_type="multipart/form-data",
        )
        owner_picture = client.get(f"/accounts/{owner.id}/picture")
        other_picture = client.get(f"/accounts/{other.id}/picture")

    assert owner_picture.status_code == 200
    assert other_picture.status_code == 404


def test_anonymous_upload_is_redirected_to_login_and_nothing_stored(app, create_user):
    user = create_user("Anon", "Target")

    with app.test_client() as client:
        response = upload(client, make_image_bytes("PNG"))
        served = client.get(f"/accounts/{user.id}/picture")

    assert response.status_code in (302, 401)
    assert served.status_code == 404


def test_user_without_picture_has_no_picture_resource(app, create_user):
    user = create_user("No", "Picture")

    with app.test_client() as client:
        served = client.get(f"/accounts/{user.id}/picture")

    assert served.status_code == 404


def user_avatar_sources(html_text):
    from html.parser import HTMLParser

    sources = []

    class Finder(HTMLParser):
        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if tag == "img" and "user-avatar" in (attributes.get("class") or "").split():
                sources.append(attributes.get("src"))

    Finder().feed(html_text)
    return sources


def test_header_avatar_uses_uploaded_picture(app, create_user, login_as):
    user = create_user("Head", "Er")

    with app.test_client() as client:
        login_as(client, user)
        upload(client, make_image_bytes("PNG"))
        page = client.get("/accounts")

    assert page.status_code == 200
    sources = user_avatar_sources(page.data.decode())
    assert len(sources) == 1
    assert sources[0].startswith(f"/accounts/{user.id}/picture")


def test_header_avatar_falls_back_to_icon_without_picture(app, create_user, login_as):
    user = create_user("Plain", "User")

    with app.test_client() as client:
        login_as(client, user)
        page = client.get("/accounts")

    assert page.status_code == 200
    assert user_avatar_sources(page.data.decode()) == []
    assert "ph-user" in page.data.decode()


def test_account_page_offers_picture_upload_form(app, create_user, login_as):
    user = create_user("Form", "Seen")

    with app.test_client() as client:
        login_as(client, user)
        page = client.get("/accounts")

    body = page.data.decode()
    assert 'action="/accounts/picture"' in body
    assert 'enctype="multipart/form-data"' in body
    assert 'type="file"' in body
    assert 'name="picture"' in body
