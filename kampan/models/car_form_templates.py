import datetime

import mongoengine as me

from kampan.models.organizations import ORGANIZATION_ROLES

FIELD_SOURCES = [("catalog", "จาก catalog"), ("custom", "กำหนดเอง")]
CUSTOM_FIELD_TYPES = [
    ("text", "ข้อความ"),
    ("textarea", "ข้อความยาว"),
    ("number", "ตัวเลข"),
    ("date", "วันที่"),
    ("radio", "เลือกข้อเดียว"),
    ("checkbox", "เลือกได้หลายข้อ"),
]
PLACEMENT_KINDS = [("text", "ข้อความ"), ("check", "เครื่องหมายถูก")]
PLACEMENT_ALIGNS = [("left", "ชิดซ้าย"), ("center", "กึ่งกลาง"), ("right", "ชิดขวา")]
APPROVER_TYPES = [("role", "ตาม role"), ("user", "ระบุตัวคน")]


class FormFieldDef(me.EmbeddedDocument):
    source = me.StringField(choices=FIELD_SOURCES, required=True, default="catalog")
    key = me.StringField(required=True, regex=r"^[a-z][a-z0-9_]*$")
    label = me.StringField()
    field_type = me.StringField(choices=CUSTOM_FIELD_TYPES)
    choices = me.ListField(me.StringField())
    is_required = me.BooleanField(default=False)

    def details_key(self):
        return self.key if self.source == "catalog" else f"custom_{self.key}"


class ApprovalStepDef(me.EmbeddedDocument):
    key = me.StringField(required=True, regex=r"^[a-z][a-z0-9_]*$")
    label = me.StringField(required=True)
    approver_type = me.StringField(choices=APPROVER_TYPES, default="role")
    role = me.StringField(choices=ORGANIZATION_ROLES)
    user = me.ReferenceField("User", dbref=True)
    same_division = me.BooleanField(default=False)
    assigns_vehicle = me.BooleanField(default=False)


class CarFormPaperFile(me.Document):
    """PDF ต้นฉบับของใบพิมพ์ (immutable: อัปโหลดใหม่ = เอกสารใหม่)"""

    meta = {"collection": "car_form_paper_files", "indexes": ["organization"]}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    filename = me.StringField(default="")
    data = me.BinaryField(required=True)
    page_count = me.IntField(required=True, min_value=1)
    page_sizes = me.ListField(me.ListField(me.FloatField()))
    uploaded_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class PaperPlacement(me.EmbeddedDocument):
    """ตำแหน่งวางค่าบนหน้า PDF เป็นสัดส่วน 0..1 ของหน้า origin มุมบนซ้าย"""

    page = me.IntField(min_value=0, default=0)
    x = me.FloatField(required=True)
    y = me.FloatField(required=True)
    w = me.FloatField(required=True)
    h = me.FloatField(required=True)
    variable = me.StringField(required=True)
    kind = me.StringField(choices=PLACEMENT_KINDS, default="text")
    match_value = me.StringField(default="")
    font_size = me.FloatField(default=14)
    align = me.StringField(choices=PLACEMENT_ALIGNS, default="left")


class CarFormTemplate(me.Document):
    meta = {"collection": "car_form_templates", "indexes": ["organization"]}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    name = me.StringField(required=True)
    description = me.StringField(default="")
    fields = me.ListField(me.EmbeddedDocumentField(FormFieldDef))
    steps = me.ListField(me.EmbeddedDocumentField(ApprovalStepDef))
    paper_file = me.ReferenceField("CarFormPaperFile", dbref=True)
    placements = me.ListField(me.EmbeddedDocumentField(PaperPlacement))
    status = me.StringField(
        default="active", choices=[("active", "ใช้งาน"), ("disactive", "ยกเลิก")]
    )
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def clean(self):
        problems = template_problems(self)
        if problems:
            raise CarFormTemplateInvalid(problems)


INTERNAL_PROBLEM = "ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่"
ROLE_LABELS = dict(ORGANIZATION_ROLES)
CUSTOM_TYPE_KEYS = {key for key, _ in CUSTOM_FIELD_TYPES}


class CarFormTemplateInvalid(me.ValidationError):
    """รวมปัญหาทุกข้อของ template เป็นข้อความภาษาไทยที่อ่านรู้เรื่อง"""

    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


def _quote(value):
    return f"“{value}”"


def _valid_key(key):
    import re

    return bool(re.match(r"^[a-z][a-z0-9_]*$", key or ""))


def template_problems(template):
    return (
        _field_problems(template.fields)
        + _step_problems(template.steps)
        + _placement_problems(template)
    )


def _field_problems(fields):
    from kampan.utils.car_form_catalog import CATALOG

    problems = []
    seen = {}
    seen_names = {}
    for index, field in enumerate(fields, start=1):
        where = f"ฟิลด์ที่ {index}"
        if field.source == "catalog":
            catalog_field = CATALOG.get(field.key)
            if catalog_field is None:
                if field.key:
                    problems.append(f"{where}: ไม่มีฟิลด์ {_quote(field.key)} ใน catalog")
                else:
                    problems.append(f"{where}: ต้องเลือกฟิลด์จาก catalog")
                continue
            label = field.label or catalog_field.default_label
            name = label.strip()
            invalid = [c for c in field.choices if c not in catalog_field.choices]
            if invalid:
                problems.append(
                    f"{where} ({label}): ตัวเลือก {', '.join(map(_quote, invalid))} ไม่มีใน catalog"
                    f" (ใช้ได้: {', '.join(catalog_field.choices)})"
                )
        else:
            name = (field.label or "").strip()
            if not name:
                problems.append(f"{where}: ต้องกรอกชื่อฟิลด์")
            if field.field_type not in CUSTOM_TYPE_KEYS:
                problems.append(f"{where}: ต้องเลือกชนิดข้อมูล")
            elif field.field_type in ("radio", "checkbox") and not field.choices:
                problems.append(f"{where}: ต้องใส่ตัวเลือกอย่างน้อย 1 ค่า")

        details_key = field.details_key()
        if field.source != "catalog" and not _valid_key(field.key):
            problems.append(f"{where}: {INTERNAL_PROBLEM}")
            continue
        if details_key in seen:
            if field.source == "catalog":
                problems.append(
                    f"{where}: เลือก {_quote(catalog_field.default_label)} ซ้ำกับฟิลด์ที่ {seen[details_key]}"
                )
            else:
                problems.append(f"{where}: {INTERNAL_PROBLEM}")
            continue
        seen[details_key] = index

        if name in seen_names:
            problems.append(f"{where}: ชื่อ {_quote(name)} ซ้ำกับฟิลด์ที่ {seen_names[name]}")
        elif name:
            seen_names[name] = index
    return problems


def _step_problems(steps):
    if not steps:
        return ["ต้องมีอย่างน้อย 1 ขั้นอนุมัติ"]

    problems = []
    seen = {}
    seen_names = {}
    for index, step in enumerate(steps, start=1):
        where = f"ขั้นที่ {index}"
        if not _valid_key(step.key) or step.key in seen:
            problems.append(f"{where}: {INTERNAL_PROBLEM}")
        else:
            seen[step.key] = index
        name = (step.label or "").strip()
        if not name:
            problems.append(f"{where}: ต้องกรอกชื่อขั้น")
        elif name in seen_names:
            problems.append(f"{where}: ชื่อ {_quote(name)} ซ้ำกับขั้นที่ {seen_names[name]}")
        else:
            seen_names[name] = index
        if step.approver_type == "user":
            if not step.user:
                problems.append(f"{where}: ต้องเลือกผู้อนุมัติ")
        elif not step.role:
            problems.append(f"{where}: ต้องเลือก role")
        elif step.role not in ROLE_LABELS:
            problems.append(f"{where}: ไม่มี role {_quote(step.role)} ในระบบ")

    vehicle_steps = sum(1 for step in steps if step.assigns_vehicle)
    if vehicle_steps != 1:
        problems.append(f"ต้องมีขั้นจัดรถพอดี 1 ขั้น (ตอนนี้มี {vehicle_steps} ขั้น)")
    return problems


def _placement_problems(template):
    from kampan.utils.car_form_paper import available_variables

    if not template.placements:
        return []
    if not template.paper_file:
        return ["ต้องอัปโหลด PDF ก่อนวางตัวแปรบนกระดาษ"]

    problems = []
    variables = available_variables(template)
    for index, placement in enumerate(template.placements, start=1):
        where = f"กล่องที่ {index} ({placement.variable})"
        if placement.variable not in variables:
            problems.append(f"{where}: ไม่มีตัวแปรนี้ใน template (ลบกล่องหรือบันทึกฟิลด์/ขั้นก่อน)")
        if placement.page >= template.paper_file.page_count:
            problems.append(
                f"{where}: อยู่หน้า {placement.page + 1} แต่ PDF มี {template.paper_file.page_count} หน้า"
            )
        if (
            placement.x < 0
            or placement.y < 0
            or placement.w <= 0
            or placement.h <= 0
            or placement.x + placement.w > 1 + 1e-9
            or placement.y + placement.h > 1 + 1e-9
        ):
            problems.append(f"{where}: อยู่นอกหน้ากระดาษ")
    return problems
