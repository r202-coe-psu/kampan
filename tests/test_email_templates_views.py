import datetime
import re
from types import SimpleNamespace

import pytest
from flask import url_for

from kampan import models
from kampan.models.email_templates import EMAIL_TEMPLATE_VARIABLES, EMAIL_TYPE
from kampan.utils import email_utils


def _person(name):
    return SimpleNamespace(get_name=lambda: name, email=f"{name}@test.com")


def _documented(email_type):
    return {name for name, _ in EMAIL_TEMPLATE_VARIABLES[email_type]}


NOW = datetime.datetime(2026, 11, 2, 9, 30)
ORGANIZATION = SimpleNamespace(name="Org")
DIVISION = SimpleNamespace(name="Div", description="desc", organization=ORGANIZATION)


def test_every_email_type_documents_its_variables():
    assert set(EMAIL_TEMPLATE_VARIABLES) == {value for value, _ in EMAIL_TYPE}


@pytest.mark.parametrize(
    "email_type", ["to endorser", "to supervisor supplier", "to admin"]
)
def test_order_variables_match_what_is_sent(email_type):
    order = SimpleNamespace(
        created_by=_person("creator"),
        updated_date=NOW,
        sent_item_date=NOW,
        description="objective",
    )
    sent = email_utils.get_endorser_text_format(
        DIVISION, _person("sender"), _person("endorser"), order, "http://x"
    )
    assert _documented(email_type) == set(sent)


def test_staff_variables_are_sent_without_approval_link():
    order = SimpleNamespace(
        created_by=_person("creator"), updated_date=NOW, sent_item_date=None, description=""
    )
    sent = email_utils.get_endorser_text_format(
        DIVISION, _person("sender"), _person("endorser"), order, ""
    )
    assert _documented("to staff") == set(sent) - {"endorsement_url"}


def test_lost_break_variables_match_what_is_sent():
    lost_break_item = SimpleNamespace(
        created_date=NOW,
        user=_person("reporter"),
        description="broken",
        item=SimpleNamespace(name="Pen"),
        quantity=2,
    )
    sent = email_utils.get_send_email_lost_break_text_format(
        ORGANIZATION, _person("sender"), _person("endorser"), lost_break_item, "http://x"
    )
    assert _documented("lost_break") == set(sent)


def test_car_application_variables_match_what_is_sent():
    car_application = SimpleNamespace(
        creator=_person("driver"),
        departure_datetime=NOW,
        request_reason="trip",
        car=SimpleNamespace(license_plate="กข 1234"),
    )
    sent = email_utils.get_car_application_text_format(
        DIVISION, _person("sender"), _person("endorser"), car_application, "http://x"
    )
    assert _documented("car_application") == set(sent)


@pytest.fixture
def email_setup(app, create_org, create_user, assign_user_to_org):
    org = create_org("Mail Org")
    other_org = create_org("Other Org")
    admin = create_user("Mailadmin", "Org")
    assign_user_to_org(admin, org, roles=["admin"])
    template = models.EmailTemplate(
        name="แจ้งผู้อนุมัติ",
        subject="ขออนุมัติ {{ order_creator }}",
        body="เรียน {{ endorser_name }}\nกรุณาอนุมัติ",
        type="lost_break",
        organization=org,
    ).save()
    foreign = models.EmailTemplate(
        name="ของอีกองค์กร", subject="s", body="b", organization=other_org
    ).save()
    return SimpleNamespace(org=org, admin=admin, template=template, foreign=foreign)


def _get(app, client, endpoint, **values):
    with app.test_request_context():
        url = url_for(endpoint, **values)
    return client.get(url)


def test_index_uses_icon_actions_with_tooltips(app, login_as, email_setup):
    s = email_setup
    with app.test_client() as client:
        login_as(client, s.admin)
        html = _get(app, client, "email_templates.index", organization_id=str(s.org.id)).get_data(as_text=True)

    tbody = html[html.index("<tbody>"):html.index("</tbody>")]
    for label in ("ดูรายละเอียด", "แก้ไข", "ลบ"):
        assert f'data-tip="{label}"' in tbody
    assert "ของอีกองค์กร" not in tbody
    # modal ต้องอยู่นอกตาราง ไม่งั้นรับ whitespace-nowrap ของคอลัมน์จัดการแล้วข้อความล้นกล่อง
    assert "<dialog" not in tbody
    assert 'class="toggle toggle-success toggle-sm"' in tbody
    assert "ph-star" not in html


def test_detail_shows_variables_of_its_type(app, login_as, email_setup):
    s = email_setup
    with app.test_client() as client:
        login_as(client, s.admin)
        html = _get(
            app, client, "email_templates.detail",
            organization_id=str(s.org.id), email_template_id=str(s.template.id),
        ).get_data(as_text=True)

    visible = re.search(r'data-email-type="lost_break" class="mt-4 "', html)
    assert visible, "panel ของประเภท lost_break ต้องไม่ถูกซ่อน"
    assert 'data-email-type="car_application" class="mt-4 hidden"' in html
    assert "{{ lost_break_item_name }}" in html
    assert "{{ user_name }}" not in html
    assert "เรียน {{ endorser_name }}" in html


def test_cannot_open_or_delete_another_organizations_template(app, login_as, email_setup):
    s = email_setup
    with app.test_client() as client:
        login_as(client, s.admin)
        detail = _get(
            app, client, "email_templates.detail",
            organization_id=str(s.org.id), email_template_id=str(s.foreign.id),
        )
        with app.test_request_context():
            delete_url = url_for(
                "email_templates.delete_email_template",
                organization_id=str(s.org.id), email_template_id=str(s.foreign.id),
            )
        deleted = client.post(delete_url)

    assert detail.status_code == 404
    assert deleted.status_code == 404
    assert models.EmailTemplate.objects(id=s.foreign.id).count() == 1
