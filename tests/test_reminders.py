"""ระบบเตือน MA (#28, #29)

- ``due_reminders(today)``: reminder ที่ถึงกำหนดแล้วและยังไม่เคยส่ง (อ่าน Mongo อย่างเดียว)
- ``send_reminder_job``: งานส่งอีเมล 1 reminder (mock PSUSMTP)
- controller tick: สร้าง ReminderLog queued แล้ว enqueue (mock queue)
"""

import datetime

import pytest

from kampan.utils.date_utils import parse_thai_date


@pytest.mark.parametrize(
    "text, expected",
    [
        ("28/05/2570", datetime.date(2027, 5, 28)),
        ("1/4/2571", datetime.date(2028, 4, 1)),
        (" 29/02/2571 ", datetime.date(2028, 2, 29)),
    ],
)
def test_parse_thai_date_converts_buddhist_year(text, expected):
    assert parse_thai_date(text) == expected


@pytest.mark.parametrize("text", ["30/02/2570", "28/05/2027", "2570-05-28", "", "abc", "32/01/2570", "28/13/2570"])
def test_parse_thai_date_rejects_invalid(text):
    with pytest.raises(ValueError):
        parse_thai_date(text)


# ---------------------------------------------------------------------------
# due_reminders
# ---------------------------------------------------------------------------

from decimal import Decimal  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from kampan import models  # noqa: E402
from kampan.utils.reminders import due_reminders  # noqa: E402


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org):
    org = create_org("[TEST] Org")
    alice = create_user("Alice", "Reminder")
    bob = create_user("Bob", "Reminder")
    role_alice = assign_user_to_org(alice, org, roles=["staff"])
    role_bob = assign_user_to_org(bob, org, roles=["staff"])
    # clean_db ลบ collection (และ index) ทุกเทสต์ แต่ mongoengine cache collection ไว้ จึงสร้าง index ใหม่เอง
    models.ReminderLog.ensure_indexes()
    return SimpleNamespace(org=org, alice=alice, bob=bob, role_alice=role_alice, role_bob=role_bob)


def _item(world, name="[TEST] Microsoft 365", end=datetime.date(2027, 5, 31), installments=None, **fields):
    end_datetime = datetime.datetime.combine(end, datetime.time.min)
    fields.setdefault("responsible_by", [world.role_alice])
    # เตือนจ่ายงวดมีเฉพาะรายการที่แบ่งจ่ายเป็นงวด (installment_mode) ที่เหลือไม่มีการจ่าย
    fields.setdefault("installment_mode", True)
    return models.ProcurementItem(
        name=name,
        category="software",
        amount=Decimal(fields.pop("amount", "100.00")),
        start_date=end_datetime - datetime.timedelta(days=365),
        end_date=end_datetime,
        installments=installments or [models.Installment(due_date=end_datetime, paid_date=end_datetime)],
        **fields,
    )


def _ma(world, *items, status="active"):
    items = list(items) or [_item(world)]
    procurement = models.Procurement(
        psu_disbursement_number="12345/2569",
        name="[TEST] MA",
        company="[TEST] Vendor",
        organization=world.org,
        status=status,
        total_amount=sum((item.amount for item in items), Decimal("0")),
    )
    procurement.save_with_items(items)
    return procurement


def _triggers(today, kind=None):
    return sorted(
        (reminder.kind, reminder.trigger_date, reminder.offset)
        for reminder in due_reminders(today)
        if kind is None or reminder.kind == kind
    )


def test_default_expiry_offsets_fire_on_calendar_month_dates(world):
    _ma(world)  # end_date 31/05/2570, ค่าเริ่มต้น 3, 2, 1 เดือน, 15, 7 วัน

    assert _triggers(datetime.date(2027, 2, 27)) == []
    assert _triggers(datetime.date(2027, 2, 28)) == [("expiry", datetime.date(2027, 2, 28), "3m")]
    assert _triggers(datetime.date(2027, 3, 31)) == [("expiry", datetime.date(2027, 3, 31), "2m")]
    assert _triggers(datetime.date(2027, 4, 30)) == [("expiry", datetime.date(2027, 4, 30), "1m")]
    assert _triggers(datetime.date(2027, 5, 16)) == [("expiry", datetime.date(2027, 5, 16), "15d")]
    assert _triggers(datetime.date(2027, 5, 24)) == [("expiry", datetime.date(2027, 5, 24), "7d")]
    assert _triggers(datetime.date(2027, 5, 31)) == [("expiry", datetime.date(2027, 5, 31), "due")]


def _log(world, reminder_item, kind, trigger, status="sent", **fields):
    return models.ReminderLog(
        organization=world.org,
        procurement=reminder_item.procurement,
        item=reminder_item,
        kind=kind,
        trigger_date=datetime.datetime.combine(trigger, datetime.time.min),
        status=status,
        **fields,
    ).save()


def test_outage_collapses_to_latest_due_trigger(world):
    _ma(world)

    # controller ล่มตั้งแต่ก่อน trigger 3 เดือน จนเลย trigger 2 เดือน: ได้ฉบับเดียว (2 เดือน)
    assert _triggers(datetime.date(2027, 4, 5)) == [("expiry", datetime.date(2027, 3, 31), "2m")]


@pytest.mark.parametrize("status", ["queued", "sent", "failed"])
def test_logged_trigger_is_not_returned_again(world, status):
    procurement = _ma(world)
    item = procurement.get_items()[0]
    _log(world, item, "expiry", datetime.date(2027, 3, 31), status=status)

    assert _triggers(datetime.date(2027, 3, 31)) == []
    assert _triggers(datetime.date(2027, 4, 29)) == []
    assert _triggers(datetime.date(2027, 4, 30)) == [("expiry", datetime.date(2027, 4, 30), "1m")]


def test_manual_log_does_not_count_as_sent(world):
    procurement = _ma(world)
    item = procurement.get_items()[0]
    _log(world, item, "manual", datetime.date(2027, 3, 31), status="manual")

    assert _triggers(datetime.date(2027, 3, 31)) == [("expiry", datetime.date(2027, 3, 31), "2m")]


def test_no_weekly_repeat_after_end_date(world):
    procurement = _ma(world)
    item = procurement.get_items()[0]
    _log(world, item, "expiry", datetime.date(2027, 5, 31))

    for days in (1, 7, 14, 60):
        assert _triggers(datetime.date(2027, 5, 31) + datetime.timedelta(days=days)) == []


def test_unchecked_offsets_do_not_fire(world):
    _ma(world, _item(world, expiry_reminder_offsets=["1m"]))

    assert _triggers(datetime.date(2027, 2, 28)) == []
    assert _triggers(datetime.date(2027, 3, 31)) == []
    assert _triggers(datetime.date(2027, 5, 7)) == [("expiry", datetime.date(2027, 4, 30), "1m")]
    assert _triggers(datetime.date(2027, 5, 16)) == []


def test_custom_offset_days_fire_before_end_date(world):
    _ma(world, _item(world, expiry_reminder_offsets=[], reminder_offsets_days=[45, 10]))

    assert _triggers(datetime.date(2027, 4, 15)) == []
    assert _triggers(datetime.date(2027, 4, 16)) == [("expiry", datetime.date(2027, 4, 16), "45")]
    assert _triggers(datetime.date(2027, 5, 21)) == [("expiry", datetime.date(2027, 5, 21), "10")]


def test_changing_offset_after_send_does_not_resend(world):
    procurement = _ma(world, _item(world, expiry_reminder_offsets=[], reminder_offsets_days=[60]))
    item = procurement.get_items()[0]
    _log(world, item, "expiry", datetime.date(2027, 4, 1), offset="60")
    item.reminder_offsets_days = [61]
    item.save()

    assert _triggers(datetime.date(2027, 4, 2)) == []


def test_custom_dates_each_fire_once(world):
    dates = [datetime.date(2027, 5, 28), datetime.date(2027, 10, 18), datetime.date(2028, 4, 10)]
    procurement = _ma(
        world,
        _item(
            world,
            end=datetime.date(2028, 12, 31),
            expiry_reminder_offsets=[],
            custom_reminder_dates=[datetime.datetime.combine(day, datetime.time.min) for day in dates],
        ),
    )
    item = procurement.get_items()[0]

    for day in dates:
        assert _triggers(day, kind="custom") == [("custom", day, "date")]
        _log(world, item, "custom", day)
        assert _triggers(day, kind="custom") == []


def test_custom_date_older_than_seven_days_is_skipped(world):
    day = datetime.date(2027, 5, 28)
    _ma(world, _item(world, end=datetime.date(2028, 12, 31), custom_reminder_dates=[datetime.datetime(2027, 5, 28)]))

    assert _triggers(day + datetime.timedelta(days=7), kind="custom") == [("custom", day, "date")]
    assert _triggers(day + datetime.timedelta(days=8), kind="custom") == []


def test_activation_reminder_on_end_date_only_when_required(world):
    _ma(
        world,
        _item(world, name="[TEST] ต้อง activate", requires_activation=True, expiry_reminder_offsets=[]),
        _item(world, name="[TEST] ไม่ต้อง activate", expiry_reminder_offsets=[]),
    )

    assert _triggers(datetime.date(2027, 5, 30), kind="activation") == []
    reminders = [r for r in due_reminders(datetime.date(2027, 5, 31)) if r.kind == "activation"]
    assert [(r.item.name, r.trigger_date) for r in reminders] == [("[TEST] ต้อง activate", datetime.date(2027, 5, 31))]


@pytest.mark.parametrize("status", ["disactive", "renewed"])
def test_stopped_ma_gets_no_reminders(world, status):
    _ma(
        world,
        _item(
            world,
            requires_activation=True,
            custom_reminder_dates=[datetime.datetime(2027, 5, 31)],
            installments=[models.Installment(due_date=datetime.datetime(2027, 5, 31))],
        ),
        status=status,
    )

    assert due_reminders(datetime.date(2027, 5, 31)) == []


def _payment_item(world, *installments, **fields):
    return _item(
        world,
        end=datetime.date(2028, 12, 31),
        expiry_reminder_offsets=[],
        installments=list(installments),
        **fields,
    )


def test_payment_reminders_per_unpaid_installment(world):
    _ma(
        world,
        _payment_item(
            world,
            models.Installment(due_date=datetime.datetime(2027, 3, 15)),
            models.Installment(due_date=datetime.datetime(2027, 6, 15)),
            payment_reminder_offsets=["7d"],
        ),
    )

    assert _triggers(datetime.date(2027, 2, 15), kind="payment") == []  # ไม่มีเตือน 1 เดือน / 3 เดือนแล้ว
    assert [(r.trigger_date, r.offset, r.installment_index) for r in due_reminders(datetime.date(2027, 3, 8))] == [
        (datetime.date(2027, 3, 8), "7d", 1)
    ]
    assert _triggers(datetime.date(2027, 3, 15), kind="payment") == [("payment", datetime.date(2027, 3, 15), "due")]
    assert _triggers(datetime.date(2027, 6, 15), kind="payment") == [("payment", datetime.date(2027, 6, 15), "due")]


def test_default_payment_reminder_is_due_date_only(world):
    _ma(world, _payment_item(world, models.Installment(due_date=datetime.datetime(2027, 3, 15))))

    assert _triggers(datetime.date(2027, 3, 8), kind="payment") == []
    assert _triggers(datetime.date(2027, 3, 15), kind="payment") == [("payment", datetime.date(2027, 3, 15), "due")]


def test_item_without_installment_mode_gets_no_payment_reminders_but_expiry_stays(world):
    _ma(
        world,
        _item(
            world,
            installment_mode=False,
            installments=[models.Installment(due_date=datetime.datetime(2027, 5, 31))],
        ),
    )

    assert _triggers(datetime.date(2027, 5, 31), kind="payment") == []
    assert _triggers(datetime.date(2027, 5, 31), kind="expiry") == [("expiry", datetime.date(2027, 5, 31), "due")]


def test_paid_installment_stops_payment_reminders(world):
    _ma(
        world,
        _payment_item(
            world,
            models.Installment(due_date=datetime.datetime(2027, 3, 15), paid_date=datetime.datetime(2027, 3, 1)),
        ),
    )

    assert _triggers(datetime.date(2027, 3, 15), kind="payment") == []


def test_payment_offsets_are_separate_from_expiry_offsets(world):
    _ma(
        world,
        _payment_item(world, models.Installment(due_date=datetime.datetime(2027, 3, 15)), payment_reminder_offsets=["5d"]),
    )

    assert _triggers(datetime.date(2027, 3, 8), kind="payment") == []
    assert _triggers(datetime.date(2027, 3, 10), kind="payment") == [("payment", datetime.date(2027, 3, 10), "5d")]


def test_legacy_payment_offsets_are_ignored_when_sending(world):
    _ma(
        world,
        _payment_item(
            world, models.Installment(due_date=datetime.datetime(2027, 3, 15)), payment_reminder_offsets=["15d", "1m"]
        ),
    )

    assert _triggers(datetime.date(2027, 2, 28), kind="payment") == []
    assert _triggers(datetime.date(2027, 2, 15), kind="payment") == []
    assert _triggers(datetime.date(2027, 3, 15), kind="payment") == [("payment", datetime.date(2027, 3, 15), "due")]


def test_payment_log_of_one_installment_does_not_block_another(world):
    procurement = _ma(
        world,
        _payment_item(
            world,
            models.Installment(due_date=datetime.datetime(2027, 3, 15)),
            models.Installment(due_date=datetime.datetime(2027, 3, 15)),
        ),
    )
    item = procurement.get_items()[0]
    first = item.get_sorted_installments()[0]
    _log(world, item, "payment", datetime.date(2027, 3, 15), installment_id=first._id)

    reminders = [r for r in due_reminders(datetime.date(2027, 3, 15)) if r.kind == "payment"]
    assert [r.installment_id for r in reminders] == [item.get_sorted_installments()[1]._id]


def test_recipients_are_responsible_of_that_item_only(world):
    world.role_bob.email = "bob-member@test.com"
    world.role_bob.user = None
    world.role_bob.save()
    _ma(
        world,
        _item(world, name="[TEST] A", responsible_by=[world.role_alice, world.role_alice]),
        _item(world, name="[TEST] B", responsible_by=[world.role_bob]),
        _item(world, name="[TEST] C", responsible_by=[]),
    )

    reminders = due_reminders(datetime.date(2027, 5, 31))
    assert sorted((r.item.name, r.recipients) for r in reminders) == [
        ("[TEST] A", ["alice@test.com"]),
        ("[TEST] B", ["bob-member@test.com"]),
        ("[TEST] C", []),
    ]


def test_reminder_dedupe_key_identifies_item_kind_installment_and_date(world):
    procurement = _ma(world, _payment_item(world, models.Installment(due_date=datetime.datetime(2027, 3, 15))))
    item = procurement.get_items()[0]
    installment = item.installments[0]

    (reminder,) = due_reminders(datetime.date(2027, 3, 15))

    assert reminder.dedupe_key == f"{item.id}:payment:{installment._id}:2027-03-15"


# ---------------------------------------------------------------------------
# ReminderLog dedupe + controller tick (queue mocked)
# ---------------------------------------------------------------------------

import mongoengine as me  # noqa: E402

from kampan.controllers.reminder_scheduler import enqueue_due_reminders  # noqa: E402
from kampan.utils import ma_send_emails  # noqa: E402


class FakeQueue:
    def __init__(self, fail=False):
        self.jobs = []
        self.fail = fail

    def enqueue(self, func, args=(), **kwargs):
        if self.fail:
            raise ConnectionError("redis down")
        self.jobs.append((func, tuple(args)))
        return SimpleNamespace(id=f"job-{len(self.jobs)}")


SETTINGS = {"KAMPAN_HOST_URL": "https://kampan.test"}


def test_dedupe_key_is_unique_but_manual_logs_without_key_can_repeat(world):
    item = _ma(world).get_items()[0]
    _log(world, item, "expiry", datetime.date(2027, 5, 31), dedupe_key="k1")
    with pytest.raises(me.NotUniqueError):
        _log(world, item, "expiry", datetime.date(2027, 5, 31), dedupe_key="k1")

    _log(world, item, "manual", datetime.date(2027, 5, 31), status="manual", note="โทรแจ้ง")
    _log(world, item, "manual", datetime.date(2027, 5, 31), status="manual", note="โทรอีกรอบ")
    assert models.ReminderLog.objects(kind="manual").count() == 2


def test_tick_creates_queued_log_and_enqueues_job_with_log_id(world):
    procurement = _ma(world)
    queue = FakeQueue()

    enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, queue)

    log = models.ReminderLog.objects.get()
    assert (log.kind, log.status, log.offset) == ("expiry", "queued", "due")
    assert log.trigger_date == datetime.datetime(2027, 5, 31)
    assert log.organization.id == world.org.id and log.procurement.id == procurement.id
    assert log.recipients == ["alice@test.com"]
    assert log.dedupe_key
    assert queue.jobs == [(ma_send_emails.send_reminder_job, (str(log.id), SETTINGS))]


def test_tick_run_twice_same_day_creates_no_second_log(world):
    _ma(world)
    queue = FakeQueue()

    enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, queue)
    enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, queue)

    assert models.ReminderLog.objects.count() == 1
    assert len(queue.jobs) == 1


def test_tick_skips_reminder_when_log_with_same_key_appears_concurrently(world, monkeypatch):
    """controller 2 ตัวรันพร้อมกัน: อีกตัวสร้าง log ไปก่อนระหว่างที่ตัวนี้คำนวณ reminder"""
    _ma(world)
    from kampan.controllers import reminder_scheduler

    reminders = due_reminders(datetime.date(2027, 5, 31))
    _log(world, reminders[0].item, "expiry", datetime.date(2027, 5, 31), status="queued", dedupe_key=reminders[0].dedupe_key)
    monkeypatch.setattr(reminder_scheduler, "due_reminders", lambda today: reminders)
    queue = FakeQueue()

    enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, queue)

    assert models.ReminderLog.objects.count() == 1
    assert queue.jobs == []


def test_tick_marks_log_failed_when_enqueue_fails(world):
    _ma(world)

    enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, FakeQueue(fail=True))

    log = models.ReminderLog.objects.get()
    assert log.status == "failed"
    # ข้อความดิบของ exception (อาจมี host / รหัสผ่านของ Redis) ไม่เก็บใน log ที่ผู้ใช้เห็น
    assert log.error == "เข้าคิวส่งอีเมลไม่สำเร็จ"


# ---------------------------------------------------------------------------
# send_reminder_job (PSUSMTP mocked)
# ---------------------------------------------------------------------------


class FakeSMTP:
    instances = []
    login_ok = True
    failing = set()
    raise_on_send = None

    def __init__(self, settings):
        self.sent = []
        self.quit_called = False
        FakeSMTP.instances.append(self)

    def login(self):
        return FakeSMTP.login_ok

    def send_email(self, receiver, subject, body, html=False, steps=None):
        if FakeSMTP.raise_on_send:
            raise FakeSMTP.raise_on_send
        self.sent.append((receiver, subject, body))
        return receiver not in FakeSMTP.failing

    def quit(self):
        self.quit_called = True


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.login_ok = True
    FakeSMTP.failing = set()
    FakeSMTP.raise_on_send = None
    monkeypatch.setattr(ma_send_emails, "PSUSMTP", FakeSMTP)
    return FakeSMTP


def _queued_log(world, today, **item_fields):
    item_fields.setdefault("responsible_by", [world.role_alice, world.role_bob])
    _ma(world, _item(world, **item_fields))
    (log,) = enqueue_due_reminders(today, SETTINGS, FakeQueue())
    # วันส่งนับจาก created_date ของ log จึงตรึงให้เป็นวันที่รอบเตือนในเทสต์ ไม่ผูกกับวันที่จริงของเครื่อง
    log.created_date = datetime.datetime.combine(today, datetime.time(0, 10))
    log.save()
    return log


def test_job_sends_one_email_per_recipient_and_marks_sent(world, smtp):
    log = _queued_log(world, datetime.date(2027, 2, 28), reminder_kind="license")

    assert ma_send_emails.send_reminder_job(str(log.id), SETTINGS) is True

    log.reload()
    assert log.status == "sent" and log.sent_date and not log.error
    (server,) = smtp.instances
    assert [receiver for receiver, _, _ in server.sent] == ["alice@test.com", "bob@test.com"]
    receiver, subject, body = server.sent[0]
    assert subject == "[แจ้งเตือน] หมดอายุใน 90 วัน [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"
    assert "License" in body and "31 พฤษภาคม 2570" in body
    assert f"https://kampan.test/procurement/payment/{log.procurement.id}?organization_id={world.org.id}" in body
    assert server.quit_called


def test_job_partial_failure_marks_failed_with_recipient(world, smtp):
    smtp.failing = {"bob@test.com"}
    log = _queued_log(world, datetime.date(2027, 2, 28))

    assert ma_send_emails.send_reminder_job(str(log.id), SETTINGS) is False

    log.reload()
    assert log.status == "failed"
    assert "bob@test.com" in log.error and "alice@test.com" not in log.error


def test_job_login_failure_marks_failed(world, smtp):
    smtp.login_ok = False
    log = _queued_log(world, datetime.date(2027, 2, 28))

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    log.reload()
    assert log.status == "failed" and "SMTP" in log.error


def test_job_without_recipients_marks_failed(world, smtp):
    log = _queued_log(world, datetime.date(2027, 2, 28), responsible_by=[])

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    log.reload()
    assert log.status == "failed" and log.error == "ไม่มีผู้รับ"
    assert smtp.instances == []


def test_job_exception_never_leaves_log_queued(world, smtp, caplog):
    smtp.raise_on_send = RuntimeError("smtp exploded")
    log = _queued_log(world, datetime.date(2027, 2, 28))

    assert ma_send_emails.send_reminder_job(str(log.id), SETTINGS) is False

    log.reload()
    # ข้อความดิบของ exception ไปอยู่ใน log ของ worker เท่านั้น ไม่เก็บใน ReminderLog ที่แสดงบนหน้าเว็บ
    assert log.status == "failed" and log.error == "ส่งอีเมลไม่สำเร็จ"
    assert "smtp exploded" in caplog.text


def test_job_ignores_log_that_is_not_queued(world, smtp):
    log = _queued_log(world, datetime.date(2027, 2, 28))
    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    # job ซ้ำ (เช่น RQ retry) ต้องไม่ส่งซ้ำ
    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    assert len(smtp.instances) == 1


@pytest.mark.parametrize(
    "today, fields, expected_subject",
    [
        (datetime.date(2027, 5, 31), {}, "[แจ้งเตือน] ครบกำหนดหมดอายุวันนี้ [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"),
        (
            datetime.date(2027, 4, 16),
            {"expiry_reminder_offsets": [], "reminder_offsets_days": [45]},
            "[แจ้งเตือน] หมดอายุใน 45 วัน [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)",
        ),
        (
            datetime.date(2027, 4, 30),
            {"expiry_reminder_offsets": [], "installments": [models.Installment(due_date=datetime.datetime(2027, 4, 30))]},
            "[แจ้งเตือน] ครบกำหนดจ่ายงวดที่ 1 วันนี้ [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)",
        ),
        (
            datetime.date(2027, 4, 23),
            {
                "expiry_reminder_offsets": [],
                "payment_reminder_offsets": ["7d"],
                "installments": [models.Installment(due_date=datetime.datetime(2027, 4, 30))],
            },
            "[แจ้งเตือน] จ่ายงวดที่ 1 ใน 7 วัน [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)",
        ),
        (
            datetime.date(2027, 1, 10),
            {"expiry_reminder_offsets": [], "custom_reminder_dates": [datetime.datetime(2027, 1, 10)]},
            "[แจ้งเตือน] เตือนตามวันที่กำหนด [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)",
        ),
    ],
)
def test_job_subject_by_kind(world, smtp, today, fields, expected_subject):
    log = _queued_log(world, today, **fields)

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    assert smtp.instances[0].sent[0][1] == expected_subject


def test_job_activation_subject(world, smtp):
    _ma(world, _item(world, requires_activation=True, expiry_reminder_offsets=[]))
    logs = enqueue_due_reminders(datetime.date(2027, 5, 31), SETTINGS, FakeQueue())
    log = next(log for log in logs if log.kind == "activation")

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    expected = "[แจ้งเตือน] ครบกำหนด activate วันนี้ [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"
    assert smtp.instances[0].sent[0][1] == expected


def test_inactive_responsible_member_gets_no_email(world):
    world.role_bob.status = "disactive"
    world.role_bob.save()
    _ma(world, _item(world, responsible_by=[world.role_alice, world.role_bob]))

    (reminder,) = due_reminders(datetime.date(2027, 5, 31))

    assert reminder.recipients == ["alice@test.com"]


# ---------------------------------------------------------------------------
# trigger เก่าเกิน 7 วันไม่ส่ง + ข้อความจำนวนวันนับจากวันที่ส่ง
# ---------------------------------------------------------------------------

from dateutil.relativedelta import relativedelta  # noqa: E402


def _monthly_installments(first_due: datetime.date, count: int) -> list:
    first = datetime.datetime.combine(first_due, datetime.time.min)
    return [models.Installment(due_date=first + relativedelta(months=n)) for n in range(count)]


def test_imported_ma_with_past_unpaid_installments_reminds_only_within_seven_days(world):
    # นำเข้า MA ที่มี 12 งวดค้างจ่าย (15/02/2569 – 15/01/2570) รอบแรกต้องไม่ยิงเมลย้อนหลังทุกงวด
    _ma(world, _payment_item(world, *_monthly_installments(datetime.date(2026, 2, 15), 12)))

    logs = enqueue_due_reminders(datetime.date(2027, 1, 20), SETTINGS, FakeQueue())

    assert [(log.kind, log.trigger_date, log.offset, log.installment_index) for log in logs] == [
        ("payment", datetime.datetime(2027, 1, 15), "due", 12)
    ]


def test_expiry_and_activation_older_than_seven_days_are_skipped(world):
    _ma(world, _item(world, requires_activation=True))  # end_date 31/05/2570

    assert _triggers(datetime.date(2027, 6, 7)) == [
        ("activation", datetime.date(2027, 5, 31), "due"),
        ("expiry", datetime.date(2027, 5, 31), "due"),
    ]
    assert _triggers(datetime.date(2027, 6, 8)) == []


def _sent_subject_and_body(smtp):
    _, subject, body = smtp.instances[0].sent[0]
    return subject, body


def test_late_offset_reminder_states_real_days_left(world, smtp):
    # MA สร้างตอนเหลือ 10 วัน: trigger ล่าสุดที่ถึงคือ 15 วัน แต่ข้อความต้องบอกว่าเหลือ 10 วัน
    log = _queued_log(world, datetime.date(2027, 5, 21))
    assert log.offset == "15d"

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    subject, body = _sent_subject_and_body(smtp)
    assert subject == "[แจ้งเตือน] หมดอายุใน 10 วัน [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"
    assert "(อีก 10 วัน)" in body and "15 วัน" not in body


def test_late_due_date_reminder_says_how_many_days_ago(world, smtp):
    log = _queued_log(world, datetime.date(2027, 6, 3))

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    subject, body = _sent_subject_and_body(smtp)
    assert subject == "[แจ้งเตือน] เลยกำหนดหมดอายุมาแล้ว 3 วัน [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"
    assert "(เลยมาแล้ว 3 วัน)" in body and "(วันนี้)" not in body


def test_payment_due_today_says_today(world, smtp):
    log = _queued_log(
        world,
        datetime.date(2027, 4, 30),
        expiry_reminder_offsets=[],
        installments=[models.Installment(due_date=datetime.datetime(2027, 4, 30))],
    )

    ma_send_emails.send_reminder_job(str(log.id), SETTINGS)

    subject, body = _sent_subject_and_body(smtp)
    assert subject == "[แจ้งเตือน] ครบกำหนดจ่ายงวดที่ 1 วันนี้ [TEST] Microsoft 365 (ม.อ.เบิกจ่าย 12345/2569)"
    assert "(วันนี้)" in body


def test_parent_with_sub_contracts_is_not_reminded_twice(world):
    """สัญญาหลักที่แยกสัญญาย่อยแล้วเตือนจากสัญญาย่อยเท่านั้น (รายการย่อยซ้ำกัน ห้ามได้เมลซ้ำ)"""
    parent = _ma(world, _item(world, name="[TEST] A"), _item(world, name="[TEST] B"))
    for name in ("[TEST] A", "[TEST] B"):
        child = models.Procurement(
            psu_disbursement_number="12345/2569",
            name=name,
            company="[TEST] Vendor",
            organization=world.org,
            status="active",
            total_amount=Decimal("100.00"),
            parent_procurement=parent,
        )
        child.save_with_items([_item(world, name=name)])

    reminders = [r for r in due_reminders(datetime.date(2027, 2, 28)) if r.kind == "expiry"]

    assert sorted(r.item.name for r in reminders) == ["[TEST] A", "[TEST] B"]
    assert all(r.item.procurement.parent_procurement is not None for r in reminders)
