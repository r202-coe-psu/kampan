"""เอกสารเบิกค่าใช้จ่ายของ พขร. (ระบบจองรถ): จำนวนเงินตัวอักษรไทย และ PDF ใบเบิกที่การเงินกรอกเงินแล้วดาวน์โหลด"""

import datetime
import io
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PyPDF2 import PdfReader

from kampan import models, utils
from kampan.web import redis_rq

thai_baht_text = utils.car_reservation_finance.thai_baht_text


@pytest.mark.parametrize(
    "amount, expected",
    [
        (830, "แปดร้อยสามสิบบาทถ้วน"),
        (150, "หนึ่งร้อยห้าสิบบาทถ้วน"),
        ("21.50", "ยี่สิบเอ็ดบาทห้าสิบสตางค์"),
        (1000000, "หนึ่งล้านบาทถ้วน"),
        (11, "สิบเอ็ดบาทถ้วน"),
        (21, "ยี่สิบเอ็ดบาทถ้วน"),
        (0, "ศูนย์บาทถ้วน"),
        ("0.25", "ศูนย์บาทยี่สิบห้าสตางค์"),
        (101, "หนึ่งร้อยเอ็ดบาทถ้วน"),
        (1234567, "หนึ่งล้านสองแสนสามหมื่นสี่พันห้าร้อยหกสิบเจ็ดบาทถ้วน"),
    ],
)
def test_thai_baht_text_spells_the_amount_in_thai_words(amount, expected):
    assert thai_baht_text(Decimal(str(amount))) == expected


def test_half_satang_rounds_half_even_like_the_saved_money():
    assert thai_baht_text(Decimal("37.625")) == "สามสิบเจ็ดบาทหกสิบสองสตางค์"
    assert thai_baht_text(Decimal("2.675")) == "สองบาทหกสิบแปดสตางค์"


def test_meal_rows_are_rounded_once_so_figures_words_and_total_agree():
    from kampan.utils.template_filters import format_amount

    data = utils.car_reservation_finance.FinanceData(
        meal_rows=((Decimal("75.25"), Decimal("0.5")), (Decimal("100.01"), Decimal("0.5")))
    )
    assert data.meal_amounts == (Decimal("37.62"), Decimal("50.00"))
    assert data.total == Decimal("87.62")
    assert format_amount(data.total) == "87.62"
    assert thai_baht_text(data.total) == "แปดสิบเจ็ดบาทหกสิบสองสตางค์"


BASE = "/car_reservation/requests"


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """ปิดงานแล้วระบบส่งอีเมลเข้าคิว: กันการต่อ Redis จริง"""
    with patch.object(redis_rq.redis_queue, "queue", MagicMock(), create=True):
        yield


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, login_as, create_car):
    org = create_org("Finance Org")
    org.enabled_modules = ["car_reservation"]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "Finance")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.driver = create_user("สมชาย", "ใจดี")
    assign_user_to_org(s.driver, org, roles=["driver"])
    s.head = create_user("Head", "Finance")
    assign_user_to_org(s.head, org, roles=["head"])
    s.dispatcher = create_user("Dispatcher", "Finance")
    assign_user_to_org(s.dispatcher, org, roles=["dispatcher"])
    s.org_admin = create_user("Admin", "Finance")
    assign_user_to_org(s.org_admin, org, roles=["admin"])
    s.car = create_car(org, "กก 1234", vehicle_type="เก๋ง")

    def client_for(user):
        return login_as(app.test_client(), user)

    s.client_for = client_for

    def reservation(request_type="domestic", status="completed"):
        return models.CarReservation(
            organization=org,
            creator=s.requester,
            requester_unit="คณะวิศวกรรมศาสตร์",
            phone="081-234-5678",
            request_type=request_type,
            province_scope="in_province" if request_type == "domestic" else None,
            location="กรุงเทพฯ",
            request_reason="ประชุม",
            departure_datetime=datetime.datetime(2026, 11, 20, 8, 30),
            return_datetime=datetime.datetime(2026, 11, 20, 16, 30),
            status=status,
            route_snapshot=["supervisor", "dispatcher"],
            current_step=2,
            car=s.car,
            driver=s.driver,
            started_at=datetime.datetime(2026, 11, 20, 8, 40),
            completed_at=datetime.datetime(2026, 11, 20, 16, 10),
        ).save()

    s.reservation = reservation
    return s


def finance_url(world, reservation, doc):
    return f"{BASE}/{reservation.id}/finance/{doc}?organization_id={world.org.id}"


def finance_data(**overrides):
    data = {
        "memo_number": "ศธ 0521.1/123",
        "memo_date": "2026-11-18",
        "meal_rate_1": "380",
        "meal_days_1": "1",
        "meal_rate_2": "450",
        "meal_days_2": "1",
        "evidence_count": "2",
    }
    data.update(overrides)
    return data


def pdf_text(response):
    reader = PdfReader(io.BytesIO(response.data))
    return "\n".join(page.extract_text() for page in reader.pages)


def test_finance_downloads_a_travel_expense_pdf_filled_with_the_trip_and_the_money(world):
    reservation = world.reservation()

    response = world.client_for(world.head).post(
        finance_url(world, reservation, "travel"), data=finance_data()
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert str(reservation.id) in response.headers["Content-Disposition"]
    text = pdf_text(response)
    for expected in (
        "สมชาย ใจดี",  # พขร.
        "20 พฤศจิกายน 2569",  # วันเดินทาง (พ.ศ.)
        "830",  # รวมเงิน
        "แปดร้อยสามสิบบาทถ้วน",  # ตัวอักษร
    ):
        assert expected in text


def test_domestic_trip_offers_both_the_travel_and_the_allowance_documents(world):
    reservation = world.reservation("domestic")

    response = world.client_for(world.head).post(
        finance_url(world, reservation, "allowance"),
        data=finance_data(allowance_days="0.5", allowance_amount="150", meal_rate_1="", meal_days_1="", meal_rate_2="", meal_days_2=""),
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    text = pdf_text(response)
    assert "150" in text
    assert "หนึ่งร้อยห้าสิบบาทถ้วน" in text


def test_welfare_and_abroad_trips_only_have_the_travel_document(world):
    for request_type in ("welfare", "abroad"):
        reservation = world.reservation(request_type)
        client = world.client_for(world.head)

        travel = client.post(finance_url(world, reservation, "travel"), data=finance_data())
        allowance = client.post(finance_url(world, reservation, "allowance"), data=finance_data())

        assert travel.status_code == 200
        assert allowance.status_code == 404


def test_airport_trip_has_no_finance_document(world):
    reservation = world.reservation("airport")
    client = world.client_for(world.head)

    for doc in ("travel", "allowance"):
        assert client.post(finance_url(world, reservation, doc), data=finance_data()).status_code == 404


@pytest.mark.parametrize("who", ["requester", "driver"])
def test_people_without_a_finance_role_are_refused(world, who):
    reservation = world.reservation()

    response = world.client_for(getattr(world, who)).post(
        finance_url(world, reservation, "travel"), data=finance_data()
    )

    assert response.status_code in (302, 403)
    assert response.mimetype != "application/pdf"


@pytest.mark.parametrize("who", ["head", "dispatcher", "org_admin"])
def test_head_approvers_and_org_admin_may_issue_the_documents(world, who):
    reservation = world.reservation()

    response = world.client_for(getattr(world, who)).post(
        finance_url(world, reservation, "travel"), data=finance_data()
    )

    assert response.status_code == 200


@pytest.mark.parametrize("status", ["pending", "active", "denied", "cancelled"])
def test_a_trip_that_is_not_completed_has_no_finance_document(world, status):
    reservation = world.reservation(status=status)

    response = world.client_for(world.head).post(
        finance_url(world, reservation, "travel"), data=finance_data()
    )

    assert response.status_code in (302, 403)
    assert response.mimetype != "application/pdf"


def test_finance_form_asks_for_the_money_before_downloading(world):
    reservation = world.reservation()

    response = world.client_for(world.head).get(finance_url(world, reservation, "travel"))

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    for field in ("memo_number", "lodging_amount", "vehicle_cost", "meal_rate_1", "evidence_count"):
        assert f'name="{field}"' in html


def test_detail_page_offers_the_allowed_documents_to_finance_roles_once_completed(world):
    reservation = world.reservation("domestic")
    url = f"{BASE}/{reservation.id}?organization_id={world.org.id}"

    head_html = world.client_for(world.head).get(url).get_data(as_text=True)
    requester_html = world.client_for(world.requester).get(url).get_data(as_text=True)

    assert f"/requests/{reservation.id}/finance/travel" in head_html
    assert f"/requests/{reservation.id}/finance/allowance" in head_html
    assert "/finance/" not in requester_html


def test_detail_page_hides_the_documents_for_airport_and_unfinished_trips(world):
    airport = world.reservation("airport")
    pending = world.reservation("domestic", status="pending")
    client = world.client_for(world.head)

    for reservation in (airport, pending):
        html = client.get(f"{BASE}/{reservation.id}?organization_id={world.org.id}").get_data(as_text=True)
        assert "/finance/" not in html


def test_trip_hours_come_from_the_actual_start_and_close_times(world):
    reservation = world.reservation()
    reservation.started_at = datetime.datetime(2026, 11, 20, 8, 0)
    reservation.completed_at = datetime.datetime(2026, 11, 21, 12, 30)

    assert utils.car_reservation_finance.trip_duration(reservation) == (1, 4)

    reservation.started_at = reservation.completed_at = None
    assert utils.car_reservation_finance.trip_duration(reservation) == (0, 8)


def test_travel_times_printed_are_the_actual_start_and_end_the_duration_is_counted_from(
    world,
):
    reservation = world.reservation()

    response = world.client_for(world.head).post(
        finance_url(world, reservation, "travel"), data=finance_data()
    )

    text = pdf_text(response)
    assert "08.40" in text  # started_at, not the planned 08.30
    assert "16.10" in text  # completed_at, not the planned 16.30
    assert "08.30" not in text


def saved_records(world, reservation):
    return models.CarReservationFinanceDocument.objects(reservation=reservation)


def test_saving_keeps_the_numbers_in_their_own_collection_and_reopens_the_form_with_them(world):
    reservation = world.reservation()
    client = world.client_for(world.head)

    response = client.post(
        finance_url(world, reservation, "travel"), data={**finance_data(), "action": "save"}
    )

    assert response.status_code == 302
    (record,) = saved_records(world, reservation)
    assert (record.doc, record.organization, record.created_by) == ("travel", world.org, world.head)
    assert record.memo_number == "ศธ 0521.1/123"
    assert record.memo_date == datetime.date(2026, 11, 18)
    assert record.meal_rate_1 == Decimal("380.00") and record.evidence_count == 2
    page = client.get(response.headers["Location"]).get_data(as_text=True)
    assert 'value="ศธ 0521.1/123"' in page
    assert 'value="380.00"' in page
    assert 'data-role="finance-saved-at"' in page


def test_two_saves_racing_to_create_the_same_document_end_in_one_record(world, monkeypatch):
    reservation = world.reservation()
    client = world.client_for(world.head)
    client.post(finance_url(world, reservation, "travel"), data={**finance_data(), "action": "save"})
    finance = utils.car_reservation_finance
    real_lookup = finance.saved_document
    lookups = []

    def lookup_misses_once(reservation, doc):
        # คำขอที่สองค้นตอนที่คำขอแรกยังไม่บันทึก จึงไม่เจอ แล้วพยายามสร้างซ้ำ
        lookups.append(doc)
        return None if len(lookups) == 1 else real_lookup(reservation, doc)

    monkeypatch.setattr(finance, "saved_document", lookup_misses_once)
    response = client.post(
        finance_url(world, reservation, "travel"),
        data={**finance_data(), "memo_number": "ศธ 999", "action": "save"},
    )

    assert response.status_code == 302
    (record,) = saved_records(world, reservation)
    assert record.memo_number == "ศธ 999"


def test_the_travel_and_allowance_documents_are_saved_separately_and_updated_in_place(world):
    reservation = world.reservation()
    client = world.client_for(world.head)

    client.post(finance_url(world, reservation, "travel"), data={**finance_data(), "action": "save"})
    client.post(
        finance_url(world, reservation, "allowance"),
        data={**finance_data(memo_number="ศธ 999"), "action": "save"},
    )
    client.post(
        finance_url(world, reservation, "travel"),
        data={**finance_data(memo_number="ศธ 0521.1/124"), "action": "save"},
    )

    records = {r.doc: r for r in saved_records(world, reservation)}
    assert set(records) == {"travel", "allowance"}
    assert records["travel"].memo_number == "ศธ 0521.1/124"
    assert records["allowance"].memo_number == "ศธ 999"


def test_downloading_also_saves_the_numbers(world):
    reservation = world.reservation()

    response = world.client_for(world.head).post(
        finance_url(world, reservation, "travel"), data={**finance_data(), "action": "download"}
    )

    assert response.mimetype == "application/pdf"
    assert saved_records(world, reservation).count() == 1


def test_detail_page_marks_which_documents_have_been_saved(world):
    reservation = world.reservation()
    client = world.client_for(world.head)
    client.post(finance_url(world, reservation, "travel"), data={**finance_data(), "action": "save"})

    html = client.get(f"{BASE}/{reservation.id}?organization_id={world.org.id}").get_data(as_text=True)

    travel = html.split('data-doc="travel"')[1].split("</a>")[0]
    allowance = html.split('data-doc="allowance"')[1].split("</a>")[0]
    assert 'data-role="finance-saved"' in travel
    assert 'data-role="finance-saved"' not in allowance
