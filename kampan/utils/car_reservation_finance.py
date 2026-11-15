"""เอกสารเบิกค่าใช้จ่ายของพนักงานขับรถ (ระบบจองรถ): จำนวนเงินตัวอักษรไทยและการพิมพ์ทับแบบฟอร์ม PDF

แบบฟอร์มเปล่าอยู่ที่ kampan/web/static/data/car_reservation_finance/*.pdf (สร้างจาก .docx ของกองกายภาพด้วย
scripts/prepare_car_finance_forms.py) ฟังก์ชัน render พิมพ์ข้อมูลทับลงบนเส้นประ/ช่องตาราง
"""

import dataclasses
import datetime
import io
import pathlib
from decimal import ROUND_HALF_UP, Decimal

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from kampan import models
from kampan.utils import template_filters

DIGITS = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
PLACES = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน"]
MILLION = 1_000_000


def _words_below_million(number):
    words = []
    digits = str(number)
    for index, char in enumerate(digits):
        digit = int(char)
        place = len(digits) - index - 1
        if digit == 0:
            continue
        if place == 1 and digit == 1:
            words.append("สิบ")
        elif place == 1 and digit == 2:
            words.append("ยี่สิบ")
        elif place == 0 and digit == 1 and len(digits) > 1:
            words.append("เอ็ด")
        else:
            words.append(DIGITS[digit] + PLACES[place])
    return "".join(words)


def _integer_words(number):
    if number == 0:
        return DIGITS[0]
    groups = []
    while number > 0:
        groups.append(number % MILLION)
        number //= MILLION
    words = ""
    for index, group in enumerate(reversed(groups)):
        if group:
            words += _words_below_million(group)
        if index < len(groups) - 1:
            words += "ล้าน"
    return words


def thai_baht_text(amount):
    """จำนวนเงินเป็นตัวอักษรไทย เช่น 21.50 -> ยี่สิบเอ็ดบาทห้าสิบสตางค์ (ไม่มีสตางค์ลงท้าย บาทถ้วน)"""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    baht = int(amount)
    satang = int((amount - baht) * 100)
    text = _integer_words(baht) + "บาท"
    if satang == 0:
        return text + "ถ้วน"
    return text + _words_below_million(satang) + "สตางค์"


# ---------------------------------------------------------------------------
# ข้อมูลและกติกาของเอกสาร
# ---------------------------------------------------------------------------

# ผู้ออกเอกสารเบิก: หัวหน้า ผู้อนุมัติทุกขั้น และ admin ของ org (admin ของระบบผ่านอยู่แล้ว)
FINANCE_ROLES = ("admin", "head", *models.organizations.RESERVATION_APPROVER_ROLE_KEYS)

# เอกสารที่ออกได้ของใบขอแต่ละประเภท (airport ไม่มีเอกสารเบิก)
DOCUMENTS_BY_REQUEST_TYPE = {
    "domestic": ("travel", "allowance"),
    "welfare": ("travel",),
    "abroad": ("travel",),
    "airport": (),
}
DOCUMENT_LABELS = {
    "travel": "ใบเบิกค่าใช้จ่ายในการเดินทาง + ใบสำคัญรับเงิน",
    "allowance": "ใบเบิกค่าเบี้ยเลี้ยงเดินทาง",
}
DOCUMENT_PDFS = {"travel": "travel_expense.pdf", "allowance": "allowance.pdf"}

THAI_MONTHS = [
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]


def documents_for(request_type):
    return DOCUMENTS_BY_REQUEST_TYPE.get(request_type, ())


def can_issue(organization, user):
    """user ออกเอกสารเบิกได้ใน org นี้: admin ระบบ หรือถือ role ใน FINANCE_ROLES ที่ active"""
    if user is None:
        return False
    if "admin" in user.roles:
        return True
    return (
        models.OrganizationUserRole.objects(
            organization=organization,
            user=user,
            status="active",
            roles__in=FINANCE_ROLES,
        ).first()
        is not None
    )


def documents_for_reservation(reservation):
    """เอกสารที่ออกได้ของใบขอนี้: เฉพาะที่เสร็จสิ้นแล้ว คืน [(key, ชื่อเอกสาร)]"""
    if reservation.status != "completed":
        return []
    return [(doc, DOCUMENT_LABELS[doc]) for doc in documents_for(reservation.request_type)]


def thai_date(date):
    """20 พฤศจิกายน 2569"""
    return f"{date.day} {THAI_MONTHS[date.month - 1]} {date.year + 543}"


def thai_time(moment):
    return f"{moment.hour:02d}.{moment.minute:02d}"


def _decimal(value):
    return Decimal(value) if value is not None else Decimal(0)


@dataclasses.dataclass
class FinanceData:
    """ตัวเลขที่การเงินกรอก (ช่องว่าง = 0)"""

    memo_number: str = ""
    memo_date: datetime.date = None
    allowance_type: str = ""
    allowance_days: Decimal = Decimal(0)
    allowance_amount: Decimal = Decimal(0)
    lodging_days: Decimal = Decimal(0)
    lodging_amount: Decimal = Decimal(0)
    vehicle_cost: Decimal = Decimal(0)
    # เงินช่วยเหลือค่าอาหาร พขร.: (อัตราต่อวัน, จำนวนวัน) สูงสุด 2 แถว ตามใบสำคัญรับเงิน
    meal_rows: tuple = ()
    evidence_count: int = 0

    @classmethod
    def from_form(cls, form):
        meal_rows = []
        for rate, days in (
            (form.meal_rate_1.data, form.meal_days_1.data),
            (form.meal_rate_2.data, form.meal_days_2.data),
        ):
            if _decimal(rate) and _decimal(days):
                meal_rows.append((_decimal(rate), _decimal(days)))
        return cls(
            memo_number=form.memo_number.data or "",
            memo_date=form.memo_date.data,
            allowance_type=form.allowance_type.data or "",
            allowance_days=_decimal(form.allowance_days.data),
            allowance_amount=_decimal(form.allowance_amount.data),
            lodging_days=_decimal(form.lodging_days.data),
            lodging_amount=_decimal(form.lodging_amount.data),
            vehicle_cost=_decimal(form.vehicle_cost.data),
            meal_rows=tuple(meal_rows),
            evidence_count=form.evidence_count.data or 0,
        )

    @property
    def meal_total(self):
        return sum((rate * days for rate, days in self.meal_rows), Decimal(0))

    @property
    def total(self):
        return (
            self.allowance_amount
            + self.lodging_amount
            + self.vehicle_cost
            + self.meal_total
        )


def trip_duration(reservation):
    """(วัน, ชั่วโมง) ของทริป: จากเวลาเริ่ม-ปิดงานจริง ถ้าไม่มีใช้เวลาออก-กลับตามใบขอ"""
    start = reservation.started_at or reservation.departure_datetime
    end = reservation.completed_at or reservation.return_datetime or start
    seconds = max(int((end - start).total_seconds()), 0)
    return seconds // 86400, seconds % 86400 // 3600


# ---------------------------------------------------------------------------
# พิมพ์ทับแบบฟอร์ม PDF เปล่า
#
# พิกัดวัดจากแบบฟอร์มเปล่าเป็น pt: x จากซ้าย, y จากบนของเส้นประ/เส้นกรอบของบรรทัด ถ้าสร้างฟอร์มเปล่าใหม่
# (scripts/prepare_car_finance_forms.py) ต้องวัดพิกัดด้านล่างใหม่
# ---------------------------------------------------------------------------

STATIC = pathlib.Path(__file__).resolve().parent.parent / "web/static"
FORMS_DIR = STATIC / "data/car_reservation_finance"
FONT_NAME = "THSarabunNew"
FONT_PATH = STATIC / "fonts/THSarabunNew.ttf"
FONT_SIZE = 16
MIN_FONT_SIZE = 11
PAGE_WIDTH, PAGE_HEIGHT = 612, 792
BASELINE_RAISE = 4.5  # ตัวอักษรอยู่เหนือเส้นประเท่านี้
LINE_STEP = 21.8

# ช่วงแนวนอน (x0, x1) ของช่องที่ซ้ำกันทั้งสองฟอร์ม
MEMO_NUMBER = (203, 380)
MEMO_DATE = (432, 551)
NAME = (160, 289)
WITH_CELL = (345, 551)
PURPOSE_FIRST = (190, 551)
PURPOSE_NEXT = (76, 551)
DATE_CELL = (471, 553)
TIME_CELL = (97, 138)
TRIP_DAYS = (281, 324)
TRIP_HOURS = (353, 402)
ALLOWANCE_TYPE = (167, 310)
DAYS_CELL = (351, 387)
AMOUNT_CELL = (444, 521)
WORDS_CELL = (176, 378)
EVIDENCE_CELL = (111, 175)
SIGNER_CELL = (279, 434)
BOX_OFFICE_X = 284.4  # กลางช่องสี่เหลี่ยม "สำนักงาน"
BOX_SELF_X = 393.9  # กลางช่องสี่เหลี่ยม "ข้าพเจ้า"
BOX_HALF = 6
BOX_RISE = 12.8

# y (จากบน) ของแต่ละบรรทัดหน้า 1 ฟอร์มเบี้ยเลี้ยงมีบรรทัดเส้นประเพิ่ม 1 บรรทัดก่อนถึงส่วนวันเดินทาง
PAGE1_ROWS = {
    "memo": 252.1,
    "name": 273.9,
    "with": 295.7,
    "purpose": 339.3,
    "depart_date": 404.7,
    "depart_time": 426.5,
    "return_date": 426.5,
    "return_time": 448.3,
    "duration": 448.3,
    "subject": 476.1,
    "allowance": 497.4,
    "lodging": 519.2,
    "vehicle": 541.0,
    "other": 562.8,
    "total": 584.6,
    "evidence": 633.7,
    "signer": 707.3,
}
PAGE1_SHIFT = {"travel": 0, "allowance": LINE_STEP}
  # ไม่เลื่อนตามฟอร์ม

# หน้า 2 (ส่วนรับเงิน): y ของบรรทัด
PAGE2_ROWS = {
    "travel": {"received": 342.9, "words": 364.7, "payee": 426.3},
    "allowance": {"received": 364.2, "words": 386.0, "payee": 447.6},
}
PAGE2_RECEIVED_CELL = (437, 516)
PAGE2_WORDS_CELL = (74, 360)
PAGE2_PAYEE_CELL = (121, 267)

# หน้า 3: ใบสำคัญรับเงิน (เฉพาะฟอร์ม travel)
RECEIPT_NAME = (209, 366)
RECEIPT_NAME_LINE = 139.0  # บรรทัดจุดไข่ปลาที่เป็นตัวอักษร: ยกตัวหนังสือให้อยู่เหนือจุดเล็กน้อย
RECEIPT_ITEM_X = 110
RECEIPT_FIRST_ROW = 285.0
RECEIPT_AMOUNT_RIGHT = 503
RECEIPT_SATANG_CENTER = 520.5
RECEIPT_TOTAL_LINE = 546.0
RECEIPT_WORDS = (162, 445)
RECEIPT_WORDS_LINE = 613.0


def _register_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def _fitted_size(text, width):
    size = FONT_SIZE
    while size > MIN_FONT_SIZE and pdfmetrics.stringWidth(text, FONT_NAME, size) > width:
        size -= 0.5
    return size


def put(pdf, text, cell, line, align="center"):
    """พิมพ์ text ลงช่อง cell=(x0, x1) บนเส้น y=line (จากบน) ย่อขนาดตัวอักษรถ้าไม่พอดี"""
    text = str(text)
    if not text:
        return
    x0, x1 = cell
    width = x1 - x0 - 4
    size = _fitted_size(text, width)
    pdf.setFont(FONT_NAME, size)
    y = PAGE_HEIGHT - line + BASELINE_RAISE
    if align == "right":
        pdf.drawRightString(x1 - 2, y, text)
    elif align == "left":
        pdf.drawString(x0 + 2, y, text)
    else:
        pdf.drawCentredString((x0 + x1) / 2, y, text)


def check(pdf, center_x, row_line):
    """ติ๊กถูกในช่องสี่เหลี่ยมของบรรทัดที่เส้นประอยู่ y=row_line (กลางช่องอยู่เหนือเส้นประ BOX_RISE)"""
    center_y = PAGE_HEIGHT - row_line + BOX_RISE
    pdf.setLineWidth(1.4)
    pdf.line(
        center_x - BOX_HALF * 0.7,
        center_y,
        center_x - BOX_HALF * 0.2,
        center_y - BOX_HALF * 0.6,
    )
    pdf.line(
        center_x - BOX_HALF * 0.2,
        center_y - BOX_HALF * 0.6,
        center_x + BOX_HALF * 0.8,
        center_y + BOX_HALF * 0.8,
    )


def _wrap(text, widths):
    """ตัดข้อความเป็นหลายบรรทัดตามความกว้างของแต่ละบรรทัด (ภาษาไทยไม่มีช่องว่างจึงตัดตามตัวอักษร)"""
    combining = set("ะัาิีึืุูเแโใไ็่้๊๋์ํ")  # ห้ามขึ้นบรรทัดใหม่ด้วยอักขระกลุ่มนี้ที่ต้องติดตัวก่อนหน้า
    lines, current = [], ""
    for char in text:
        candidate = current + char
        limit = widths[min(len(lines), len(widths) - 1)]
        too_wide = pdfmetrics.stringWidth(candidate, FONT_NAME, FONT_SIZE) > limit
        if too_wide and current and char not in combining:
            space = current.rfind(" ")
            if space > len(current) // 2:  # ตัดที่ช่องว่างถ้าไม่ทำให้บรรทัดสั้นเกินไป
                lines.append(current[:space].strip())
                current = current[space + 1 :] + char
            else:
                lines.append(current.strip())
                current = char
        else:
            current = candidate
    if current.strip():
        lines.append(current.strip())
    return lines


def money(value):
    return template_filters.format_amount(value)


def _count(value):
    return f"{value.normalize():f}" if value else ""


def _reservation_page1(pdf, doc, reservation, data):
    shift = PAGE1_SHIFT[doc]
    rows = {
        key: line if key in ("memo", "name", "with") else line + shift
        for key, line in PAGE1_ROWS.items()
    }
    put(pdf, data.memo_number, MEMO_NUMBER, rows["memo"], "left")
    if data.memo_date:
        put(pdf, thai_date(data.memo_date), MEMO_DATE, rows["memo"])
    put(pdf, reservation.driver.get_name() if reservation.driver else "", NAME, rows["name"])
    put(pdf, reservation.extra_travelers, WITH_CELL, rows["with"], "left")

    purpose = f"{reservation.request_reason} ณ {reservation.location}".strip()
    first_width = PURPOSE_FIRST[1] - PURPOSE_FIRST[0] - 4
    next_width = PURPOSE_NEXT[1] - PURPOSE_NEXT[0] - 4
    lines = _wrap(purpose, [first_width, next_width])[:3]
    for index, text in enumerate(lines):
        cell = PURPOSE_FIRST if index == 0 else PURPOSE_NEXT
        put(pdf, text, cell, rows["purpose"] + LINE_STEP * index, "left")

    departure = reservation.departure_datetime
    arrival = reservation.return_datetime or departure
    check(pdf, BOX_OFFICE_X, rows["depart_date"])  # เดินทางจาก: สำนักงาน
    check(pdf, BOX_OFFICE_X, rows["return_date"])  # กลับถึง: สำนักงาน
    put(pdf, thai_date(departure), DATE_CELL, rows["depart_date"])
    put(pdf, thai_time(departure), TIME_CELL, rows["depart_time"])
    put(pdf, thai_date(arrival), DATE_CELL, rows["return_date"])
    put(pdf, thai_time(arrival), TIME_CELL, rows["return_time"])
    days, hours = trip_duration(reservation)
    put(pdf, days, TRIP_DAYS, rows["duration"])
    put(pdf, hours, TRIP_HOURS, rows["duration"])
    check(pdf, BOX_SELF_X, rows["subject"])  # เบิกสำหรับ: ข้าพเจ้า

    if data.allowance_amount:
        put(pdf, data.allowance_type, ALLOWANCE_TYPE, rows["allowance"])
        put(pdf, _count(data.allowance_days), DAYS_CELL, rows["allowance"])
        put(pdf, money(data.allowance_amount), AMOUNT_CELL, rows["allowance"], "right")
    if data.lodging_amount:
        put(pdf, _count(data.lodging_days), DAYS_CELL, rows["lodging"])
        put(pdf, money(data.lodging_amount), AMOUNT_CELL, rows["lodging"], "right")
    if data.vehicle_cost:
        put(pdf, money(data.vehicle_cost), AMOUNT_CELL, rows["vehicle"], "right")
    if data.meal_total:
        put(pdf, money(data.meal_total), AMOUNT_CELL, rows["other"], "right")
    put(pdf, thai_baht_text(data.total), WORDS_CELL, rows["total"])
    put(pdf, money(data.total), AMOUNT_CELL, rows["total"], "right")
    if data.evidence_count:
        put(pdf, data.evidence_count, EVIDENCE_CELL, rows["evidence"])
    put(pdf, reservation.driver.get_name() if reservation.driver else "", SIGNER_CELL, rows["signer"])


def _reservation_page2(pdf, doc, reservation, data):
    rows = PAGE2_ROWS[doc]
    put(pdf, money(data.total), PAGE2_RECEIVED_CELL, rows["received"], "right")
    put(pdf, f"({thai_baht_text(data.total)})", PAGE2_WORDS_CELL, rows["words"])
    put(pdf, reservation.driver.get_name() if reservation.driver else "", PAGE2_PAYEE_CELL, rows["payee"])


def _receipt_page(pdf, reservation, data):
    put(pdf, reservation.driver.get_name() if reservation.driver else "", RECEIPT_NAME, RECEIPT_NAME_LINE)
    for index, (rate, days) in enumerate(data.meal_rows):
        line = RECEIPT_FIRST_ROW + LINE_STEP * index
        description = f"เงินช่วยเหลือค่าอาหาร พขร. ({money(rate)} บาท x {_count(days)} วัน)"
        pdf.setFont(FONT_NAME, FONT_SIZE)
        pdf.drawString(RECEIPT_ITEM_X, PAGE_HEIGHT - line + BASELINE_RAISE, description)
        _amount_with_satang(pdf, rate * days, line)
    _amount_with_satang(pdf, data.total, RECEIPT_TOTAL_LINE)
    put(pdf, f"{thai_baht_text(data.total)}", RECEIPT_WORDS, RECEIPT_WORDS_LINE)


def _amount_with_satang(pdf, amount, line):
    """ช่องจำนวนเงินของใบสำคัญรับเงิน: บาทชิดขวา และช่องสตางค์ (ไม่มีสตางค์ใส่ -)"""
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    baht = int(amount)
    satang = int((amount - baht) * 100)
    y = PAGE_HEIGHT - line + BASELINE_RAISE
    pdf.setFont(FONT_NAME, FONT_SIZE)
    pdf.drawRightString(RECEIPT_AMOUNT_RIGHT, y, f"{baht:,}")
    pdf.drawCentredString(RECEIPT_SATANG_CENTER, y, f"{satang:02d}" if satang else "-")


def render(doc, reservation, data):
    """PDF (bytes) ของเอกสาร doc ("travel" | "allowance") ของใบขอที่เสร็จสิ้นแล้ว"""
    _register_font()
    base = PdfReader(str(FORMS_DIR / DOCUMENT_PDFS[doc]))
    overlays = {}
    for page_number in range(len(base.pages)):
        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=(PAGE_WIDTH, PAGE_HEIGHT))
        if page_number == 0:
            _reservation_page1(pdf, doc, reservation, data)
        elif page_number == 1:
            _reservation_page2(pdf, doc, reservation, data)
        else:
            _receipt_page(pdf, reservation, data)
        pdf.save()
        buffer.seek(0)
        overlays[page_number] = PdfReader(buffer).pages[0]

    writer = PdfWriter()
    for page_number, page in enumerate(base.pages):
        page.merge_page(overlays[page_number])
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
