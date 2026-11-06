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
