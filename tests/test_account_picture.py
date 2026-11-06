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
