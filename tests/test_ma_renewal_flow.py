"""สถานะ 2 ชนิดของ MA และขั้นตอนขอ / อนุมัติต่ออายุ

- สถานะการใช้งาน (usage_status): คำนวณตอนบันทึก + controller รายวัน
- สถานะการต่ออายุ (status): รอตรวจสอบ → รอต่ออายุ (ผู้รับผิดชอบขอ renew / stop) → ต่ออายุแล้ว / ไม่ต่ออายุ (admin อนุมัติ)
- อีเมลแจ้งการมอบหมายผู้รับผิดชอบ 1 ฉบับต่อรายการ + สมาชิก และการหยุดส่งเมื่อ MA ปิดแล้ว
"""

import asyncio
import datetime
from decimal import Decimal

import pytest

from kampan import models
from kampan.controllers.procurement_status import ProcurementStatusUpdater
from kampan.models.procurement import compute_usage_status, normalize_renewal_status, renewal_status_statuses
from kampan.utils import ma_assignments, ma_send_emails
from kampan.utils.reminders import due_reminders
from test_ma_structure import (  # noqa: F401
    _create,
    _edit_form,
    _flashes,
    _item,
    _item_edit_url,
    _q,
    client_for,
    existing_ma,
    ma_form,
    world,
)

TODAY = datetime.date.today()


def _url(ma, action, world, org=None):
    return f"/procurement/requisitions/{ma.id}/{action}?{_q(org or world.org)}"


def _state(ma):
    ma = models.Procurement.objects.get(id=ma.id)
    return ma.status, ma.renewal_request


def _set(ma, status, request_value=None):
    models.Procurement.objects(id=ma.id).update(set__status=status, set__renewal_request=request_value)


# ---------------------------------------------------------------------------
# สถานะการใช้งาน
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "start, end, expected",
    [
        (TODAY + datetime.timedelta(days=1), TODAY + datetime.timedelta(days=30), "upcoming"),
        (TODAY, TODAY + datetime.timedelta(days=30), "in_use"),
        (TODAY - datetime.timedelta(days=30), TODAY, "in_use"),
        (TODAY - datetime.timedelta(days=30), TODAY - datetime.timedelta(days=1), "expired"),
        (None, None, None),
    ],
)
def test_compute_usage_status(start, end, expected):
    assert compute_usage_status(start, end, TODAY) == expected


def _ma_with_dates(world, create_ma, ranges, status="review"):
    items = [
        models.ProcurementItem(
            name=f"[TEST] รายการ {index}",
            category="software",
            amount=Decimal("100.00"),
            start_date=datetime.datetime.combine(start, datetime.time.min),
            end_date=datetime.datetime.combine(end, datetime.time.min),
            installment_mode=False,
        )
        for index, (start, end) in enumerate(ranges)
    ]
    return create_ma(world.org, user=world.admin, items=items, total_amount=str(100 * len(items)), status=status)


def test_usage_status_spans_earliest_start_to_latest_end_of_all_items(world, create_ma):
    day = datetime.timedelta(days=1)
    # รายการแรกหมดแล้ว แต่รายการที่สองยังไม่หมด = กำลังใช้งาน (ดูตั้งแต่เริ่มแรกสุดถึงสิ้นสุดท้ายสุด)
    in_use = _ma_with_dates(world, create_ma, [(TODAY - 60 * day, TODAY - day), (TODAY - 10 * day, TODAY + 20 * day)])
    upcoming = _ma_with_dates(world, create_ma, [(TODAY + 5 * day, TODAY + 40 * day), (TODAY + 9 * day, TODAY + 50 * day)])
    expired = _ma_with_dates(world, create_ma, [(TODAY - 90 * day, TODAY - 30 * day), (TODAY - 60 * day, TODAY - day)])

    assert [ma.usage_status for ma in (in_use, upcoming, expired)] == ["in_use", "upcoming", "expired"]
    stored = {ma.id: ma.usage_status for ma in models.Procurement.objects()}
    assert stored[expired.id] == "expired"


def test_draft_has_no_usage_status_and_gets_one_when_published(world, create_ma):
    draft = _ma_with_dates(world, create_ma, [(TODAY, TODAY + datetime.timedelta(days=30))], status="draft")
    assert draft.usage_status is None

    draft.status = "review"
    draft.save_with_items(draft.get_items())

    assert models.Procurement.objects.get(id=draft.id).usage_status == "in_use"


def test_daily_job_refreshes_usage_status_of_every_non_draft_ma_and_not_the_renewal_status(world, create_ma):
    day = datetime.timedelta(days=1)
    ma = _ma_with_dates(world, create_ma, [(TODAY - 30 * day, TODAY + 10 * day)])
    renewed = _ma_with_dates(world, create_ma, [(TODAY - 30 * day, TODAY + 10 * day)])
    draft = _ma_with_dates(world, create_ma, [(TODAY - 30 * day, TODAY + 10 * day)], status="draft")
    _set(renewed, "renewed")
    # เวลาผ่านไป: วันสิ้นสุดผ่านไปแล้วแต่ค่าที่เก็บยังเป็น in_use (controller ไม่ได้รัน)
    models.ProcurementItem.objects().update(set__end_date=datetime.datetime.now() - 2 * day)
    updater = ProcurementStatusUpdater.__new__(ProcurementStatusUpdater)
    before = models.Procurement.objects.get(id=ma.id).updated_date

    for procurement in (ma, renewed, draft):
        asyncio.run(updater.process_data({"procurement_id": procurement.id}))

    assert models.Procurement.objects.get(id=ma.id).usage_status == "expired"
    assert models.Procurement.objects.get(id=ma.id).status == "review"  # ไม่ย้ายเป็น pending เหมือนเดิม
    assert models.Procurement.objects.get(id=renewed.id).usage_status == "expired"  # ต่ออายุแล้วก็หมดอายุได้
    assert models.Procurement.objects.get(id=draft.id).usage_status is None
    assert models.Procurement.objects.get(id=ma.id).updated_date == before  # ไม่ทำให้ฟอร์มแก้ไขที่เปิดค้างชนกัน


def test_save_never_moves_renewal_status_by_expiry_window(world, create_ma):
    ma = _ma_with_dates(world, create_ma, [(TODAY - datetime.timedelta(days=300), TODAY + datetime.timedelta(days=5))])

    assert models.Procurement.objects.get(id=ma.id).status == "review"


def test_legacy_status_values_are_read_as_review_and_still_filter_and_render(world, client_for, create_ma):
    legacy = {status: create_ma(world.org, user=world.admin, name=f"[TEST] เดิม {status}", status=status, psu_disbursement_number=f"P-{status}") for status in ("active", "pending")}
    models.Procurement.objects(id=legacy["active"].id).update(set__status="active")
    assert normalize_renewal_status("active") == normalize_renewal_status("pending") == "review"
    assert set(renewal_status_statuses("review")) == {"review", "active", "pending"}
    client = client_for(world.admin)

    html = client.get(f"/procurement/products?renewal_status=review&{_q(world.org)}").get_data(as_text=True)
    detail = client.get(f"/procurement/payment/{legacy['pending'].id}?{_q(world.org)}").get_data(as_text=True)

    assert "[TEST] เดิม active" in html and "[TEST] เดิม pending" in html
    assert 'data-renewal-status="review"' in detail and "รอตรวจสอบ" in detail
    assert legacy["pending"].get_renewal_status_label() == "รอตรวจสอบ"


# ---------------------------------------------------------------------------
# ผู้รับผิดชอบกดขอ
# ---------------------------------------------------------------------------


def _request(client, ma, world, value, org=None):
    return client.post(_url(ma, "renewal-request", world, org), data={"request": value})


@pytest.mark.parametrize("value", ["renew", "stop"])
def test_responsible_request_moves_review_to_renewal_requested(world, client_for, existing_ma, value):
    response = _request(client_for(world.responsible), existing_ma, world, value)

    assert response.status_code == 302 and f"/procurement/payment/{existing_ma.id}" in response.headers["Location"]
    assert _state(existing_ma) == ("renewal-requested", value)
    assert models.Procurement.objects.get(id=existing_ma.id).last_updated_by.id == world.responsible.id


@pytest.mark.parametrize("who", ["admin", "creator", "head", "other_staff"])
def test_only_item_responsible_can_request(world, client_for, existing_ma, who):
    """admin / ผู้สร้างที่แก้ MA ได้ ก็กดขอแทนผู้รับผิดชอบไม่ได้"""
    _request(client_for(getattr(world, who)), existing_ma, world, "stop")

    assert _state(existing_ma) == ("review", None)


def test_request_from_other_org_is_404(world, client_for, existing_ma):
    response = _request(client_for(world.admin_b), existing_ma, world, "stop", org=world.other_org)

    assert response.status_code == 404
    assert _state(existing_ma) == ("review", None)


def test_responsible_of_the_other_org_cannot_request_even_with_a_forged_org_id(world, client_for, existing_ma):
    response = _request(client_for(world.responsible), existing_ma, world, "stop", org=world.other_org)

    assert response.status_code in (302, 404, 403)
    assert _state(existing_ma) == ("review", None)


@pytest.mark.parametrize("value", [None, "", "approve", "RENEW"])
def test_request_value_must_be_renew_or_stop(world, client_for, existing_ma, value):
    data = {} if value is None else {"request": value}

    client_for(world.responsible).post(_url(existing_ma, "renewal-request", world), data=data)

    assert _state(existing_ma) == ("review", None)


def test_request_is_post_only(world, client_for, existing_ma):
    assert client_for(world.responsible).get(_url(existing_ma, "renewal-request", world)).status_code == 405


def test_double_click_request_changes_nothing_the_second_time(world, client_for, existing_ma):
    client = client_for(world.responsible)

    _request(client, existing_ma, world, "renew")
    updated_after_first = models.Procurement.objects.get(id=existing_ma.id).updated_date
    second = _request(client, existing_ma, world, "renew")

    assert second.status_code == 302
    assert _state(existing_ma) == ("renewal-requested", "renew")
    assert models.Procurement.objects.get(id=existing_ma.id).updated_date == updated_after_first


def test_responsible_can_switch_request_until_admin_confirms(world, client_for, existing_ma):
    client = client_for(world.responsible)

    _request(client, existing_ma, world, "renew")
    _request(client, existing_ma, world, "stop")
    assert _state(existing_ma) == ("renewal-requested", "stop")
    _request(client, existing_ma, world, "renew")
    assert _state(existing_ma) == ("renewal-requested", "renew")


@pytest.mark.parametrize("confirmed", ["renewed", "disactive"])
def test_responsible_cannot_change_anything_after_admin_confirms(world, client_for, existing_ma, confirmed):
    _set(existing_ma, confirmed, "stop")
    client = client_for(world.responsible)

    for value in ("renew", "stop"):
        _request(client, existing_ma, world, value)
    edit = client.post(
        f"/procurement/products/{existing_ma.id}/edit?{_q(world.org)}", data=_edit_form(existing_ma, name="[TEST] แก้หลังยืนยัน")
    )
    detail = client.get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)

    assert _state(existing_ma) == (confirmed, "stop")
    assert edit.status_code == 302
    assert models.Procurement.objects.get(id=existing_ma.id).name == "[TEST] MA เดิม"
    for modal in ("request_renew_modal", "request_stop_modal"):
        assert f'id="{modal}"' not in detail
    assert f"/procurement/products/{existing_ma.id}/edit" not in detail


@pytest.mark.parametrize("who", ["responsible", "creator"])
def test_editors_cannot_edit_or_pay_a_confirmed_ma_but_admin_can(world, client_for, existing_ma, who):
    _set(existing_ma, "disactive", "stop")
    item = existing_ma.get_items()[0]
    pay = f"/procurement/payment/{existing_ma.id}/items/{item.id}/installments/{item.installments[0]._id}/pay?{_q(world.org)}"

    client_for(getattr(world, who)).post(pay, data={"paid_date": "2026-11-01", "payment_number": "PAY-LOCK"})
    assert models.ProcurementItem.objects.get(id=item.id).installments[0].paid_date is None

    client_for(world.admin).post(pay, data={"paid_date": "2026-11-01", "payment_number": "PAY-LOCK"})
    assert models.ProcurementItem.objects.get(id=item.id).installments[0].paid_date is not None


# ---------------------------------------------------------------------------
# admin อนุมัติ
# ---------------------------------------------------------------------------


def _approve_stop(client, ma, world, expected="stop"):
    data = {} if expected is None else {"expected_request": expected}
    return client.post(_url(ma, "non-renewal", world), data=data)


@pytest.mark.parametrize("who", ["responsible", "creator", "head", "other_staff"])
def test_only_admin_can_approve_stop(world, client_for, existing_ma, who):
    _set(existing_ma, "renewal-requested", "stop")

    _approve_stop(client_for(getattr(world, who)), existing_ma, world)

    assert _state(existing_ma) == ("renewal-requested", "stop")


def test_admin_approves_stop_only_after_the_request(world, client_for, existing_ma):
    client = client_for(world.admin)

    _approve_stop(client, existing_ma, world)  # ข้ามขั้นตอนขอไม่ได้
    assert _state(existing_ma) == ("review", None)

    _set(existing_ma, "renewal-requested", "renew")  # ขอต่ออายุ ไม่ใช่ขอไม่ต่ออายุ
    _approve_stop(client, existing_ma, world)
    assert _state(existing_ma) == ("renewal-requested", "renew")

    _set(existing_ma, "renewal-requested", "stop")
    _approve_stop(client, existing_ma, world)
    assert _state(existing_ma) == ("disactive", "stop")


def test_approve_stop_refused_when_the_request_changed_after_the_admin_opened_the_page(world, client_for, existing_ma):
    """admin เปิดหน้าตอนขอไม่ต่ออายุ (ฟอร์มส่ง expected_request=stop) แต่ผู้รับผิดชอบเปลี่ยนเป็นต่ออายุก่อนกด"""
    _set(existing_ma, "renewal-requested", "renew")
    client = client_for(world.admin)

    response = _approve_stop(client, existing_ma, world, expected="stop")

    assert response.status_code == 302
    assert _state(existing_ma) == ("renewal-requested", "renew")
    assert [category for category, _ in _flashes(client)] == ["error"]


def test_approve_stop_requires_the_expected_request_field(world, client_for, existing_ma):
    _set(existing_ma, "renewal-requested", "stop")

    _approve_stop(client_for(world.admin), existing_ma, world, expected=None)

    assert _state(existing_ma) == ("renewal-requested", "stop")


def test_approve_stop_double_click_and_other_org(world, client_for, existing_ma):
    _set(existing_ma, "renewal-requested", "stop")
    client = client_for(world.admin)

    _approve_stop(client, existing_ma, world)
    first_update = models.Procurement.objects.get(id=existing_ma.id).updated_date
    _approve_stop(client, existing_ma, world)

    assert _state(existing_ma) == ("disactive", "stop")
    assert models.Procurement.objects.get(id=existing_ma.id).updated_date == first_update
    _set(existing_ma, "renewal-requested", "stop")
    assert _approve_stop(client_for(world.admin_b), existing_ma, world).status_code in (302, 404)
    assert _state(existing_ma) == ("renewal-requested", "stop")


def test_parent_with_sub_contracts_cannot_be_requested_or_approved(world, client_for, create_ma):
    parent = create_ma(world.org, user=world.admin, name="[TEST] หลัก", responsible=[world.role_responsible])
    child = create_ma(world.org, user=world.admin, name="[TEST] ย่อย", responsible=[world.role_responsible])
    models.Procurement.objects(id=child.id).update(set__parent_procurement=parent.id)

    _request(client_for(world.responsible), parent, world, "stop")
    assert _state(parent) == ("review", None)
    _set(parent, "renewal-requested", "stop")
    _approve_stop(client_for(world.admin), parent, world)
    assert _state(parent) == ("renewal-requested", "stop")


# ---------------------------------------------------------------------------
# ป้ายสถานะ / ตัวกรองในรายการ MA
# ---------------------------------------------------------------------------


def test_list_renders_both_badges_and_filters_by_each_status(world, client_for, create_ma):
    day = datetime.timedelta(days=1)
    a = _ma_with_dates(world, create_ma, [(TODAY - 5 * day, TODAY + 90 * day)])
    b = _ma_with_dates(world, create_ma, [(TODAY + 5 * day, TODAY + 90 * day)])
    c = _ma_with_dates(world, create_ma, [(TODAY - 90 * day, TODAY - 5 * day)])
    for ma, name in ((a, "AAA"), (b, "BBB"), (c, "CCC")):
        models.Procurement.objects(id=ma.id).update(set__name=f"[TEST] {name}")
    _set(c, "renewal-requested", "renew")
    client = client_for(world.admin)

    def names(**query):
        params = "&".join(f"{key}={value}" for key, value in query.items())
        html = client.get(f"/procurement/products?{params}&{_q(world.org)}").get_data(as_text=True)
        return {name for name in ("AAA", "BBB", "CCC") if f"[TEST] {name}" in html}, html

    everything, html = names()
    assert everything == {"AAA", "BBB", "CCC"}
    for usage in ("upcoming", "in_use", "expired"):
        assert f'data-usage-status="{usage}"' in html
    for renewal in ("review", "renewal-requested"):
        assert f'data-renewal-status="{renewal}"' in html
    assert "(ขอต่ออายุ)" in html
    assert names(usage_status="upcoming")[0] == {"BBB"}
    assert names(usage_status="in_use")[0] == {"AAA"}
    assert names(usage_status="expired")[0] == {"CCC"}
    assert names(renewal_status="renewal-requested")[0] == {"CCC"}
    assert names(renewal_status="review")[0] == {"AAA", "BBB"}
    assert names(renewal_status="review", usage_status="upcoming")[0] == {"BBB"}
    assert names(renewal_status="renewed")[0] == set()
    assert names(usage_status="bogus")[0] == {"AAA", "BBB", "CCC"}  # ค่าที่ไม่รู้จักไม่กรอง
    form_html = client.get(f"/procurement/products?{_q(world.org)}").get_data(as_text=True)
    assert 'name="usage_status"' in form_html and 'name="renewal_status"' in form_html


def test_detail_shows_both_badges(world, client_for, existing_ma):
    html = client_for(world.admin).get(f"/procurement/payment/{existing_ma.id}?{_q(world.org)}").get_data(as_text=True)

    assert 'data-usage-status="in_use"' in html and 'data-renewal-status="review"' in html


def test_non_renewal_list_still_lists_disactive(world, client_for, existing_ma):
    _set(existing_ma, "disactive", "stop")

    html = client_for(world.admin).get(f"/procurement/requisitions/non-renewal?{_q(world.org)}").get_data(as_text=True)

    assert existing_ma.name in html


# ---------------------------------------------------------------------------
# อีเมลแจ้งการมอบหมาย
# ---------------------------------------------------------------------------


def _assigned_logs():
    return list(models.ReminderLog.objects(kind="assigned").order_by("id"))


def _form_with(world, *members, action=None, **extra):
    data = ma_form(
        [_item(amount="100000.00", responsible_by=[str(member.id) for member in members])], **extra
    )
    if action:
        data["action"] = action
    return data


def test_creating_an_ma_emails_each_responsible_once(world, client_for, assignment_emails):
    response = _create(client_for(world.admin), world, _form_with(world, world.role_responsible, world.role_creator))

    assert response.status_code == 302
    logs = _assigned_logs()
    assert len(logs) == 2 and len(assignment_emails) == 2
    assert {tuple(log.recipients) for log in logs} == {
        (world.responsible.email,),
        (world.creator.email,),
    }
    assert all(log.status == "queued" and log.created_by.id == world.admin.id for log in logs)


def test_edit_emails_only_newly_added_responsible_and_never_resends(world, client_for, existing_ma, assignment_emails):
    existing_ma = models.Procurement.objects.get(id=existing_ma.id)
    assert assignment_emails == []  # existing_ma สร้างด้วย save_with_items ตรง ๆ ไม่ผ่านฟอร์ม
    client = client_for(world.admin)
    item = existing_ma.get_items()[0]

    def edit(*members):
        fresh = models.Procurement.objects.get(id=existing_ma.id)
        form = _edit_form(fresh)
        form["items-0-responsible_by"] = [str(member.id) for member in members]
        return client.post(_item_edit_url(world, fresh), data=form)

    assert edit(world.role_responsible).status_code == 302  # คนเดิมอยู่ ไม่ส่งซ้ำ
    assert _assigned_logs() == []
    edit(world.role_responsible, world.role_creator)  # เพิ่มใหม่ 1 คน
    edit(world.role_responsible, world.role_creator)  # แก้ซ้ำ ไม่ส่งอีก
    edit(world.role_responsible)  # ถอดคนที่เพิ่ม ไม่ส่ง
    edit(world.role_responsible, world.role_creator)  # ใส่กลับ ไม่ส่งซ้ำ (1 ฉบับต่อรายการ + สมาชิก)

    logs = _assigned_logs()
    assert [tuple(log.recipients) for log in logs] == [(world.creator.email,)]
    assert len(assignment_emails) == 1 and logs[0].item.id == item.id


def test_draft_sends_nothing_until_published_then_once(world, client_for, assignment_emails):
    client = client_for(world.admin)
    response = _create(client, world, _form_with(world, world.role_responsible, action="draft"))
    assert response.status_code == 302
    draft = models.Procurement.objects.get()
    assert draft.status == "draft" and assignment_emails == [] and _assigned_logs() == []

    edit_url = f"/procurement/products/{draft.id}/edit?{_q(world.org)}"
    form = _form_with(world, world.role_responsible, world.role_creator, action="draft")
    form["version"] = draft.get_version()
    form["items-0-item_id"] = str(draft.get_items()[0].id)
    client.post(edit_url, data=form)
    assert assignment_emails == []  # แก้แบบร่างต่อ ยังไม่ส่ง

    draft = models.Procurement.objects.get()
    form = _form_with(world, world.role_responsible, world.role_creator)
    form["version"] = draft.get_version()
    form["items-0-item_id"] = str(draft.get_items()[0].id)
    assert client.post(edit_url, data=form).status_code == 302

    assert models.Procurement.objects.get().status == "review"
    assert len(assignment_emails) == 2
    assert {tuple(log.recipients) for log in _assigned_logs()} == {(world.responsible.email,), (world.creator.email,)}


def test_two_item_ma_emails_once_not_again_for_the_sub_contract_copies(world, client_for, assignment_emails):
    from test_ma_structure import _two_item_form

    _create(client_for(world.admin), world, _two_item_form(world))

    # License A: admin + responsible, MA B: creator = 3 ฉบับ (สัญญาย่อยที่เป็นสำเนาไม่ส่งซ้ำ)
    assert len(assignment_emails) == 3
    assert models.Procurement.objects(parent_procurement__ne=None).count() == 2


def test_enqueue_failure_marks_log_failed_and_does_not_break_the_save(world, client_for, monkeypatch):
    def broken(log, settings):
        raise RuntimeError("redis down")

    monkeypatch.setattr(ma_assignments, "enqueue_email_job", broken)

    response = _create(client_for(world.admin), world, _form_with(world, world.role_responsible))

    assert response.status_code == 302
    (log,) = _assigned_logs()
    assert log.status == "failed" and "redis" not in (log.error or "")


def test_assignment_email_content_has_assigner_ma_item_dates_and_link(world, client_for):
    _create(client_for(world.admin), world, _form_with(world, world.role_responsible))
    (log,) = _assigned_logs()

    subject, body = ma_send_emails.build_reminder_email(log, {"KAMPAN_HOST_URL": "https://kampan.test"})

    item = log.item
    assert subject.startswith("[มอบหมาย]") and item.name in subject
    assert "Admin" in body and "[TEST] MA" in body and item.name in body
    assert "01/01/2569" in body or "2569" in body
    assert f"https://kampan.test/procurement/payment/{log.procurement.id}?organization_id={world.org.id}" in body


def test_no_assignment_email_when_ma_is_not_open_for_it(world, create_ma, assignment_emails):
    for status in ("disactive", "renewed", "draft"):
        ma = create_ma(world.org, user=world.admin, status=status, responsible=[world.role_responsible])
        logs = ma_assignments.notify_new_assignments(ma, ma.get_items(), {}, world.admin, {})
        assert logs == []
    assert assignment_emails == []


def test_renew_emails_the_responsible_of_the_new_ma(world, client_for, existing_ma, assignment_emails):

    _set(existing_ma, "renewal-requested", "renew")
    item = existing_ma.get_items()[0]
    data = ma_form(
        [_item(amount="1000.00", name=item.name, responsible_by=[str(world.role_responsible.id)])],
        total_amount="1000.00",
        psu="PSU-RENEW",
        expected_request="renew",
    )

    response = client_for(world.admin).post(
        f"/procurement/products/{existing_ma.id}/renew?{_q(world.org)}", data=data
    )

    assert response.status_code == 302
    new = models.Procurement.objects.get(renewed_from=existing_ma.id)
    assert [log.procurement.id for log in _assigned_logs()] == [new.id]
    assert len(assignment_emails) == 1


# ---------------------------------------------------------------------------
# หยุดส่งอีเมลทั้งหมดเมื่อ MA ปิดแล้ว (รวมที่ค้างคิว)
# ---------------------------------------------------------------------------


class _FakeSMTP:
    instances = []

    def __init__(self, settings):
        self.sent = []
        _FakeSMTP.instances.append(self)

    def login(self):
        return True

    def send_email(self, receiver, subject, body, html=False):
        self.sent.append((receiver, subject))
        return True

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(ma_send_emails, "PSUSMTP", _FakeSMTP)
    return _FakeSMTP


def _queued_log(ma, kind="expiry"):
    item = ma.get_items()[0]
    return models.ReminderLog(
        organization=ma.organization,
        procurement=ma,
        item=item,
        kind=kind,
        trigger_date=datetime.datetime.combine(TODAY, datetime.time.min),
        offset="due",
        recipients=["someone@example.com"],
        status="queued",
        dedupe_key=f"{item.id}:{kind}:test",
        created_by=ma.created_by,
    ).save()


@pytest.mark.parametrize("kind", ["expiry", "payment", "assigned", "custom"])
@pytest.mark.parametrize("status", ["disactive", "renewed", "draft"])
def test_worker_skips_queued_mail_of_a_closed_ma(world, create_ma, smtp, status, kind):
    ma = create_ma(world.org, user=world.admin, responsible=[world.role_responsible])
    log = _queued_log(ma, kind)
    _set(ma, status)  # ปิด MA หลังเข้าคิวแล้ว

    sent = ma_send_emails.send_reminder_job(str(log.id), {})

    log.reload()
    assert sent is False and log.status == "skipped" and "ไม่ส่งอีเมล" in log.error
    assert smtp.instances == [] or all(not instance.sent for instance in smtp.instances)


@pytest.mark.parametrize("status", ["review", "renewal-requested", "active", "pending"])
def test_worker_still_sends_for_an_open_ma(world, create_ma, smtp, status):
    ma = create_ma(world.org, user=world.admin, responsible=[world.role_responsible])
    log = _queued_log(ma)
    _set(ma, status)

    assert ma_send_emails.send_reminder_job(str(log.id), {}) is True
    assert smtp.instances[0].sent


@pytest.mark.parametrize("status", ["disactive", "renewed", "draft"])
def test_due_reminders_skip_closed_ma(world, create_ma, status):
    ma = create_ma(world.org, user=world.admin, responsible=[world.role_responsible], days_to_end=0)
    models.ProcurementItem.objects(procurement=ma).update(set__end_date=datetime.datetime.combine(TODAY, datetime.time.min))
    assert [r.kind for r in due_reminders(TODAY)]  # ก่อนปิดมีเตือนวันสิ้นสุด
    _set(ma, status)

    assert due_reminders(TODAY) == []
