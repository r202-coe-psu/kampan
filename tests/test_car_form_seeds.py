import datetime
from io import BytesIO

import pytest
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas

from kampan import models
from kampan.utils import car_form_paper, car_form_seeds


def test_seeding_physical_domestic_creates_valid_template_with_ordered_steps_fields_and_bound_approver(
    app, create_org, create_user
):
    """seed physical_domestic: 4 ขั้นเรียง head/admin/approver/director, 5 catalog fields + custom project_no, ขั้น approver ผูกกับ user ที่ส่งมา"""
    org = create_org(name="กองกายภาพ")
    approver = create_user("Wichai", "Approver")

    template = car_form_seeds.seed_template(
        org, "physical_domestic", approver_user=approver
    )

    template.validate()
    assert [s.key for s in template.steps] == ["head", "admin", "approver", "director"]
    assert [(f.source, f.key) for f in template.fields] == [
        ("catalog", "vehicle_kind"),
        ("catalog", "vehicle_count"),
        ("catalog", "district"),
        ("catalog", "province"),
        ("catalog", "cost_responsibility"),
        ("custom", "project_no"),
    ]
    approver_step = template.steps[2]
    assert approver_step.approver_type == "user"
    assert approver_step.user.id == approver.id


def test_seeding_twice_does_not_create_duplicate_template(app, create_org):
    """seed template เดิมซ้ำใน org เดียวกัน ต้องคืน template เดิมและไม่เพิ่มจำนวน"""
    org = create_org(name="กองกายภาพ")

    first = car_form_seeds.seed_template(org, "physical_domestic")
    second = car_form_seeds.seed_template(org, "physical_domestic")

    assert second.id == first.id
    assert models.car_form_templates.CarFormTemplate.objects(organization=org).count() == 1


def test_seeding_diis_general_creates_template_with_head_and_admin_steps_and_no_fields(
    app, create_org
):
    """seed diis_general: ไม่มี detail field, 2 ขั้น head (same_division) -> admin (จัดรถ)"""
    template = car_form_seeds.seed_template(create_org(name="DIIS"), "diis_general")

    template.validate()
    assert template.name == "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)"
    assert len(template.fields) == 0
    assert [(s.key, s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", "head", True, False),
        ("admin", "admin", False, True),
    ]


def blank_a4_pdf(pages=1):
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(595.32, 841.92))
    for _ in range(pages):
        pdf.drawString(50, 800, "FORM")
        pdf.showPage()
    pdf.save()
    return buf.getvalue()


def test_seeding_physical_domestic_with_a_pdf_stores_the_pdf_as_paper_file_and_default_placements_that_validate(
    app, create_org
):
    """seed physical_domestic พร้อม PDF: paper_file เก็บ PDF นั้น (นับหน้า/ขนาดหน้า) และมี placements เริ่มต้นที่ผ่าน validate"""
    pdf_bytes = blank_a4_pdf()

    template = car_form_seeds.seed_template(
        create_org(name="กองกายภาพ"), "physical_domestic", pdf_bytes=pdf_bytes
    )

    template.validate()
    assert bytes(template.paper_file.data) == pdf_bytes
    assert template.paper_file.page_count == 1
    assert template.paper_file.page_sizes == [[595.32, 841.92]]
    assert len(template.placements) > 0
    assert {"app.location", "details.province", "approvals.head.name"} <= {
        p.variable for p in template.placements
    }


def test_seeding_without_a_pdf_still_works_with_no_paper_file_and_no_placements(
    app, create_org
):
    """seed โดยไม่ส่ง PDF: ได้ template เหมือนเดิม ไม่มี paper_file และไม่มี placements"""
    template = car_form_seeds.seed_template(create_org(name="กองกายภาพ"), "physical_domestic")

    template.validate()
    assert template.paper_file is None
    assert len(template.placements) == 0


def test_a_seeded_domestic_template_renders_a_filled_pdf_containing_the_requests_location_and_province(
    app, create_org, create_user, assign_user_to_org, create_car
):
    """คำขอจาก template ที่ seed พร้อม PDF: render_pdf ได้ PDF ที่มีสถานที่และจังหวัดของคำขอ"""
    org = create_org(name="กองกายภาพ")
    template = car_form_seeds.seed_template(
        org, "physical_domestic", pdf_bytes=blank_a4_pdf()
    )
    requester = create_user("Somchai", "Jaidee")
    assign_user_to_org(requester, org, roles=["staff"])
    application = models.vehicle_applications.CarApplication(
        organization=org,
        creator=requester,
        car=create_car(org, license_plate="กข-1234"),
        phone="0812345678",
        location="สนามบินหาดใหญ่",
        request_reason="ไปราชการ",
        departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
        return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
        details={"province": "สงขลา", "district": "หาดใหญ่"},
        template_snapshot={
            "paper_file_id": str(template.paper_file.id),
            "placements": [dict(p.to_mongo()) for p in template.placements],
        },
    )
    application.save()

    text = PdfReader(BytesIO(car_form_paper.render_pdf(application))).pages[0].extract_text()

    assert "สนามบินหาดใหญ่" in text
    assert "สงขลา" in text


def test_seeding_physical_abroad_with_a_pdf_creates_valid_template_with_expected_steps_fields_and_placements(
    app, create_org
):
    """seed physical_abroad พร้อม PDF: ชื่อตรงฟอร์มทางการ, 3 ขั้น head/admin/director, fields ตามฟอร์ม และ placements ที่ผ่าน validate"""
    template = car_form_seeds.seed_template(
        create_org(name="กองกายภาพ"), "physical_abroad", pdf_bytes=blank_a4_pdf()
    )

    template.validate()
    assert template.name == "ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ"
    assert [(s.key, s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", "head", True, False),
        ("admin", "admin", False, True),
        ("director", "director", False, False),
    ]
    assert [f.details_key() for f in template.fields] == [
        "vehicle_kind",
        "vehicle_count",
        "custom_doc_no",
        "custom_city_state",
        "custom_country",
        "custom_pickup",
        "custom_coordinator",
        "custom_coordinator_phone",
        "custom_requester_position",
    ]
    assert [f.key for f in template.fields if f.is_required] == [
        "vehicle_kind",
        "vehicle_count",
        "city_state",
        "country",
    ]
    assert template.paper_file.page_sizes == [[595.32, 841.92]]
    assert {
        "app.division",
        "details.custom_country",
        "app.departure.month_th",
        "approvals.head.name",
        "approvals.admin.name",
        "approvals.director.name",
    } <= {p.variable for p in template.placements}


def test_seeding_physical_airport_with_a_pdf_creates_valid_template_with_expected_steps_fields_and_placements(
    app, create_org, create_user
):
    """seed physical_airport พร้อม PDF: ชื่อตรงฟอร์มทางการ, 2 ขั้น admin -> approver (ผูกคนที่ส่งมา), fields ตามฟอร์ม และ placements ที่ผ่าน validate"""
    approver = create_user("Wichai", "Approver")

    template = car_form_seeds.seed_template(
        create_org(name="กองกายภาพ"),
        "physical_airport",
        approver_user=approver,
        pdf_bytes=blank_a4_pdf(),
    )

    template.validate()
    assert template.name == "ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่"
    assert [(s.key, s.approver_type, s.assigns_vehicle) for s in template.steps] == [
        ("admin", "role", True),
        ("approver", "user", False),
    ]
    assert template.steps[1].user.id == approver.id
    assert [f.details_key() for f in template.fields] == [
        "custom_transfer",
        "custom_flight_no",
        "custom_flight_date",
        "custom_arrive_time",
        "custom_depart_time",
        "custom_pickup",
        "custom_requester_position",
        *[f"custom_p{n}_{part}" for n in range(1, 6) for part in ("name", "phone")],
        "cost_responsibility",
    ]
    assert template.fields[0].choices == ["รับ", "ส่ง"]
    assert template.fields[-1].choices == ["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง", "ไม่รับผิดชอบ"]
    placed = {(p.variable, p.match_value) for p in template.placements}
    assert {
        ("details.custom_transfer", "รับ"),
        ("details.custom_transfer", "ส่ง"),
        ("app.car_type", "เก๋ง"),
        ("app.car_type", "ตู้"),
        ("details.cost_responsibility", "ไม่รับผิดชอบ"),
        ("approvals.approver.name", ""),
    } <= placed


def test_seeding_physical_airport_without_approver_user_falls_back_to_role_endorser(
    app, create_org
):
    """seed physical_airport ไม่ระบุ approver_user: ขั้น approver เป็น role endorser"""
    template = car_form_seeds.seed_template(create_org(name="กองกายภาพ"), "physical_airport")

    template.validate()
    approver_step = template.steps[1]
    assert (approver_step.key, approver_step.approver_type, approver_step.role) == (
        "approver",
        "role",
        "endorser",
    )


def test_seeding_physical_welfare_with_a_pdf_creates_valid_template_with_expected_steps_fields_and_placements(
    app, create_org, create_user
):
    """seed physical_welfare พร้อม PDF: ชื่อตรงฟอร์มทางการ, 3 ขั้น head/admin/approver (ผูกคนที่ส่งมา), fields ตามฟอร์ม และ placements ที่ผ่าน validate"""
    approver = create_user("Wichai", "Approver")

    template = car_form_seeds.seed_template(
        create_org(name="กองกายภาพ"),
        "physical_welfare",
        approver_user=approver,
        pdf_bytes=blank_a4_pdf(),
    )

    template.validate()
    assert template.name == "ใบขอใช้รถประเภทสวัสดิการบุคลากร"
    assert [(s.key, s.approver_type, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", "role", True, False),
        ("admin", "role", False, True),
        ("approver", "user", False, False),
    ]
    assert template.steps[2].user.id == approver.id
    assert [f.details_key() for f in template.fields] == [
        "custom_employee_type",
        "vehicle_kind",
        "custom_event_type",
        "custom_event_owner",
        "custom_house",
        "custom_subdistrict",
        "district",
        "province",
        "custom_pickup",
    ]
    assert template.fields[0].choices == [
        "พนักงานมหาวิทยาลัย",
        "ลูกจ้างประจำ",
        "พนักงานเงินรายได้",
    ]
    assert template.fields[1].choices == ["บัส", "ตู้"]
    assert template.fields[2].choices == ["อุปสมบท", "มงคลสมรส", "ฌาปณกิจศพ"]
    assert [f.key for f in template.fields if f.is_required] == [
        "employee_type",
        "vehicle_kind",
        "event_type",
        "province",
    ]
    placed = {(p.variable, p.match_value) for p in template.placements}
    assert {
        ("details.custom_employee_type", "ลูกจ้างประจำ"),
        ("details.vehicle_kind", "ตู้"),
        ("details.custom_event_type", "ฌาปณกิจศพ"),
        ("app.car_type", "บัส"),
        ("details.province", ""),
        ("approvals.head.name", ""),
        ("approvals.approver.name", ""),
    } <= placed


def test_seeding_physical_welfare_without_approver_user_falls_back_to_role_endorser(
    app, create_org
):
    """seed physical_welfare ไม่ระบุ approver_user: ขั้น approver เป็น role endorser"""
    template = car_form_seeds.seed_template(create_org(name="กองกายภาพ"), "physical_welfare")

    template.validate()
    approver_step = template.steps[2]
    assert (approver_step.key, approver_step.approver_type, approver_step.role) == (
        "approver",
        "role",
        "endorser",
    )


@pytest.mark.parametrize(
    "key, details, expected_text",
    [
        ("physical_abroad", {"custom_country": "มาเลเซีย", "vehicle_kind": "ตู้"}, "มาเลเซีย"),
        ("physical_airport", {"custom_flight_no": "FD3601", "custom_transfer": "รับ"}, "FD3601"),
        (
            "physical_welfare",
            {"custom_subdistrict": "คอหงส์", "province": "สงขลา", "vehicle_kind": "ตู้"},
            "คอหงส์",
        ),
    ],
)
def test_a_seeded_paper_renders_a_filled_pdf_containing_a_value_from_the_request(
    app, create_org, create_user, assign_user_to_org, create_car, key, details, expected_text
):
    """คำขอจาก template ที่ seed พร้อม PDF: render_pdf ได้ PDF ที่มีค่าที่ผู้ขอกรอกในรายละเอียด"""
    org = create_org(name="กองกายภาพ")
    template = car_form_seeds.seed_template(org, key, pdf_bytes=blank_a4_pdf())
    requester = create_user("Somchai", "Jaidee")
    assign_user_to_org(requester, org, roles=["staff"])
    application = models.vehicle_applications.CarApplication(
        organization=org,
        creator=requester,
        car=create_car(org, license_plate="กข-1234"),
        phone="0812345678",
        departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
        return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
        details=details,
        template_snapshot={
            "paper_file_id": str(template.paper_file.id),
            "placements": [dict(p.to_mongo()) for p in template.placements],
        },
    )
    application.save()

    text = PdfReader(BytesIO(car_form_paper.render_pdf(application))).pages[0].extract_text()

    assert expected_text in text
