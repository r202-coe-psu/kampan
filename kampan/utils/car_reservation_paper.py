"""ใบขอใช้รถ (PDF): เติมข้อมูลคำขอลงแบบฟอร์มทางการของแต่ละประเภทด้วย reportlab แล้วซ้อนทับ PDF ต้นฉบับ

ตำแหน่งของแต่ละช่องเป็นค่าคงที่ใน `car_reservation_paper_layouts`; ส่วนนี้สร้างค่า (context) จากคำขอ
แล้ววาดข้อความ เครื่องหมายถูก ภาพลายเซ็นและตราของผู้อนุมัติแต่ละขั้น
"""

from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from kampan.utils import car_reservation_flow as flow
from kampan.utils.car_reservation_paper_layouts import (
    LAYOUTS,
    MIN_FONT_SIZE,
    PAGE_H,
    PAPERS_DIR,
    Sign,
)

FONT_NAME = "THSarabunNew"
FONT_PATH = PAPERS_DIR.parent / "fonts/THSarabunNew.ttf"
BASELINE_LIFT = 6.0  # ข้อความนั่งเหนือเส้นจุด: baseline = ขอบล่างบรรทัด - ค่านี้

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
THAI_MONTHS_SHORT = [
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
]
AIRPORT_CAR_TYPES = ("เก๋ง", "ตู้")


def ensure_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def thai_date(value, short=False):
    months = THAI_MONTHS_SHORT if short else THAI_MONTHS
    return f"{value.day} {months[value.month - 1]} {value.year + 543}"


def _date_parts(prefix, value):
    if value is None:
        return {}
    return {
        f"{prefix}_day": value.day,
        f"{prefix}_month": THAI_MONTHS[value.month - 1],
        f"{prefix}_year": value.year + 543,
    }


def _user_name(user):
    return user.get_name() if user else ""


def _details_context(reservation):
    """ค่าเฉพาะประเภทใบขอ (ชื่อตัวแปรตรงกับฟิลด์ใน `models.car_reservations.*Details`)"""
    details = reservation.details
    if details is None:
        return {}
    context = {
        name: getattr(details, name)
        for name in details._fields_ordered
        if isinstance(getattr(details, name, None), (str, int)) and getattr(details, name) != ""
    }
    context["cost"] = list(getattr(details, "cost_responsibilities", None) or [])
    if reservation.request_type == "abroad":
        context["requester_position"] = details.requester_position
    if reservation.request_type == "airport":
        context.update(_date_parts("flight", details.flight_date))
        context["flight_leg"] = "arrival" if details.arrival_time else "departure"
        for number, passenger in enumerate(details.passengers, start=1):
            context[f"p{number}_name"] = passenger.name
            context[f"p{number}_phone"] = passenger.phone
    return context


def _money(value):
    text = f"{value:,.2f}"
    return text[:-3] if text.endswith(".00") else text


def _trip_report_context(reservation):
    """ช่อง "เลข ก.ม. ออก/กลับ รวมระยะทาง เป็นเงิน" ท้ายใบ: เติมเมื่อ พขร. ปิดงานแล้วเท่านั้น"""
    distance = reservation.distance_km
    if distance is None:
        return {}
    context = {
        "km_out": reservation.last_mileage_before,
        "km_in": reservation.last_mileage,
        "km_total": distance,
    }
    if reservation.cost_baht is not None:
        context["trip_cost"] = _money(reservation.cost_baht)
    start, end = reservation.started_at, reservation.completed_at
    if start and end:
        minutes = max(int((end - start).total_seconds()), 0) // 60
        context.update(
            trip_start_time=start.strftime("%H:%M"),
            trip_end_time=end.strftime("%H:%M"),
            trip_hours=minutes // 60,
            trip_minutes=minutes % 60,
        )
    return context


def build_context(reservation):
    car_type = (reservation.car.vehicle_type if reservation.car else "") or ""
    unit = reservation.requester_unit or (
        reservation.division.name if reservation.division else ""
    )
    context = {
        "requester_name": _user_name(reservation.creator),
        "unit": unit,
        "phone": reservation.phone,
        "location": reservation.location,
        "request_reason": reservation.request_reason,
        "passengers": reservation.passenger_number,
        "pickup_place": reservation.pickup_place,
        "pickup_time": reservation.pickup_time,
        "car_plate": (reservation.car.license_plate if reservation.car else "") or "",
        "car_type": car_type,
        "car_type_other": car_type if car_type not in AIRPORT_CAR_TYPES else "",
        "car_type_is_other": "other" if car_type not in (*AIRPORT_CAR_TYPES, "") else "",
        "driver_name": _user_name(reservation.driver),
        "extra_travelers": reservation.extra_travelers,
        "created": thai_date(reservation.created_date),
        **_date_parts("created", reservation.created_date),
        "dep_time": reservation.departure_datetime.strftime("%H:%M"),
        **_date_parts("dep", reservation.departure_datetime),
    }
    if "physical_director" in reservation.route_snapshot:
        context["route_to_physical_director"] = "yes"  # วงกลม "เรียน O ผู้อำนวยการกองกายภาพ"
    # คำขอเก่าก่อนเก็บ snapshot ไม่มีลายเซ็นของตอนยื่น: ใช้ลายเซ็นปัจจุบันแทน
    requester_signature = reservation.requester_signature or flow.signature_snapshot(
        reservation.creator
    )
    if requester_signature:
        context["requester_signature"] = bytes(requester_signature)
    if reservation.return_datetime:
        context["ret_time"] = reservation.return_datetime.strftime("%H:%M")
        context.update(_date_parts("ret", reservation.return_datetime))
    context.update(_trip_report_context(reservation))
    context.update(_details_context(reservation))
    return context


class Signer:
    """ผู้อนุมัติหนึ่งขั้นที่อนุมัติแล้ว: ข้อมูลที่พิมพ์ในช่องลงนาม"""

    def __init__(self, approval):
        self.position = approval.label or flow.step_label(approval.step_key)
        self.name = _user_name(approval.decided_by)
        self.decided_at = approval.decided_at
        # การอนุมัติก่อนเก็บ snapshot ไม่มีลายเซ็นของตอนอนุมัติ: ใช้ลายเซ็นปัจจุบันแทน
        signature = approval.signature or flow.signature_snapshot(approval.decided_by)
        self.signature = bytes(signature) if signature else None

    def date_text(self, short=False, prefix=False):
        if not self.decided_at:
            return ""
        text = thai_date(self.decided_at, short=short)
        return f"วันที่ {text}" if prefix else text


def approved_signers(reservation):
    return {
        approval.step_key: Signer(approval)
        for approval in reservation.step_approvals
        if approval.decision == "approved"
    }


def _fit(text, width, size):
    while size > MIN_FONT_SIZE and pdfmetrics.stringWidth(text, FONT_NAME, size) > width:
        size -= 0.5
    return size


def _draw_text(pdf, text, x0, x1, y, align, size):
    """วาดข้อความในช่อง x0..x1 บรรทัดที่ขอบล่าง y (ย่อขนาดให้พอดีช่อง)"""
    if text in (None, ""):
        return
    text = str(text)
    size = _fit(text, x1 - x0, size)
    while len(text) > 1 and pdfmetrics.stringWidth(text, FONT_NAME, size) > x1 - x0:
        text = text[:-4] + "..."  # ยังล้นช่องแม้ย่อสุดแล้ว: ตัดท้ายข้อความ (ข้อมูลเต็มอยู่ในหน้าคำขอ)
    pdf.setFont(FONT_NAME, size)
    baseline = PAGE_H - (y - BASELINE_LIFT)
    if align == "center":
        pdf.drawCentredString((x0 + x1) / 2, baseline, text)
    elif align == "right":
        pdf.drawRightString(x1, baseline, text)
    else:
        pdf.drawString(x0, baseline, text)


def _draw_check(pdf, cx, cy):
    size = 11
    y = PAGE_H - cy
    pdf.setLineWidth(1.4)
    path = pdf.beginPath()
    path.moveTo(cx - 0.35 * size, y)
    path.lineTo(cx - 0.1 * size, y - 0.3 * size)
    path.lineTo(cx + 0.45 * size, y + 0.4 * size)
    pdf.drawPath(path, stroke=1, fill=0)


def _is_checked(value, match):
    if isinstance(value, (list, tuple)):
        return match in value
    return str(value) == match


def _draw_image(pdf, data, x0, x1, y_bottom, height):
    pdf.drawImage(
        ImageReader(BytesIO(data)),
        x0,
        PAGE_H - y_bottom,
        width=x1 - x0,
        height=height,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )


def _draw_sign(pdf, sign, signer):
    if sign.check:
        _draw_check(pdf, *sign.check)
    if sign.image and signer.signature:
        _draw_image(pdf, signer.signature, *sign.image)
    if sign.name:
        x0, x1, y, align, size = sign.name
        _draw_text(pdf, signer.name, x0, x1, y, align, size)
    if sign.position:
        x0, x1, y, align, size = sign.position
        _draw_text(pdf, signer.position, x0, x1, y, align, size)
    if sign.date:
        x0, x1, y, align, size = sign.date
        _draw_text(
            pdf,
            signer.date_text(short=sign.date_short, prefix=sign.date_prefix),
            x0,
            x1,
            y,
            align,
            size,
        )


def _draw_overlay(layout, context, signers, page_width, page_height):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    for field in layout.fields:
        _draw_text(
            pdf,
            context.get(field.var, ""),
            field.x0,
            field.x1,
            field.y,
            field.align,
            field.size,
        )
    for check in layout.checks:
        if _is_checked(context.get(check.var, ""), check.match):
            _draw_check(pdf, check.cx, check.cy)
    creator_signature = context.get("requester_signature")
    if layout.requester_image and creator_signature:
        _draw_image(pdf, creator_signature, *layout.requester_image)
    # ขั้นที่แบบฟอร์มจริงไม่มีช่องลงนาม ไม่พิมพ์ (ดูได้ในประวัติการดำเนินการของคำขอ)
    for key, signer in signers.items():
        sign = layout.signs.get(key)
        if isinstance(sign, Sign):
            _draw_sign(pdf, sign, signer)
    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


def render_pdf(reservation):
    """PDF ของแบบฟอร์มตามประเภทใบขอ พร้อมข้อมูลคำขอ ชื่อ/ตำแหน่ง/วันที่และลายเซ็นของขั้นที่อนุมัติแล้ว"""
    ensure_font()
    layout = LAYOUTS[reservation.request_type]
    page = PdfReader(str(PAPERS_DIR / layout.filename)).pages[0]
    overlay = _draw_overlay(
        layout,
        build_context(reservation),
        approved_signers(reservation),
        float(page.mediabox.width),
        float(page.mediabox.height),
    )
    page.merge_page(overlay)
    writer = PdfWriter()
    writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
