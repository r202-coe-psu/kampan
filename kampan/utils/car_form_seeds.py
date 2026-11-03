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


def _diis_head_admin_steps():
    return [
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
    ]


def _diis_general(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)",
        fields=[_text_field("pickup", "สถานที่ให้ไปรับ")],
        steps=_diis_head_admin_steps(),
    )


def _diis_airport(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (รับ-ส่งสนามบิน)",
        fields=[
            cft.FormFieldDef(
                source="custom",
                key="transfer",
                label="ประเภทการเดินทาง",
                field_type="radio",
                choices=["ส่ง", "รับ"],
                is_required=True,
            ),
            _text_field("flight_no", "เที่ยวบิน", is_required=True),
            _text_field("flight_time", "เวลาเครื่องออก/ถึง"),
            _text_field("pickup", "สถานที่ให้ไปรับ"),
        ],
        steps=_diis_head_admin_steps(),
    )


def _diis_out_of_town(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ไปต่างจังหวัด)",
        fields=[_text_field("pickup", "สถานที่ให้ไปรับ")],
        steps=_diis_head_admin_steps()
        + [
            cft.ApprovalStepDef(
                key="director",
                label="ผู้อำนวยการสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ",
                approver_type="role",
                role="director",
            )
        ],
    )


def _approver_step(approver_user, label):
    if approver_user is not None:
        return cft.ApprovalStepDef(
            key="approver", label=label, approver_type="user", user=approver_user
        )
    # ไม่ระบุตัวผู้อนุมัติ: fallback เป็น role endorser (ต้องระบุตัวคนภายหลัง)
    return cft.ApprovalStepDef(
        key="approver", label=label, approver_type="role", role="endorser"
    )


def _text_field(key, label, is_required=False):
    return cft.FormFieldDef(
        source="custom", key=key, label=label, field_type="text", is_required=is_required
    )


def _physical_abroad(approver_user):
    return dict(
        name="ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ",
        fields=[
            cft.FormFieldDef(source="catalog", key="vehicle_kind", is_required=True),
            cft.FormFieldDef(source="catalog", key="vehicle_count", is_required=True),
            _text_field("doc_no", "เลขที่หนังสือ (ที่)"),
            _text_field("city_state", "เมือง/รัฐ", is_required=True),
            _text_field("country", "ประเทศ", is_required=True),
            _text_field("pickup", "ให้รถไปจอดรอรับที่"),
            _text_field("coordinator", "ผู้ประสานงาน"),
            _text_field("coordinator_phone", "โทรผู้ประสานงาน"),
            _text_field("requester_position", "ตำแหน่งผู้ขอ"),
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
            cft.ApprovalStepDef(
                key="director",
                label="ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
                approver_type="role",
                role="director",
            ),
        ],
    )


def _airport_fields():
    fields = [
        cft.FormFieldDef(
            source="custom",
            key="transfer",
            label="ต้องการให้รถไป",
            field_type="radio",
            choices=["รับ", "ส่ง"],
            is_required=True,
        ),
        _text_field("flight_no", "เที่ยวบินที่", is_required=True),
        cft.FormFieldDef(
            source="custom", key="flight_date", label="วันที่บิน", field_type="date"
        ),
        _text_field("arrive_time", "เวลาเครื่องบินถึงสนามบิน"),
        _text_field("depart_time", "เวลาเครื่องบินออกจากสนามบิน"),
        _text_field("pickup", "ให้รถไปรับที่"),
        _text_field("requester_position", "ตำแหน่งผู้ขอ"),
    ]
    for number in range(1, 6):
        fields.append(_text_field(f"p{number}_name", f"ผู้โดยสารคนที่ {number}"))
        fields.append(_text_field(f"p{number}_phone", f"โทรผู้โดยสารคนที่ {number}"))
    fields.append(
        cft.FormFieldDef(
            source="catalog",
            key="cost_responsibility",
            choices=["ค่าน้ำมันเชื้อเพลิง", "เบี้ยเลี้ยง", "ไม่รับผิดชอบ"],
        )
    )
    return fields


def _physical_airport(approver_user):
    return dict(
        name="ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่",
        fields=_airport_fields(),
        steps=[
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
            _approver_step(approver_user, "ผู้อนุมัติ"),
        ],
    )


def _physical_welfare(approver_user):
    return dict(
        name="ใบขอใช้รถประเภทสวัสดิการบุคลากร",
        fields=[
            cft.FormFieldDef(
                source="custom",
                key="employee_type",
                label="ประเภทบุคลากร",
                field_type="radio",
                choices=["พนักงานมหาวิทยาลัย", "ลูกจ้างประจำ", "พนักงานเงินรายได้"],
                is_required=True,
            ),
            cft.FormFieldDef(
                source="catalog",
                key="vehicle_kind",
                choices=["บัส", "ตู้"],
                is_required=True,
            ),
            cft.FormFieldDef(
                source="custom",
                key="event_type",
                label="เนื่องในงาน",
                field_type="radio",
                choices=["อุปสมบท", "มงคลสมรส", "ฌาปณกิจศพ"],
                is_required=True,
            ),
            _text_field("event_owner", "ของ (เจ้าภาพ/ผู้ที่เกี่ยวข้อง)"),
            _text_field("house", "สถานที่ไปบ้าน"),
            _text_field("subdistrict", "ตำบล"),
            cft.FormFieldDef(source="catalog", key="district"),
            cft.FormFieldDef(source="catalog", key="province", is_required=True),
            _text_field("pickup", "ให้รถไปจอดรอรับที่"),
        ],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="ผู้บังคับบัญชาของผู้ขอใช้รถ",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
            _approver_step(approver_user, "ผู้อนุมัติการขอใช้รถ"),
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


def _box(
    x0, x1, y0, y1, variable, align="center", kind="text", match_value="", font_size=15, page_w=_PAGE_W
):
    """กล่องจากพิกัด pt ของ `pdftotext -bbox` (x0..x1, y0..y1); ข้อความยกขึ้น 3pt ให้นั่งบนเส้นจุด"""
    lift = 3 if kind == "text" else 0
    return cft.PaperPlacement(
        page=0,
        x=x0 / page_w,
        y=(y0 - lift) / _PAGE_H,
        w=(x1 - x0) / page_w,
        h=(y1 - y0) / _PAGE_H,
        variable=variable,
        kind=kind,
        match_value=match_value,
        font_size=font_size,
        align=align,
    )


# (x0, x1, y0, y1, variable, ตัวเลือกของ _box) จุดเริ่มของเส้นจุดต่อจากป้ายคำนวณจากความกว้างฟอนต์ THSarabunNew 16pt
_ABROAD_PLACEMENTS = [
    (107.6, 300.0, 82.1, 99.7, "app.division", dict(align="left")),
    (77.9, 290.0, 100.2, 117.8, "details.custom_doc_no", dict(align="left")),
    (322.0, 345.0, 100.2, 117.8, "app.created.day", {}),
    (345.0, 410.0, 100.2, 117.8, "app.created.month_th", {}),
    (410.0, 450.0, 100.2, 117.8, "app.created.year_be", {}),
    (227.8, 414.8, 178.3, 193.7, "app.division", {}),
    (104.3, 163.3, 194.1, 209.6, "details.vehicle_kind", {}),
    (270.2, 296.8, 194.1, 209.6, "details.vehicle_count", {}),
    (374.1, 402.3, 194.1, 209.6, "app.passenger_number", {}),
    (113.3, 198.8, 210.0, 225.4, "details.custom_city_state", {}),
    (235.9, 320.1, 210.0, 225.4, "details.custom_country", {}),
    (355.7, 379.2, 210.0, 225.4, "app.departure.day", {}),
    (404.7, 467.8, 210.0, 225.4, "app.departure.month_th", {}),
    (490.1, 528.6, 210.0, 225.4, "app.departure.year_be", {}),
    (107.8, 350.6, 225.8, 241.3, "app.request_reason", {}),
    (437.6, 528.5, 225.8, 241.3, "details.custom_pickup", {}),
    (90.7, 129.1, 241.7, 257.1, "app.departure.time", {}),
    (318.0, 356.7, 241.7, 257.1, "app.return.day", {}),
    (382.1, 465.5, 241.7, 257.1, "app.return.month_th", {}),
    (487.9, 528.7, 241.7, 257.1, "app.return.year_be", {}),
    (128.5, 162.3, 257.4, 272.8, "app.return.time", {}),
    (198.8, 352.7, 257.4, 272.8, "details.custom_coordinator", {}),
    (371.6, 462.7, 257.4, 272.8, "details.custom_coordinator_phone", {}),
    (276.0, 411.0, 334.5, 352.0, "app.requester_name", {}),
    (287.2, 416.3, 352.5, 370.0, "details.custom_requester_position", {}),
    (276.0, 413.0, 406.7, 424.3, "approvals.head.name", {}),
    (358.5, 392.5, 483.5, 498.9, "app.car_type", {}),
    (470.6, 529.2, 483.5, 498.9, "app.car_plate", {}),
    (147.3, 337.5, 499.3, 514.8, "app.driver_name", {}),
    (124.9, 528.9, 530.9, 546.3, "approvals.admin.comment", dict(align="left")),
    (272.5, 417.8, 558.2, 575.8, "approvals.admin.name", dict(font_size=13)),
    (239.5, 313.8, 601.0, 616.5, "app.car_plate", {}),
    (454.9, 521.1, 601.0, 616.5, "details.custom_country", {}),
    (150.2, 296.1, 616.8, 632.3, "app.driver_name", {}),
    (423.0, 520.8, 616.8, 632.3, "details.custom_country", {}),
    (271.5, 391.0, 664.9, 682.5, "approvals.director.name", dict(font_size=13)),
]


def _physical_abroad_placements():
    return [
        _box(x0, x1, y0, y1, variable, **options)
        for x0, x1, y0, y1, variable, options in _ABROAD_PLACEMENTS
    ]


# ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่: กล่องตรวจสอบกว้าง 10pt กึ่งกลางที่ตัว ○ (วัดจากภาพ raster 300 dpi)
_AIRPORT_PLACEMENTS = [
    (225.7, 364.4, 113.6, 129.1, "app.division", dict(align="left")),
    (436.8, 517.4, 113.6, 129.1, "app.phone", dict(align="left")),
    (251.0, 261.0, 158.1, 168.1, "details.custom_transfer", dict(kind="check", match_value="รับ")),
    (251.0, 261.0, 175.8, 185.8, "details.custom_transfer", dict(kind="check", match_value="ส่ง")),
    (219.2, 266.7, 198.4, 213.9, "app.passenger_number", {}),
    (196.0, 263.2, 223.4, 238.9, "details.custom_flight_no", {}),
    (288.7, 327.4, 223.4, 238.9, "app.departure.day", {}),
    (356.1, 440.1, 223.4, 238.9, "app.departure.month_th", {}),
    (459.2, 511.6, 223.4, 238.9, "app.departure.year_be", {}),
    (404.0, 456.3, 241.0, 256.4, "details.custom_arrive_time", {}),
    (404.9, 457.2, 258.5, 273.9, "details.custom_depart_time", {}),
    (204.5, 411.1, 290.2, 305.6, "details.custom_pickup", dict(align="left")),
    (433.9, 487.0, 290.2, 305.6, "app.departure.time", {}),
    (237.3, 384.9, 315.0, 330.4, "details.custom_p1_name", dict(align="left")),
    (410.8, 510.9, 315.0, 330.4, "details.custom_p1_phone", dict(align="left")),
    (237.3, 384.9, 330.8, 346.3, "details.custom_p2_name", dict(align="left")),
    (410.8, 510.9, 330.8, 346.3, "details.custom_p2_phone", dict(align="left")),
    (237.3, 384.9, 346.7, 362.1, "details.custom_p3_name", dict(align="left")),
    (410.8, 510.9, 346.7, 362.1, "details.custom_p3_phone", dict(align="left")),
    (237.3, 384.9, 362.5, 378.0, "details.custom_p4_name", dict(align="left")),
    (410.8, 510.9, 362.5, 378.0, "details.custom_p4_phone", dict(align="left")),
    (237.3, 384.9, 378.4, 393.8, "details.custom_p5_name", dict(align="left")),
    (410.8, 510.9, 378.4, 393.8, "details.custom_p5_phone", dict(align="left")),
    (225.0, 235.0, 442.5, 452.5, "details.cost_responsibility", dict(kind="check", match_value="ค่าน้ำมันเชื้อเพลิง")),
    (314.7, 324.7, 442.5, 452.5, "details.cost_responsibility", dict(kind="check", match_value="เบี้ยเลี้ยง")),
    (373.6, 383.6, 442.5, 452.5, "details.cost_responsibility", dict(kind="check", match_value="ไม่รับผิดชอบ")),
    (356.1, 462.2, 516.4, 531.8, "app.requester_name", {}),
    (357.3, 466.4, 532.2, 547.7, "details.custom_requester_position", dict(align="left")),
    (371.0, 390.0, 548.1, 563.5, "app.created.day", {}),
    (391.0, 440.0, 548.1, 563.5, "app.created.month_th", {}),
    (441.0, 466.5, 548.1, 563.5, "app.created.year_be", {}),
    (195.5, 205.5, 582.3, 592.3, "app.car_type", dict(kind="check", match_value="เก๋ง")),
    (237.0, 247.0, 582.3, 592.3, "app.car_type", dict(kind="check", match_value="ตู้")),
    (445.0, 524.1, 580.1, 595.6, "app.car_plate", {}),
    (93.3, 237.4, 594.4, 609.9, "app.driver_name", {}),
    (344.0, 457.6, 651.3, 666.7, "approvals.admin.name", {}),
    (342.0, 464.5, 665.6, 681.0, "approvals.admin.date", {}),
    (347.0, 463.0, 722.6, 738.0, "approvals.approver.name", {}),
    (342.0, 466.8, 736.7, 752.2, "approvals.approver.date", {}),
]


def _physical_airport_placements():
    return [
        _box(x0, x1, y0, y1, variable, **options)
        for x0, x1, y0, y1, variable, options in _AIRPORT_PLACEMENTS
    ]


# ใบขอใช้รถประเภทสวัสดิการบุคลากร: กล่องตรวจสอบกว้าง 10pt กึ่งกลางที่วงเล็บ "( )" (วัดจากภาพ raster 300 dpi)
_WELFARE_PLACEMENTS = [
    (425.0, 445.0, 84.4, 99.9, "app.created.day", {}),
    (447.0, 505.0, 84.4, 99.9, "app.created.month_th", {}),
    (507.0, 545.0, 84.4, 99.9, "app.created.year_be", {}),
    (126.6, 277.2, 140.8, 156.3, "app.requester_name", dict(align="left")),
    (301.0, 311.0, 144.2, 154.2, "details.custom_employee_type", dict(kind="check", match_value="พนักงานมหาวิทยาลัย")),
    (397.5, 407.5, 144.2, 154.2, "details.custom_employee_type", dict(kind="check", match_value="ลูกจ้างประจำ")),
    (470.3, 480.3, 144.2, 154.2, "details.custom_employee_type", dict(kind="check", match_value="พนักงานเงินรายได้")),
    (66.3, 280.1, 164.6, 180.1, "app.division", dict(align="left")),
    (302.4, 386.1, 164.6, 180.1, "app.phone", dict(align="left")),
    (499.6, 509.6, 167.9, 177.9, "details.vehicle_kind", dict(kind="check", match_value="บัส")),
    (532.5, 542.5, 167.9, 177.9, "details.vehicle_kind", dict(kind="check", match_value="ตู้")),
    (92.3, 102.3, 191.7, 201.7, "details.custom_event_type", dict(kind="check", match_value="อุปสมบท")),
    (151.7, 161.7, 191.7, 201.7, "details.custom_event_type", dict(kind="check", match_value="มงคลสมรส")),
    (219.8, 229.8, 191.7, 201.7, "details.custom_event_type", dict(kind="check", match_value="ฌาปณกิจศพ")),
    (304.3, 552.3, 188.4, 203.8, "details.custom_event_owner", dict(align="left")),
    (103.3, 232.2, 212.0, 227.4, "details.custom_house", dict(align="left")),
    (258.7, 336.4, 212.0, 227.4, "details.custom_subdistrict", dict(align="left")),
    (366.2, 438.8, 212.0, 227.4, "details.district", dict(align="left")),
    (473.8, 552.4, 212.0, 227.4, "details.province", dict(align="left")),
    (140.3, 264.0, 235.8, 251.2, "details.custom_pickup", dict(align="left")),
    (288.0, 310.0, 235.8, 251.2, "app.departure.day", {}),
    (312.0, 368.0, 235.8, 251.2, "app.departure.month_th", {}),
    (370.0, 402.0, 235.8, 251.2, "app.departure.year_be", {}),
    (427.4, 473.1, 235.8, 251.2, "app.departure.time", {}),
    (160.0, 185.0, 259.6, 275.0, "app.return.day", {}),
    (188.0, 245.0, 259.6, 275.0, "app.return.month_th", {}),
    (247.0, 272.0, 259.6, 275.0, "app.return.year_be", {}),
    (297.3, 347.3, 259.6, 275.0, "app.return.time", {}),
    (291.0, 421.0, 337.3, 352.8, "app.requester_name", {}),
    (290.5, 421.3, 397.1, 412.5, "approvals.head.name", {}),
    (239.4, 409.4, 467.4, 482.9, "app.requester_name", dict(align="left")),
    (472.8, 482.8, 470.8, 480.8, "app.car_type", dict(kind="check", match_value="บัส")),
    (521.0, 531.0, 470.8, 480.8, "app.car_type", dict(kind="check", match_value="ตู้")),
    (112.0, 210.2, 485.5, 501.0, "app.car_plate", dict(align="left")),
    (253.4, 415.1, 485.5, 501.0, "app.driver_name", dict(align="left")),
    (291.2, 429.9, 513.7, 529.2, "approvals.admin.name", {}),
    (291.2, 423.5, 542.0, 557.4, "approvals.approver.name", {}),
    (129.5, 257.1, 598.4, 613.8, "app.driver_name", dict(align="left")),
]


def _physical_welfare_placements():
    return [
        _box(x0, x1, y0, y1, variable, **options)
        for x0, x1, y0, y1, variable, options in _WELFARE_PLACEMENTS
    ]


# ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (DIIS): ทั้ง 3 แบบใช้ PDF ใบเดียวกัน (ฟอร์มเปล่าที่ export
# จาก paper.html; A4 594.96x841.92) พิกัดวัดจาก `pdftotext -bbox` และภาพ raster 300 dpi ของ PDF นั้น
# - ข้อความ: (x0, x1, y ของเส้นจุดไข่ปลา, variable, ตัวเลือก) ข้อความนั่งเหนือเส้นจุดประมาณ 2pt
# - วงกลม/สี่เหลี่ยม: (x0, x1, y0, y1) ของรูปทรงนั้น ๆ ใช้ kind="check"
_DIIS_PAGE_W = 594.96
_DIIS_BOX_H = 15.5


def _diis_text(x0, x1, dot_y, variable, **options):
    bottom = dot_y + 4  # _box ยกข้อความขึ้น 3pt; baseline จึงอยู่เหนือเส้นจุดราว 2pt
    if options.get("align") == "left":
        x0 += 3  # เว้นจากป้ายหน้าเส้นจุดเล็กน้อย
    return _box(x0, x1, bottom - _DIIS_BOX_H, bottom, variable, page_w=_DIIS_PAGE_W, **options)


def _diis_check(x0, x1, y0, y1, variable, match_value):
    return _box(
        x0, x1, y0, y1, variable, kind="check", match_value=match_value, page_w=_DIIS_PAGE_W
    )


def _diis_date(prefix, x_left, dot_y):
    """วัน เดือน ปี พ.ศ. 3 กล่องติดกันบนเส้นจุดเส้นเดียว (เส้นของ "ในวันที่"/"เดินทางไปวันที่" ฯลฯ)"""
    return [
        _diis_text(x_left + 2, x_left + 24, dot_y, f"{prefix}.day", align="right"),
        _diis_text(x_left + 25, x_left + 93, dot_y, f"{prefix}.month_th"),
        _diis_text(x_left + 94, x_left + 144, dot_y, f"{prefix}.year_be", align="left"),
    ]


def _diis_header():
    return [
        _diis_text(299.3, 336.5, 61.0, "app.created.day"),
        _diis_text(360.0, 464.6, 61.0, "app.created.month_th"),
        _diis_text(486.0, 538.3, 61.0, "app.created.year_be"),
        _diis_text(86.9, 274.3, 111.2, "app.requester_name", align="left"),
        _diis_text(296.9, 420.5, 111.2, "app.division", align="left"),
        _diis_text(442.6, 538.3, 111.2, "app.phone", align="left"),
    ]


def _diis_signatures():
    """ลงชื่อผู้ขอใช้ และหัวหน้าฝ่าย + วันที่ (วันที่เป็นข้อความเดียว dd/mm/พ.ศ. วางบนเส้นของเดือน)"""
    return [
        _diis_text(341.3, 489.6, 464.4, "app.requester_name"),
        _diis_text(341.3, 473.0, 493.0, "approvals.head.name"),
        _diis_text(388.0, 454.0, 514.1, "approvals.head.date", font_size=13),
    ]


def _diis_section_circle(y0, y1):
    return _diis_check(57.1, 70.6, y0, y1, "app.location", "*")


def _diis_admin_box():
    """ความเห็นของผู้ควบคุมยานพาหนะ (คอลัมน์ซ้าย; ใบต่างจังหวัดไม่ใช้)"""
    return [
        _diis_check(57.1, 70.6, 558.0, 571.4, "approvals.admin.decision", "approved"),
        _diis_check(70.6, 84.0, 577.4, 590.9, "app.car_plate", "กษ-9318"),
        _diis_check(70.6, 84.0, 597.8, 611.3, "app.car_plate", "บล-5746"),
        _diis_text(92.2, 241.2, 631.7, "app.driver_name"),
        _diis_check(57.1, 70.6, 680.2, 693.8, "approvals.admin.decision", "denied"),
        _diis_text(138.7, 275.0, 694.8, "approvals.admin.comment", align="left"),
        _diis_text(135.8, 233.0, 731.5, "approvals.admin.name"),
        _diis_text(154.0, 222.0, 752.4, "approvals.admin.date", font_size=13),
    ]


def _diis_general_placements():
    return (
        _diis_header()
        + [
            _diis_section_circle(135.1, 148.6),
            _diis_text(127.4, 538.3, 149.5, "app.location", align="left"),
            _diis_text(140.2, 407.8, 169.7, "app.request_reason", align="left"),
            _diis_text(470.9, 523.2, 169.7, "app.passenger_number"),
        ]
        + _diis_date("app.departure", 105.8, 189.2)
        + [
            _diis_text(378.7, 431.0, 189.2, "app.departure.time"),
            _diis_text(474.0, 526.3, 189.2, "app.return.time"),
            _diis_text(142.6, 449.8, 208.8, "details.custom_pickup", align="left"),
            _diis_text(474.0, 526.3, 208.8, "app.departure.time"),
        ]
        + _diis_signatures()
        + _diis_admin_box()
    )


def _diis_airport_placements():
    # ใบนี้พิมพ์ค่าลงแถว "ไปส่งที่สนามบิน" เท่านั้น (ค่า รับ/ส่ง ถูกแยกด้วยเครื่องหมายในช่อง □ ของแถวนั้น)
    return (
        _diis_header()
        + [
            _diis_check(57.1, 70.6, 217.4, 230.9, "app.location", "*"),
            _diis_check(78.0, 90.0, 239.3, 251.3, "details.custom_transfer", "ส่ง"),
            _diis_check(78.0, 90.0, 300.0, 312.0, "details.custom_transfer", "รับ"),
        ]
        + _diis_date("app.departure", 169.4, 252.2)
        + [
            _diis_text(352.6, 404.6, 252.2, "app.departure.time"),
            _diis_text(478.6, 523.2, 252.2, "app.passenger_number"),
            _diis_text(131.3, 337.9, 272.4, "details.custom_flight_no", align="left"),
            _diis_text(474.0, 526.3, 272.4, "details.custom_flight_time"),
            _diis_text(163.4, 538.3, 292.1, "details.custom_pickup", align="left"),
        ]
        + _diis_signatures()
        + _diis_admin_box()
    )


def _diis_out_of_town_placements():
    return (
        _diis_header()
        + [
            _diis_section_circle(342.7, 356.2),
            _diis_text(166.6, 538.3, 357.2, "app.location", align="left"),
            _diis_text(140.2, 407.8, 377.5, "app.request_reason", align="left"),
            _diis_text(470.9, 523.2, 377.5, "app.passenger_number"),
        ]
        + _diis_date("app.departure", 132.0, 397.0)
        + [_diis_text(474.0, 526.3, 397.0, "app.departure.time")]
        + [_diis_text(142.6, 538.3, 416.4, "details.custom_pickup", align="left")]
        + _diis_date("app.return", 138.7, 436.1)
        + [_diis_text(474.0, 526.3, 436.1, "app.return.time")]
        + _diis_signatures()
        + [
            _diis_text(463.4, 538.3, 600.2, "app.car_plate", align="left"),
            _diis_text(392.9, 538.3, 619.7, "app.driver_name", align="left"),
            _diis_text(372.0, 469.9, 640.1, "app.location", align="left"),
            _diis_text(398.9, 496.3, 669.2, "approvals.admin.name"),
            _diis_text(417.0, 485.0, 690.2, "approvals.admin.date", font_size=13),
            _diis_check(303.1, 316.6, 701.3, 714.7, "approvals.director.decision", "approved"),
            _diis_check(357.1, 370.6, 701.3, 714.7, "approvals.director.decision", "denied"),
            _diis_text(449.3, 538.3, 715.7, "approvals.director.comment", align="left"),
            _diis_text(404.2, 501.6, 749.5, "approvals.director.name"),
            _diis_text(417.0, 485.0, 770.4, "approvals.director.date", font_size=13),
        ]
    )


_PLACEMENT_BUILDERS = {
    "diis_general": _diis_general_placements,
    "diis_airport": _diis_airport_placements,
    "diis_out_of_town": _diis_out_of_town_placements,
    "physical_domestic": _physical_domestic_placements,
    "physical_abroad": _physical_abroad_placements,
    "physical_airport": _physical_airport_placements,
    "physical_welfare": _physical_welfare_placements,
}

_BUILDERS = {
    "diis_general": _diis_general,
    "diis_airport": _diis_airport,
    "diis_out_of_town": _diis_out_of_town,
    "physical_domestic": _physical_domestic,
    "physical_abroad": _physical_abroad,
    "physical_airport": _physical_airport,
    "physical_welfare": _physical_welfare,
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
