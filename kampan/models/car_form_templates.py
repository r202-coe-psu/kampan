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
        from kampan.utils.car_form_catalog import CATALOG

        for field in self.fields:
            if field.source == "catalog":
                catalog_field = CATALOG.get(field.key)
                if catalog_field is None:
                    raise me.ValidationError(
                        f"catalog field '{field.key}' ไม่มีอยู่ใน catalog"
                    )
                if not set(field.choices) <= set(catalog_field.choices):
                    raise me.ValidationError(
                        f"choices ของ '{field.key}' ต้องเป็นสับเซตของ catalog"
                    )
            elif not field.field_type:
                raise me.ValidationError(
                    f"custom field '{field.key}' ต้องระบุ field_type"
                )

        if not self.steps:
            raise me.ValidationError("ต้องมีอย่างน้อย 1 ขั้นอนุมัติ")
        if sum(1 for step in self.steps if step.assigns_vehicle) != 1:
            raise me.ValidationError("ต้องมีขั้นจัดรถ (assigns_vehicle) พอดี 1 ขั้น")

        self._validate_placements()

    def _validate_placements(self):
        from kampan.utils.car_form_paper import available_variables

        if not self.placements:
            return
        if not self.paper_file:
            raise me.ValidationError("ต้องอัปโหลด PDF ก่อนวางตัวแปรบนกระดาษ")

        variables = available_variables(self)
        for placement in self.placements:
            if placement.variable not in variables:
                raise me.ValidationError(
                    f"ตัวแปร '{placement.variable}' ไม่มีใน template นี้"
                )
            if placement.page >= self.paper_file.page_count:
                raise me.ValidationError(
                    f"หน้า {placement.page} เกินจำนวนหน้าของ PDF"
                )
            if (
                placement.x < 0
                or placement.y < 0
                or placement.w <= 0
                or placement.h <= 0
                or placement.x + placement.w > 1 + 1e-9
                or placement.y + placement.h > 1 + 1e-9
            ):
                raise me.ValidationError(
                    f"ตำแหน่งของ '{placement.variable}' อยู่นอกหน้ากระดาษ"
                )
