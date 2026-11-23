"""ช่องข้อความในฟอร์มขอใช้รถถูกจำกัดความยาวให้พิมพ์ลงช่องของแบบฟอร์ม PDF ได้ครบ ไม่ถูกตัดเป็น "..." """

import pytest
from reportlab.pdfbase import pdfmetrics
from wtforms import validators

from kampan.utils import car_reservation_finance as finance
from kampan.utils import car_reservation_paper as paper
from kampan.utils import car_reservation_paper_layouts as layouts
from kampan.web.forms import car_reservation as forms
from kampan.web.forms import car_reservation_finance as finance_forms

THAI = "คณะวิศวกรรมศาสตร์ ภาควิชาวิศวกรรมคอมพิวเตอร์ กองกายภาพและสิ่งแวดล้อม ประชุมวิชาการ " * 3
DIGITS = "0742870000 ต่อ 1234 " * 6


def _max_length(field):
    return next(v.max for v in field.validators if isinstance(v, validators.Length))


@pytest.mark.parametrize("request_type", list(layouts.LAYOUTS))
def test_text_at_the_limit_fits_every_paper_field(app, request_type):
    paper.ensure_font()
    for field in layouts.LAYOUTS[request_type].fields:
        limit = layouts.max_chars(field.var, (request_type,))
        for text in (THAI[:limit], DIGITS[:limit]):
            width = pdfmetrics.stringWidth(text, paper.FONT_NAME, layouts.MIN_FONT_SIZE)
            assert width <= field.x1 - field.x0, (field.var, text)


@pytest.mark.parametrize(
    "request_type, field_name, var",
    [
        ("domestic", "requester_unit", "unit"),
        ("domestic", "phone", "phone"),
        ("airport", "requester_unit", "unit"),
        ("airport", "flight_number", "flight_number"),
        ("welfare", "affiliation", "unit"),
        ("welfare", "house", "house"),
        ("abroad", "country", "country"),
        ("abroad", "pickup_place", "pickup_place"),
    ],
)
def test_form_field_is_capped_to_its_paper_field(app, request_type, field_name, var):
    with app.test_request_context():
        field = forms.FORM_BY_REQUEST_TYPE[request_type]()[field_name]
    limit = layouts.max_chars(var, (request_type,))
    assert _max_length(field) == limit
    assert f'maxlength="{limit}"' in field()


def test_form_rejects_text_longer_than_the_paper_field(app):
    limit = layouts.max_chars("phone", ("domestic",))
    with app.test_request_context(method="POST", data={"phone": "0" * (limit + 1)}):
        form = forms.DomesticReservationForm(meta={"csrf": False})
        form.validate()
    assert form.phone.errors == [f"ยาวเกินช่องในแบบฟอร์มใบขอใช้รถ (ไม่เกิน {limit} ตัวอักษร)"]


def test_airport_passenger_rows_are_capped(app):
    with app.test_request_context():
        form = forms.AirportReservationForm()
    for row in form.passengers:
        assert _max_length(row.form.name) == layouts.max_chars("p1_name", ("airport",))
        assert _max_length(row.form.phone) == layouts.max_chars("p1_phone", ("airport",))


def test_location_dropdowns_keep_their_limit_so_every_reference_name_is_accepted(app):
    with app.test_request_context():
        form = forms.WelfareReservationForm()
    assert _max_length(form.subdistrict) == 256


def test_extra_travelers_fits_the_narrowest_paper(app):
    with app.test_request_context():
        form = forms.DispatchDecisionForm()
    assert _max_length(form.extra_travelers) == layouts.max_chars("extra_travelers")


def test_finance_memo_number_fits_its_cell(app):
    with app.test_request_context():
        form = finance_forms.FinanceForm()
    assert _max_length(form.memo_number) == finance.max_chars(finance.MEMO_NUMBER)


def test_wrong_type_errors_are_thai(app):
    data = {"passenger_number": "abc", "departure_date": "2569-99-99"}
    with app.test_request_context(method="POST", data=data):
        form = forms.DomesticReservationForm(meta={"csrf": False})
        form.validate()
    assert "กรุณากรอกเป็นจำนวนเต็ม" in form.passenger_number.errors
    assert "วันที่ไม่ถูกต้อง" in form.departure_date.errors
    assert form.location.errors == ["กรุณากรอกข้อมูล"]


def test_field_renders_placeholder_and_live_hint(app):
    with app.test_request_context():
        form = forms.DomesticReservationForm()
        renderer = app.jinja_env.get_template("/base/html-renderer.html").module
        location = str(renderer.render_field(form.location))
        email = str(renderer.render_field(form.contact_email))
        passengers = str(renderer.render_number_field(form.passenger_number))
    assert 'placeholder="เช่น มหาวิทยาลัยเชียงใหม่"' in location
    assert 'class="validator-hint hidden">กรุณากรอกข้อมูล' in location
    assert 'type="email"' in email and "รูปแบบอีเมลไม่ถูกต้อง" in email
    assert f"กรุณากรอกเป็นตัวเลข 0 ถึง {forms.MAX_PASSENGERS}" in passengers
