import re

import pytest

from kampan import models


@pytest.fixture
def staff_client(app, create_org, create_user, assign_user_to_org, login_as):
    org = create_org(name="DIIS")
    staff = create_user("Staff", "User")
    assign_user_to_org(staff, org, roles=["staff"])
    return login_as(app.test_client(), staff), org


def _template(org, name, status="active"):
    step = models.car_form_templates.ApprovalStepDef(
        key="admin", label="ผู้จัดรถ", approver_type="role", role="admin", assigns_vehicle=True
    )
    return models.car_form_templates.CarFormTemplate(
        organization=org, name=name, status=status, steps=[step]
    ).save()


def _picker(html):
    return re.search(r'<dialog id="new-car-request-modal".*?</dialog>', html, re.S).group(0)


def _index(client, org, query=""):
    return client.get(f"/vehicle_lending/car_form_requests/?organization_id={org.id}{query}").get_data(as_text=True)


def test_the_request_list_offers_only_active_templates_in_the_picker(staff_client):
    client, org = staff_client
    active = _template(org, "ขอใช้รถในเมือง")
    _template(org, "ขอใช้รถต่างจังหวัด")
    _template(org, "แบบเก่า", status="disactive")

    html = _index(client, org)
    picker = _picker(html)

    assert f"/vehicle_lending/car_form_requests/new/{active.id}?organization_id={org.id}" in picker
    assert "ขอใช้รถต่างจังหวัด" in picker
    assert "แบบเก่า" not in picker
    assert "document.getElementById('new-car-request-modal').showModal()" in html


def test_a_single_template_skips_the_picker(staff_client):
    client, org = staff_client
    only = _template(org, "ขอใช้รถ")

    html = _index(client, org)

    assert f'window.location.href = "/vehicle_lending/car_form_requests/new/{only.id}?organization_id={org.id}"' in html


def test_the_picker_says_so_when_no_template_is_active(staff_client):
    client, org = staff_client

    assert "ยังไม่มีแบบฟอร์มที่เปิดใช้งาน" in _picker(_index(client, org))


def test_the_old_new_request_page_opens_the_picker_on_the_request_list(staff_client):
    client, org = staff_client

    resp = client.get(f"/vehicle_lending/car_form_requests/new?organization_id={org.id}")

    assert resp.status_code == 302
    assert "/vehicle_lending/car_form_requests/?" in resp.location
    assert "new=1" in resp.location
    assert "addEventListener('DOMContentLoaded', openNewCarRequest)" in _index(client, org, "&new=1")
    assert "addEventListener('DOMContentLoaded', openNewCarRequest)" not in _index(client, org)


def test_the_sidebar_has_one_request_menu(staff_client):
    client, org = staff_client

    html = _index(client, org)

    assert "ยื่นคำขอใช้รถ (template)" not in html
