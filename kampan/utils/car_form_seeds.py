from io import BytesIO

from PyPDF2 import PdfReader

from kampan import models

cft = models.car_form_templates

def _physical_domestic(approver_user):
    if approver_user is not None:
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="user",
            user=approver_user,
        )
    else:
        # ไม่ระบุตัวผู้อนุมัติ: fallback เป็น role endorser (ต้องระบุตัวคนภายหลัง)
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="role",
            role="endorser",
        )
    return dict(
        name="ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ",
        fields=[
            cft.FormFieldDef(source="catalog", key="vehicle_kind", is_required=True),
            cft.FormFieldDef(source="catalog", key="vehicle_count"),
            cft.FormFieldDef(source="catalog", key="district"),
            cft.FormFieldDef(source="catalog", key="province", is_required=True),
            cft.FormFieldDef(source="catalog", key="cost_responsibility"),
            cft.FormFieldDef(
                source="custom",
                key="project_no",
                label="เลขที่โครงการ/หนังสือ",
                field_type="text",
            ),
        ],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="ผู้บังคับบัญชาผู้ขอใช้รถ",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
            approver_step,
            cft.ApprovalStepDef(
                key="director",
                label="ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
                approver_type="role",
                role="director",
            ),
        ],
    )


def _diis_general(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)",
        fields=[],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="หัวหน้าฝ่าย",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้ควบคุมยานพาหนะ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
        ],
    )


# ตำแหน่งบนใบขอใช้รถยนต์ฯ ต้นฉบับ (A4 595.32x841.92 pt) วัดจาก `pdftotext -bbox-layout`
# แต่ละรายการ: (variable, x, y, w, align) หน่วย pt มุมบนซ้าย
_PAGE_W, _PAGE_H = 595.32, 841.92
_BOX_H = 14
_DOT_TO_BOX_TOP = 13.2  # baseline ของตัวอักษร 14pt อยู่ต่ำกว่าขอบบนกล่องประมาณนี้
_VEHICLE_KIND_CHECKS = {"บัส": 191.0, "ตู้": 231.9, "เก๋ง": 266.8, "มินิบัส": 305.7}
_COST_CHECKS = {
    "ค่าน้ำมันเชื้อเพลิง": 170.4,
    "เบี้ยเลี้ยง": 253.5,
    "ค่าที่พักของพนักงานขับรถ": 304.4,
    "ไม่รับผิดชอบ": 425.3,
}
# y ในตารางนี้คือระดับเส้นจุดไข่ปลา (วัดจากภาพ raster ของ PDF) ไม่ใช่ขอบบนของกล่อง
_TEXT_PLACEMENTS = [
    ("app.created.day", 372, 113.0, 30, "center"),
    ("app.created.month_th", 421, 113.0, 54, "center"),
    ("app.created.year_be", 497, 113.0, 40, "center"),
    ("app.division", 168, 169.4, 235, "left"),
    ("app.phone", 480, 169.4, 57, "left"),
    ("details.vehicle_count", 161, 202.8, 26, "center"),
    ("app.passenger_number", 247, 202.8, 31, "center"),
    ("app.location", 369, 202.8, 168, "left"),
    ("details.district", 85, 218.6, 75, "left"),
    ("details.province", 197, 218.6, 83, "left"),
    ("app.request_reason", 322, 218.6, 215, "left"),
    ("app.departure.day", 84, 234.5, 16, "center"),
    ("app.departure.month_th", 103, 234.5, 47, "center"),
    ("app.departure.year_be", 153, 234.5, 30, "center"),
    ("app.departure.time", 477, 234.5, 48, "center"),
    ("app.return.day", 225, 250.3, 20, "center"),
    ("app.return.month_th", 247, 250.3, 50, "center"),
    ("app.return.year_be", 299, 250.3, 27, "center"),
    ("app.return.time", 383, 250.3, 57, "center"),
    ("app.requester_name", 290, 357.1, 114, "center"),
    ("approvals.head.name", 290, 398.6, 113, "center"),
    ("app.car_plate", 390, 463.7, 141, "left"),
    ("app.driver_name", 145, 482.2, 314, "left"),
    ("approvals.admin.name", 297, 585.6, 104, "center"),
    ("approvals.approver.name", 298, 633.1, 104, "center"),
]


def _placement(variable, x, y, w, align="left", kind="text", match_value="", h=_BOX_H):
    return cft.PaperPlacement(
        page=0,
        x=x / _PAGE_W,
        y=y / _PAGE_H,
        w=w / _PAGE_W,
        h=h / _PAGE_H,
        variable=variable,
        kind=kind,
        match_value=match_value,
        font_size=14,
        align=align,
    )


def _physical_domestic_placements():
    placements = [
        _placement(variable, x, dot_y - _DOT_TO_BOX_TOP, w, align)
        for variable, x, dot_y, w, align in _TEXT_PLACEMENTS
    ]
    placements += [
        _placement("details.vehicle_kind", x, 173.3, 10.1, kind="check", match_value=choice, h=17.2)
        for choice, x in _VEHICLE_KIND_CHECKS.items()
    ]
    placements += [
        _placement("details.cost_responsibility", x, 295.4, 10.2, kind="check", match_value=choice, h=17.2)
        for choice, x in _COST_CHECKS.items()
    ]
    placements.append(
        _placement(
            "approvals.director.decision", 272.7, 676.5, 10.1, kind="check", match_value="approved", h=17.1
        )
    )
    return placements


_PLACEMENT_BUILDERS = {"physical_domestic": _physical_domestic_placements}

_BUILDERS = {
    "diis_general": _diis_general,
    "physical_domestic": _physical_domestic,
}
TEMPLATE_KEYS = tuple(_BUILDERS)


def _store_paper_file(organization, pdf_bytes, created_by):
    reader = PdfReader(BytesIO(pdf_bytes))
    paper_file = cft.CarFormPaperFile(
        organization=organization,
        filename="form.pdf",
        data=pdf_bytes,
        page_count=len(reader.pages),
        page_sizes=[
            [float(page.mediabox.width), float(page.mediabox.height)]
            for page in reader.pages
        ],
        uploaded_by=created_by,
    )
    paper_file.save()
    return paper_file


def seed_template(organization, key, created_by=None, approver_user=None, pdf_bytes=None):
    spec = _BUILDERS[key](approver_user)
    existing = cft.CarFormTemplate.objects(
        organization=organization, name=spec["name"]
    ).first()
    if existing:
        return existing
    template = cft.CarFormTemplate(
        organization=organization,
        created_by=created_by,
        last_updated_by=created_by,
        **spec,
    )
    if pdf_bytes is not None:
        template.paper_file = _store_paper_file(organization, pdf_bytes, created_by)
        build_placements = _PLACEMENT_BUILDERS.get(key)
        if build_placements:
            template.placements = build_placements()
    template.save()
    return template
