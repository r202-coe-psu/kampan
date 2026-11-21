import base64
import io

from PIL import Image


def make_png_bytes(size=(60, 30), color=(10, 10, 120)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def upload_signature(client, data, filename="sign.png", content_type="image/png"):
    return client.post(
        "/accounts/signature",
        data={"signature": (io.BytesIO(data), filename, content_type)},
        content_type="multipart/form-data",
    )


def draw_signature(client, data_url):
    return client.post("/accounts/signature", data={"signature_data": data_url})


def test_user_can_upload_signature_and_it_is_served_as_png(app, create_user, login_as):
    user = create_user("Sign", "Uploader")

    with app.test_client() as client:
        login_as(client, user)
        response = upload_signature(client, make_png_bytes())
        assert response.status_code == 302

        served = client.get(f"/accounts/{user.id}/signature")

    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_users_cannot_fetch_someone_elses_signature(app, create_user, login_as):
    owner = create_user("Sign", "Owner")
    other = create_user("Sign", "Snoop")
    with app.test_client() as client:
        login_as(client, owner)
        upload_signature(client, make_png_bytes())

    with app.test_client() as client:
        login_as(client, other)
        served = client.get(f"/accounts/{owner.id}/signature")

    assert served.status_code == 404


def test_user_can_draw_signature_as_png_data_url(app, create_user, login_as):
    user = create_user("Sign", "Drawer")
    data_url = "data:image/png;base64," + base64.b64encode(make_png_bytes()).decode()

    with app.test_client() as client:
        login_as(client, user)
        response = draw_signature(client, data_url)
        assert response.status_code == 302

        served = client.get(f"/accounts/{user.id}/signature")

    assert served.status_code == 200
    assert served.mimetype == "image/png"
    assert served.data[:8] == b"\x89PNG\r\n\x1a\n"


def test_non_image_signature_is_refused_and_nothing_stored(app, create_user, login_as):
    user = create_user("Sign", "Badfile")

    with app.test_client() as client:
        login_as(client, user)
        response = upload_signature(client, b"definitely not an image")
        followed = client.get(response.headers["Location"])
        bad_draw = draw_signature(client, "data:image/png;base64,bm90IGFuIGltYWdl")
        served = client.get(f"/accounts/{user.id}/signature")

    assert "ไม่ใช่รูปภาพ" in followed.data.decode()
    assert bad_draw.status_code == 302
    assert served.status_code == 404


def test_user_can_remove_signature(app, create_user, login_as):
    user = create_user("Sign", "Remover")

    with app.test_client() as client:
        login_as(client, user)
        upload_signature(client, make_png_bytes())
        assert client.get(f"/accounts/{user.id}/signature").status_code == 200

        response = client.post("/accounts/signature/remove")
        served = client.get(f"/accounts/{user.id}/signature")

    assert response.status_code == 302
    assert served.status_code == 404


from test_car_reservation import (  # noqa: E402  ใช้ world + helper ของระบบจองรถซ้ำ
    approve_url,
    detail_url,
    mock_redis_queue,  # noqa: F401
    step_data,
    world,  # noqa: F401
)


def test_reservation_detail_does_not_show_approver_signatures(world):
    car_application = world.submit_domestic_request()
    upload_signature_as(world, world.supervisor)
    response = world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )
    assert response.status_code == 302

    html = world.client_for(world.requester).get(detail_url(world, car_application)).get_data(as_text=True)
    assert f"/accounts/{world.supervisor.id}/signature" not in html


def upload_signature_as(world, user):
    upload_signature(world.client_for(user), make_png_bytes())


def test_printed_papers_keep_the_signatures_from_when_people_signed(world):
    from kampan import models, utils

    upload_signature(world.client_for(world.requester), make_png_bytes(color=(1, 1, 1)))
    car_application = world.submit_domestic_request()
    upload_signature(world.client_for(world.supervisor), make_png_bytes(color=(2, 2, 2)))
    world.client_for(world.supervisor).post(
        approve_url(world, car_application), data=step_data(world, "supervisor")
    )
    signed_requester = models.User.objects.get(id=world.requester.id).signature.read()
    signed_supervisor = models.User.objects.get(id=world.supervisor.id).signature.read()

    upload_signature(world.client_for(world.requester), make_png_bytes(color=(9, 9, 9)))
    upload_signature(world.client_for(world.supervisor), make_png_bytes(color=(8, 8, 8)))

    car_application.reload()
    paper = utils.car_reservation_paper
    assert paper.build_context(car_application)["requester_signature"] == signed_requester
    assert paper.approved_signers(car_application)["supervisor"].signature == signed_supervisor
