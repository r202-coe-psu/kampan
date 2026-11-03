import datetime
from io import BytesIO

import pytest
from PyPDF2 import PdfReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from kampan import models
from kampan.utils import car_form_paper


def blank_pdf(label="FORM", pages=1):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(595, 842))
    for _ in range(pages):
        pdf.drawString(50, 800, label)
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def placement(variable, x=0.1, y=0.1, w=0.5, h=0.03, **extra):
    return {"page": 0, "x": x, "y": y, "w": w, "h": h, "variable": variable, **extra}


def page_text(pdf_bytes):
    return PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text()


@pytest.fixture
def make_application(app, create_org, create_user, assign_user_to_org, create_car):
    def _make(placements, phone="0812345678", details=None, approvers=None):
        org = create_org(name="กองกายภาพ")
        requester = create_user("Somchai", "Jaidee")
        assign_user_to_org(requester, org, roles=["staff"])
        paper_file = models.car_form_templates.CarFormPaperFile(
            organization=org,
            filename="form.pdf",
            data=blank_pdf(),
            page_count=1,
            page_sizes=[[595, 842]],
        )
        paper_file.save()

        step_approvals = [
            models.vehicle_applications.StepApproval(
                step_key=step_key,
                decision="approved",
                decided_by=approver,
                decided_at=decided_at,
            )
            for step_key, approver, decided_at in approvers or []
        ]
        application = models.vehicle_applications.CarApplication(
            organization=org,
            creator=requester,
            car=create_car(org, license_plate="กข-1234"),
            phone=phone,
            location="สนามบินหาดใหญ่",
            request_reason="ไปราชการ",
            departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
            return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
            details=details or {},
            step_approvals=step_approvals,
            template_snapshot={
                "paper_file_id": str(paper_file.id),
                "placements": placements,
            },
        )
        application.save()
        return application

    return _make


def test_paper_pdf_contains_the_requests_values_at_their_placements(
    make_application, create_user
):
    head = create_user("Prasert", "Meesuk")
    application = make_application(
        placements=[
            placement("app.phone", y=0.10),
            placement("details.province", y=0.20),
            placement("approvals.head.name", y=0.30),
        ],
        details={"province": "สงขลา"},
        approvers=[("head", head, datetime.datetime(2026, 11, 2, 10, 0))],
    )

    text = page_text(car_form_paper.render_pdf(application))

    assert "FORM" in text  # the original page is kept underneath
    assert "0812345678" in text
    assert "สงขลา" in text
    assert "Prasert Meesuk" in text


def font_sizes_of(pdf_bytes, needle):
    """Font size used for each text chunk containing `needle`, read back from the PDF."""
    sizes = []

    def visitor(text, cm, tm, font_dict, font_size):
        if needle in text:
            sizes.append(round(font_size * abs(tm[0]) if tm[0] else font_size, 1))

    PdfReader(BytesIO(pdf_bytes)).pages[0].extract_text(visitor_text=visitor)
    return sizes


def test_text_longer_than_its_box_is_shrunk_to_fit_but_still_complete(make_application):
    long_note = "ABCDEFGHIJ" * 4
    details = {"note": long_note}
    wide = make_application([placement("details.note", w=0.9, font_size=14)], details=details)
    narrow = make_application([placement("details.note", w=0.2, font_size=14)], details=details)

    wide_pdf = car_form_paper.render_pdf(wide)
    narrow_pdf = car_form_paper.render_pdf(narrow)

    assert font_sizes_of(wide_pdf, long_note) == [14.0]
    (shrunk,) = font_sizes_of(narrow_pdf, long_note)
    assert 8 <= shrunk < 14
    box_width = 0.2 * 595
    assert pdfmetrics.stringWidth(long_note, "THSarabunNew", shrunk) <= box_width


def drawn_line_segments(pdf_bytes):
    """Number of path line-to operators ('x y l') in the page content: vector strokes such as a check mark."""
    content = PdfReader(BytesIO(pdf_bytes)).pages[0].get_contents().get_data().decode("latin-1")
    return sum(1 for line in content.splitlines() if line.endswith(" l"))


def test_check_placement_is_drawn_only_when_the_value_matches(make_application):
    check = placement(
        "details.vehicle_kind", w=0.03, h=0.02, kind="check", match_value="ตู้"
    )
    matching = make_application([check], details={"vehicle_kind": "ตู้"})
    other = make_application([check], details={"vehicle_kind": "เก๋ง"})
    in_list = make_application(
        [placement("details.tags", w=0.03, h=0.02, kind="check", match_value="b")],
        details={"tags": ["a", "b"]},
    )

    assert drawn_line_segments(car_form_paper.render_pdf(matching)) == 2
    assert drawn_line_segments(car_form_paper.render_pdf(other)) == 0
    assert drawn_line_segments(car_form_paper.render_pdf(in_list)) == 2
