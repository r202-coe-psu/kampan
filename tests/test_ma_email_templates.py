"""อีเมล MA ใช้ template ขององค์กรเท่านั้น (ชนิด ma_assigned / ma_expiry / ma_payment) ผ่าน Jinja sandbox"""

import datetime
from types import SimpleNamespace

import pytest

from kampan import models
from kampan.models.email_templates import EMAIL_TEMPLATE_VARIABLES
from kampan.utils import ma_email_templates, ma_send_emails

SETTINGS = {"KAMPAN_HOST_URL": "https://kampan.test"}


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, create_ma):
    org = create_org("[TEST] Org A")
    other_org = create_org("[TEST] Org B")
    admin = create_user("Admin", "Mail")
    role_admin = assign_user_to_org(admin, org, roles=["admin"])
    role_admin.first_name, role_admin.last_name = "Admin", "Mail"
    role_admin.save()
    ma = create_ma(org, user=admin, name="[TEST] MA เมล", responsible=[role_admin])
    item = ma.get_items()[0]
    return SimpleNamespace(org=org, other_org=other_org, admin=admin, role_admin=role_admin, ma=ma, item=item)


def _log(world, kind, **extra):
    today = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    values = dict(
        organization=world.org,
        procurement=world.ma,
        item=world.item,
        kind=kind,
        trigger_date=today,
        offset="due",
        recipients=["a@example.com"],
        status="queued",
        dedupe_key=f"{world.item.id}:{kind}:{extra.get('installment_index', '-')}",
        created_by=world.admin,
        created_date=today,
    )
    if kind == "payment":
        values.update(installment_id=world.item.installments[0]._id, installment_index=1)
    values.update(extra)
    return models.ReminderLog(**values).save()


def _template(org, email_type, subject, body, default=True):
    return models.EmailTemplate(
        organization=org, type=email_type, name="t", subject=subject, body=body, is_default=default
    ).save()


@pytest.mark.parametrize("kind", ["assigned", "expiry", "payment", "activation", "custom"])
def test_first_email_creates_the_default_template_in_the_organization(world, kind):
    assert models.EmailTemplate.objects(organization=world.org).count() == 0

    subject, body = ma_send_emails.build_reminder_email(_log(world, kind), SETTINGS)

    email_type = ma_email_templates.email_type_for(kind)
    created = models.EmailTemplate.objects.get(organization=world.org, type=email_type)
    assert created.is_default
    assert world.item.name in subject and "[TEST] MA เมล" in body
    assert f"https://kampan.test/procurement/payment/{world.ma.id}?organization_id={world.org.id}" in body


def test_organization_template_is_used_instead_of_any_builtin_text(world):
    _template(world.org, "ma_payment", "จ่ายงวด {{ item_name }} / {{ psu_number }}", "งวด {{ installment_index }} ครบ {{ due_date }} {{ days_text }}")

    subject, body = ma_send_emails.build_reminder_email(_log(world, "payment"), SETTINGS)

    assert subject == "จ่ายงวด [TEST] MA เมล / PSU-0001"
    assert body.startswith("งวด 1 ครบ ") and ("(วันนี้)" in body or "(อีก" in body)
    assert "เรียน ผู้รับผิดชอบ" not in body  # ไม่มีข้อความตายตัวของระบบแทรก


def test_template_of_another_organization_is_never_used(world):
    _template(world.other_org, "ma_assigned", "ขององค์กรอื่น", "ของ {{ organization_name }}")

    subject, _ = ma_send_emails.build_reminder_email(_log(world, "assigned"), SETTINGS)

    assert "ขององค์กรอื่น" not in subject
    assert models.EmailTemplate.objects(organization=world.org, type="ma_assigned").count() == 1


def test_no_default_template_means_failed_log_not_a_hardcoded_email(world):
    _template(world.org, "ma_expiry", "ไม่ใช่ตัวเริ่มต้น", "x", default=False)
    log = _log(world, "expiry")

    sent = ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    log.reload()
    assert sent is False
    assert log.status == "failed" and log.error == ma_email_templates.NO_TEMPLATE_ERROR


def test_other_types_do_not_borrow_each_others_template(world):
    _template(world.org, "ma_assigned", "assigned only", "x")

    subject, _ = ma_send_emails.build_reminder_email(_log(world, "expiry"), SETTINGS)

    assert subject != "assigned only"


def test_jinja_expressions_cannot_reach_internals(world):
    _template(world.org, "ma_assigned", "ok", "{{ ''.__class__.__mro__[1].__subclasses__() }}")
    log = _log(world, "assigned")

    with pytest.raises(ma_email_templates.MaEmailTemplateError):
        ma_send_emails.build_reminder_email(log, SETTINGS)
    assert ma_send_emails.send_reminder_job(str(log.id), SETTINGS) is False
    log.reload()
    assert log.status == "failed" and log.error == ma_email_templates.BAD_TEMPLATE_ERROR


def test_broken_template_syntax_fails_the_log_with_a_clear_message(world):
    _template(world.org, "ma_expiry", "{{ unclosed", "x")
    log = _log(world, "expiry")

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    log.reload()
    assert log.status == "failed" and log.error == ma_email_templates.BAD_TEMPLATE_ERROR


@pytest.mark.parametrize("kind", ["assigned", "expiry", "payment"])
def test_every_variable_listed_on_the_template_page_is_provided(world, kind):
    context = ma_send_emails.build_email_context(_log(world, kind), SETTINGS)

    email_type = ma_email_templates.email_type_for(kind)
    assert {name for name, _ in EMAIL_TEMPLATE_VARIABLES[email_type]} <= set(context)


def test_ma_types_are_listed_and_creatable_on_the_template_page(app, world, login_as):
    client = login_as(app.test_client(), world.admin)

    page = client.get(f"/email_templates/?organization_id={world.org.id}&system=procurement")
    created = client.post(
        f"/email_templates/create?organization_id={world.org.id}",
        data={"name": "[TEST] MA", "type": "ma_payment", "subject": "s {{ item_name }}", "body": "b", "is_default": "y"},
    )

    assert page.status_code == 200 and "ระบบ MA" in page.get_data(as_text=True)
    assert created.status_code == 302
    assert models.EmailTemplate.objects.get(organization=world.org, type="ma_payment").subject == "s {{ item_name }}"


def test_concurrent_default_creation_leaves_a_single_default(world, monkeypatch):
    """worker อีกตัวสร้าง default แทรกระหว่างตรวจกับบันทึก: ต้องเหลือตัวเดียวและทั้งสองฝั่งได้ตัวเดียวกัน"""
    real_save = models.EmailTemplate.save
    rival = {}

    def save_with_rival(self, *args, **kwargs):
        if not rival:
            rival["doc"] = real_save(
                models.EmailTemplate(organization=self.organization, type=self.type, is_default=True, **_FIELDS)
            )
        return real_save(self, *args, **kwargs)

    _FIELDS = {"name": "rival", "subject": "s", "body": "b"}
    monkeypatch.setattr(models.EmailTemplate, "save", save_with_rival)

    chosen = ma_email_templates.get_template(world.org, "ma_expiry")

    defaults = models.EmailTemplate.objects(organization=world.org, type="ma_expiry", is_default=True)
    assert defaults.count() == 1
    assert chosen.id == rival["doc"].id == defaults.first().id
