import datetime
import re
from io import BytesIO

import pytest
from PyPDF2 import PdfReader
from reportlab.pdfgen import canvas

from kampan import models
from kampan.utils import car_form_keys, car_form_paper, car_form_seeds
from kampan.utils.car_form_catalog import CATALOG

# ลำดับ field/step ที่ seed กำหนดไว้ (ชื่ออ่านง่าย) ส่วน key จริงหลัง seed เป็นค่าสุ่ม
# ฟิลด์ custom เขียนเป็น "custom_xxx" เหมือน details_key()
SEED_DETAILS_KEYS = {
    "physical_domestic": [
        "vehicle_kind",
        "vehicle_count",
        "district",
        "province",
        "cost_responsibility",
        "custom_project_no",
    ],
    "physical_abroad": [
        "vehicle_kind",
        "vehicle_count",
        "custom_doc_no",
        "custom_city_state",
        "custom_country",
        "custom_pickup",
        "custom_coordinator",
        "custom_coordinator_phone",
        "custom_requester_position",
    ],
    "physical_airport": [
        "custom_transfer",
        "custom_flight_no",
        "custom_flight_date",
        "custom_arrive_time",
        "custom_depart_time",
        "custom_pickup",
        "custom_requester_position",
        *[f"custom_p{n}_{part}" for n in range(1, 6) for part in ("name", "phone")],
        "cost_responsibility",
    ],
    "physical_welfare": [
        "custom_employee_type",
        "vehicle_kind",
        "custom_event_type",
        "custom_event_owner",
        "custom_house",
        "custom_subdistrict",
        "district",
        "province",
        "custom_pickup",
    ],
    "diis_general": ["custom_pickup"],
    "diis_airport": [
        "custom_transfer",
        "custom_flight_no",
        "custom_flight_time",
        "custom_pickup",
    ],
    "diis_out_of_town": ["custom_pickup"],
}
SEED_STEP_KEYS = {
    "physical_domestic": ["head", "admin", "approver", "director"],
    "physical_abroad": ["head", "admin", "director"],
    "physical_airport": ["admin", "approver"],
    "physical_welfare": ["head", "admin", "approver"],
    "diis_general": ["head", "admin"],
    "diis_airport": ["head", "admin"],
    "diis_out_of_town": ["head", "admin", "director"],
}


class SeededKeys:
    """แปลงชื่ออ่านง่ายของ field/step ที่ seed กำหนด (เช่น approvals.head.name, details.custom_pickup)
    เป็น key จริงของ template ที่ seed แล้ว โดยจับคู่ตามตำแหน่งใน template.fields / template.steps"""

    def __init__(self, template, key):
        readable_fields = SEED_DETAILS_KEYS[key]
        readable_steps = SEED_STEP_KEYS[key]
        assert len(template.fields) == len(readable_fields)
        assert len(template.steps) == len(readable_steps)
        self._details = {}
        for field, readable in zip(template.fields, readable_fields):
            if field.source == "catalog":
                assert field.key == readable
            else:
                assert readable.startswith("custom_")
                assert car_form_keys.is_generated(field.key, "f")
            self._details[readable] = field.details_key()
        self._steps = {}
        for step, readable in zip(template.steps, readable_steps):
            assert car_form_keys.is_generated(step.key, "s")
            self._steps[readable] = step.key

    def details_key(self, readable):
        return self._details[readable]

    def details(self, readable_details):
        return {self._details[k]: v for k, v in readable_details.items()}

    def step_key(self, readable):
        return self._steps[readable]

    def variable(self, readable):
        parts = readable.split(".")
        if parts[0] == "details":
            return f"details.{self._details[parts[1]]}"
        if parts[0] == "approvals":
            return f"approvals.{self._steps[parts[1]]}.{parts[2]}"
        return readable

    def variables(self, readables):
        return {self.variable(r) for r in readables}


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
    SeededKeys(template, "physical_domestic")
    assert [s.label for s in template.steps] == [
        "ผู้บังคับบัญชาผู้ขอใช้รถ",
        "ผู้จัดรถบริการ",
        "ผู้อนุมัติ",
        "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
    ]
    assert [(f.source, f.label if f.source == "custom" else f.key) for f in template.fields] == [
        ("catalog", "vehicle_kind"),
        ("catalog", "vehicle_count"),
        ("catalog", "district"),
        ("catalog", "province"),
        ("catalog", "cost_responsibility"),
        ("custom", "เลขที่โครงการ/หนังสือ"),
    ]
    approver_step = template.steps[2]
    assert approver_step.approver_type == "user"
    assert approver_step.user.id == approver.id


@pytest.mark.parametrize("key", sorted(car_form_seeds.TEMPLATE_KEYS))
def test_a_seeded_template_uses_the_same_generated_key_format_as_one_built_in_the_web_ui(
    app, create_org, key
):
    """seed template: custom field key เป็น f_xxxxxx, step key เป็น s_xxxxxx, catalog key ไม่เปลี่ยน และทุก placement ยังชี้ไปที่ field/step ที่มีอยู่จริง"""
    pdf_bytes = blank_diis_pdf() if key.startswith("diis") else blank_a4_pdf()

    template = car_form_seeds.seed_template(create_org(name="DIIS"), key, pdf_bytes=pdf_bytes)

    template.validate()
    custom_keys = {f.key for f in template.fields if f.source == "custom"}
    step_keys = {s.key for s in template.steps}
    assert all(re.fullmatch(r"f_[a-z0-9]{6}", k) for k in custom_keys)
    assert all(re.fullmatch(r"s_[a-z0-9]{6}", k) for k in step_keys)
    assert all(
        f.key in CATALOG for f in template.fields if f.source == "catalog"
    )
    referenced_fields = {
        p.variable[len("details.custom_") :]
        for p in template.placements
        if p.variable.startswith("details.custom_")
    }
    referenced_steps = {
        p.variable.split(".")[1] for p in template.placements if p.variable.startswith("approvals.")
    }
    assert referenced_fields <= custom_keys
    assert referenced_steps and referenced_steps <= step_keys


def test_seeding_twice_does_not_create_duplicate_template(app, create_org):
    """seed template เดิมซ้ำใน org เดียวกัน ต้องคืน template เดิมและไม่เพิ่มจำนวน"""
    org = create_org(name="กองกายภาพ")

    first = car_form_seeds.seed_template(org, "physical_domestic")
    second = car_form_seeds.seed_template(org, "physical_domestic")

    assert second.id == first.id
    assert models.car_form_templates.CarFormTemplate.objects(organization=org).count() == 1


DIIS_HEAD_ADMIN = [
    ("head", True, False),
    ("admin", False, True),
]


@pytest.mark.parametrize(
    "key, name, fields, steps",
    [
        (
            "diis_general",
            "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)",
            [("text", "สถานที่ให้ไปรับ", False, [])],
            DIIS_HEAD_ADMIN,
        ),
        (
            "diis_airport",
            "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (รับ-ส่งสนามบิน)",
            [
                ("radio", "ประเภทการเดินทาง", True, ["ส่ง", "รับ"]),
                ("text", "เที่ยวบิน", True, []),
                ("text", "เวลาเครื่องออก/ถึง", False, []),
                ("text", "สถานที่ให้ไปรับ", False, []),
            ],
            DIIS_HEAD_ADMIN,
        ),
        (
            "diis_out_of_town",
            "ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ไปต่างจังหวัด)",
            [("text", "สถานที่ให้ไปรับ", False, [])],
            DIIS_HEAD_ADMIN + [("director", False, False)],
        ),
    ],
)
def test_seeding_a_diis_template_creates_valid_template_with_its_fields_and_approval_steps(
    app, create_org, key, name, fields, steps
):
    """seed diis_*: ชื่อ/field/ขั้นอนุมัติตรงกับใบขอใช้รถของสำนักนวัตกรรมดิจิทัลฯ แต่ละแบบ"""
    template = car_form_seeds.seed_template(create_org(name="DIIS"), key)

    template.validate()
    SeededKeys(template, key)
    assert template.name == name
    assert [
        (f.field_type, f.label, f.is_required, list(f.choices)) for f in template.fields
    ] == fields
    assert [(s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == steps


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
    keys = SeededKeys(template, "physical_domestic")
    assert keys.variables(
        ["app.location", "details.province", "approvals.head.name"]
    ) <= {p.variable for p in template.placements}


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
    keys = SeededKeys(template, "physical_abroad")
    assert [(s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", True, False),
        ("admin", False, True),
        ("director", False, False),
    ]
    assert [f.label for f in template.fields if f.source == "custom"] == [
        "เลขที่หนังสือ (ที่)",
        "เมือง/รัฐ",
        "ประเทศ",
        "ให้รถไปจอดรอรับที่",
        "ผู้ประสานงาน",
        "โทรผู้ประสานงาน",
        "ตำแหน่งผู้ขอ",
    ]
    assert [f.details_key() for f in template.fields if f.is_required] == [
        keys.details_key(k)
        for k in ["vehicle_kind", "vehicle_count", "custom_city_state", "custom_country"]
    ]
    assert template.paper_file.page_sizes == [[595.32, 841.92]]
    assert keys.variables(
        [
            "app.division",
            "details.custom_country",
            "app.departure.month_th",
            "approvals.head.name",
            "approvals.admin.name",
            "approvals.director.name",
        ]
    ) <= {p.variable for p in template.placements}


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
    keys = SeededKeys(template, "physical_airport")
    assert [(s.approver_type, s.assigns_vehicle) for s in template.steps] == [
        ("role", True),
        ("user", False),
    ]
    assert template.steps[1].user.id == approver.id
    assert [f.label for f in template.fields[:7]] == [
        "ต้องการให้รถไป",
        "เที่ยวบินที่",
        "วันที่บิน",
        "เวลาเครื่องบินถึงสนามบิน",
        "เวลาเครื่องบินออกจากสนามบิน",
        "ให้รถไปรับที่",
        "ตำแหน่งผู้ขอ",
    ]
    assert [f.label for f in template.fields[7:-1]] == [
        label
        for n in range(1, 6)
        for label in (f"ผู้โดยสารคนที่ {n}", f"โทรผู้โดยสารคนที่ {n}")
    ]
    assert template.fields[-1].key == "cost_responsibility"
    assert template.fields[0].choices == ["รับ", "ส่ง"]
    assert template.fields[-1].choices == ["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง", "ไม่รับผิดชอบ"]
    placed = {(p.variable, p.match_value) for p in template.placements}
    assert {
        (keys.variable("details.custom_transfer"), "รับ"),
        (keys.variable("details.custom_transfer"), "ส่ง"),
        ("app.car_type", "เก๋ง"),
        ("app.car_type", "ตู้"),
        ("details.cost_responsibility", "ไม่รับผิดชอบ"),
        (keys.variable("approvals.approver.name"), ""),
    } <= placed


def test_seeding_physical_airport_without_approver_user_falls_back_to_role_endorser(
    app, create_org
):
    """seed physical_airport ไม่ระบุ approver_user: ขั้น approver เป็น role endorser"""
    template = car_form_seeds.seed_template(create_org(name="กองกายภาพ"), "physical_airport")

    template.validate()
    SeededKeys(template, "physical_airport")
    approver_step = template.steps[1]
    assert (approver_step.label, approver_step.approver_type, approver_step.role) == (
        "ผู้อนุมัติ",
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
    keys = SeededKeys(template, "physical_welfare")
    assert [(s.approver_type, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("role", True, False),
        ("role", False, True),
        ("user", False, False),
    ]
    assert template.steps[2].user.id == approver.id
    assert [f.label for f in template.fields if f.source == "custom"] == [
        "ประเภทบุคลากร",
        "เนื่องในงาน",
        "ของ (เจ้าภาพ/ผู้ที่เกี่ยวข้อง)",
        "สถานที่ไปบ้าน",
        "ตำบล",
        "ให้รถไปจอดรอรับที่",
    ]
    assert [f.key for f in template.fields if f.source == "catalog"] == [
        "vehicle_kind",
        "district",
        "province",
    ]
    assert template.fields[0].choices == [
        "พนักงานมหาวิทยาลัย",
        "ลูกจ้างประจำ",
        "พนักงานเงินรายได้",
    ]
    assert template.fields[1].choices == ["บัส", "ตู้"]
    assert template.fields[2].choices == ["อุปสมบท", "มงคลสมรส", "ฌาปณกิจศพ"]
    assert [f.details_key() for f in template.fields if f.is_required] == [
        keys.details_key(k)
        for k in ["custom_employee_type", "vehicle_kind", "custom_event_type", "province"]
    ]
    placed = {(p.variable, p.match_value) for p in template.placements}
    assert {
        (keys.variable("details.custom_employee_type"), "ลูกจ้างประจำ"),
        ("details.vehicle_kind", "ตู้"),
        (keys.variable("details.custom_event_type"), "ฌาปณกิจศพ"),
        ("app.car_type", "บัส"),
        ("details.province", ""),
        (keys.variable("approvals.head.name"), ""),
        (keys.variable("approvals.approver.name"), ""),
    } <= placed


def test_seeding_physical_welfare_without_approver_user_falls_back_to_role_endorser(
    app, create_org
):
    """seed physical_welfare ไม่ระบุ approver_user: ขั้น approver เป็น role endorser"""
    template = car_form_seeds.seed_template(create_org(name="กองกายภาพ"), "physical_welfare")

    template.validate()
    SeededKeys(template, "physical_welfare")
    approver_step = template.steps[2]
    assert (approver_step.label, approver_step.approver_type, approver_step.role) == (
        "ผู้อนุมัติการขอใช้รถ",
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
    keys = SeededKeys(template, key)
    requester = create_user("Somchai", "Jaidee")
    assign_user_to_org(requester, org, roles=["staff"])
    application = models.vehicle_applications.CarApplication(
        organization=org,
        creator=requester,
        car=create_car(org, license_plate="กข-1234"),
        phone="0812345678",
        departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
        return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
        details=keys.details(details),
        template_snapshot={
            "paper_file_id": str(template.paper_file.id),
            "placements": [dict(p.to_mongo()) for p in template.placements],
        },
    )
    application.save()

    text = PdfReader(BytesIO(car_form_paper.render_pdf(application))).pages[0].extract_text()

    assert expected_text in text


def blank_diis_pdf():
    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=(594.96, 841.92))
    pdf.drawString(50, 800, "DIIS FORM")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


DIIS_COMMON_VARIABLES = {
    "app.created.day",
    "app.created.month_th",
    "app.created.year_be",
    "app.requester_name",
    "app.division",
    "app.phone",
    "app.location",
    "app.departure.time",
    "app.passenger_number",
    "approvals.head.name",
    "approvals.head.date",
    "approvals.admin.name",
    "approvals.admin.date",
}
DIIS_PLACEMENT_EXPECTATIONS = {
    "diis_general": DIIS_COMMON_VARIABLES
    | {
        "app.request_reason",
        "app.return.time",
        "details.custom_pickup",
        "app.car_plate",
        "app.driver_name",
        "approvals.admin.decision",
        "approvals.admin.comment",
    },
    "diis_airport": DIIS_COMMON_VARIABLES
    | {
        "details.custom_transfer",
        "details.custom_flight_no",
        "details.custom_flight_time",
        "details.custom_pickup",
        "app.car_plate",
        "app.driver_name",
        "approvals.admin.decision",
        "approvals.admin.comment",
    },
    "diis_out_of_town": DIIS_COMMON_VARIABLES
    | {
        "app.request_reason",
        "app.return.day",
        "app.return.time",
        "details.custom_pickup",
        "app.car_plate",
        "app.driver_name",
        "approvals.director.name",
        "approvals.director.date",
        "approvals.director.decision",
        "approvals.director.comment",
    },
}


@pytest.mark.parametrize("key", sorted(DIIS_PLACEMENT_EXPECTATIONS))
def test_seeding_a_diis_template_with_a_pdf_places_its_values_and_every_placement_validates(
    app, create_org, key
):
    """seed diis_* พร้อม PDF: paper_file เก็บ PDF, placements ผ่าน validate และครอบคลุมตัวแปรที่ใบนั้นต้องพิมพ์"""
    pdf_bytes = blank_diis_pdf()

    template = car_form_seeds.seed_template(create_org(name="DIIS"), key, pdf_bytes=pdf_bytes)

    template.validate()
    assert bytes(template.paper_file.data) == pdf_bytes
    keys = SeededKeys(template, key)
    assert keys.variables(DIIS_PLACEMENT_EXPECTATIONS[key]) <= {
        p.variable for p in template.placements
    }


@pytest.mark.parametrize(
    "key, details, expected_text",
    [
        ("diis_general", {"custom_pickup": "หน้าตึกอธิการ"}, "หน้าตึกอธิการ"),
        ("diis_airport", {"custom_transfer": "ส่ง", "custom_flight_no": "TG123"}, "TG123"),
        ("diis_out_of_town", {"custom_pickup": "หน้าตึกอธิการ"}, "หน้าตึกอธิการ"),
    ],
)
def test_a_seeded_diis_paper_renders_a_filled_pdf_containing_a_value_from_the_request(
    app, create_org, create_user, assign_user_to_org, create_car, key, details, expected_text
):
    """คำขอจาก template DIIS ที่ seed พร้อม PDF: render_pdf ได้ PDF ที่มีค่าที่ผู้ขอกรอก"""
    org = create_org(name="DIIS")
    template = car_form_seeds.seed_template(org, key, pdf_bytes=blank_diis_pdf())
    keys = SeededKeys(template, key)
    requester = create_user("Somchai", "Jaidee")
    assign_user_to_org(requester, org, roles=["staff"])
    application = models.vehicle_applications.CarApplication(
        organization=org,
        creator=requester,
        car=create_car(org, license_plate="กษ-9318"),
        phone="0812345678",
        location="ศูนย์ประชุมนานาชาติ",
        departure_datetime=datetime.datetime(2026, 11, 3, 8, 30),
        return_datetime=datetime.datetime(2026, 11, 3, 17, 0),
        details=keys.details(details),
        template_snapshot={
            "paper_file_id": str(template.paper_file.id),
            "placements": [dict(p.to_mongo()) for p in template.placements],
        },
    )
    application.save()

    text = PdfReader(BytesIO(car_form_paper.render_pdf(application))).pages[0].extract_text()

    assert expected_text in text
