import pathlib
from io import BytesIO

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from kampan import models

FONT_NAME = "THSarabunNew"
FONT_PATH = (
    pathlib.Path(__file__).resolve().parent.parent / "web/static/fonts/THSarabunNew.ttf"
)
MIN_FONT_SIZE = 8

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


def _thai_date(dt):
    return {"day": dt.day, "month_th": THAI_MONTHS[dt.month - 1], "year_be": dt.year + 543}


def _thai_datetime(dt):
    return {**_thai_date(dt), "time": dt.strftime("%H:%M")}


def _user_name(user):
    return user.get_resources_fullname_th() if user else ""


def _build_app(car_application):
    return {
        "requester_name": _user_name(car_application.creator),
        "division": car_application.division.name if car_application.division else "",
        "phone": car_application.phone,
        "location": car_application.location,
        "request_reason": car_application.request_reason,
        "passenger_number": car_application.passenger_number,
        "car_plate": (car_application.car.license_plate if car_application.car else "") or "",
        "driver_name": _user_name(car_application.driver),
        "departure": _thai_datetime(car_application.departure_datetime),
        "return": _thai_datetime(car_application.return_datetime),
        "created": _thai_date(car_application.created_date),
    }


def _build_approvals(car_application):
    approvals = {}
    for step in car_application.step_approvals:
        decided_at = step.decided_at
        approvals[step.step_key] = {
            "name": _user_name(step.decided_by),
            "date": decided_at.strftime("%d/%m/") + str(decided_at.year + 543) if decided_at else "",
            "decision": step.decision,
            "comment": step.comment,
        }
    return approvals


_DATE_PARTS = ("day", "month_th", "year_be")
APP_VARIABLES = frozenset(
    {
        "app.requester_name",
        "app.division",
        "app.phone",
        "app.location",
        "app.request_reason",
        "app.passenger_number",
        "app.car_plate",
        "app.driver_name",
    }
    | {f"app.{group}.{part}" for group in ("departure", "return") for part in (*_DATE_PARTS, "time")}
    | {f"app.created.{part}" for part in _DATE_PARTS}
)
APPROVAL_PARTS = ("name", "date", "decision", "comment")


def available_variables(template):
    """ชุดตัวแปรที่ placement ของ template นี้อ้างได้ (ตรงกับ context ที่ render_pdf สร้าง)"""
    variables = set(APP_VARIABLES) | {"org.name"}
    variables |= {f"details.{field.details_key()}" for field in template.fields}
    variables |= {
        f"approvals.{step.key}.{part}"
        for step in template.steps
        for part in APPROVAL_PARTS
    }
    return variables


def _build_context(car_application):
    return {
        "app": _build_app(car_application),
        "details": dict(car_application.details or {}),
        "approvals": _build_approvals(car_application),
        "org": {"name": car_application.organization.name},
    }


def _resolve(context, variable):
    value = context
    for part in variable.split("."):
        if not isinstance(value, dict) or part not in value:
            return ""
        value = value[part]
    return "" if value is None else value


def _ensure_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(FONT_PATH)))


def _draw_text(pdf, text, box, font_size, align):
    left, bottom, width, height = box
    size = font_size
    while size > MIN_FONT_SIZE and pdfmetrics.stringWidth(text, FONT_NAME, size) > width:
        size -= 0.5
    pdf.setFont(FONT_NAME, size)
    baseline = bottom + (height - size) / 2 + 0.2 * size
    if align == "center":
        pdf.drawCentredString(left + width / 2, baseline, text)
    elif align == "right":
        pdf.drawRightString(left + width, baseline, text)
    else:
        pdf.drawString(left, baseline, text)


def _draw_check(pdf, box):
    left, bottom, width, height = box
    size = min(width, height)
    cx, cy = left + width / 2, bottom + height / 2
    pdf.setLineWidth(max(1, size / 8))
    path = pdf.beginPath()
    path.moveTo(cx - 0.35 * size, cy)
    path.lineTo(cx - 0.1 * size, cy - 0.3 * size)
    path.lineTo(cx + 0.4 * size, cy + 0.35 * size)
    pdf.drawPath(path, stroke=1, fill=0)


def _is_checked(value, match_value):
    if isinstance(value, (list, tuple)):
        return match_value in value
    return str(value) == match_value


def _draw_overlay(placements, context, page_width, page_height):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(page_width, page_height))
    for item in placements:
        box = (
            item["x"] * page_width,
            page_height - (item["y"] + item["h"]) * page_height,
            item["w"] * page_width,
            item["h"] * page_height,
        )
        value = _resolve(context, item["variable"])
        if item.get("kind", "text") == "check":
            if _is_checked(value, item.get("match_value", "")):
                _draw_check(pdf, box)
        elif value != "":
            _draw_text(
                pdf,
                str(value),
                box,
                item.get("font_size") or 14,
                item.get("align", "left"),
            )
    pdf.showPage()  # a canvas with nothing drawn still needs its (blank) page
    pdf.save()
    buf.seek(0)
    return PdfReader(buf).pages[0]


def render_pdf(car_application):
    """เขียนค่าของคำขอทับ PDF ต้นฉบับตาม placements ใน snapshot; ไม่มี paper_file คืน None"""
    snapshot = car_application.template_snapshot or {}
    paper_file_id = snapshot.get("paper_file_id")
    paper_file = (
        models.car_form_templates.CarFormPaperFile.objects(
            id=paper_file_id, organization=car_application.organization
        ).first()
        if paper_file_id
        else None
    )
    if paper_file is None:
        return None

    _ensure_font()
    context = _build_context(car_application)
    placements = snapshot.get("placements") or []
    reader = PdfReader(BytesIO(paper_file.data))
    writer = PdfWriter()
    for page_index, page in enumerate(reader.pages):
        on_page = [p for p in placements if p.get("page", 0) == page_index]
        if on_page:
            page_width = float(page.mediabox.width)
            page_height = float(page.mediabox.height)
            page.merge_page(_draw_overlay(on_page, context, page_width, page_height))
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
