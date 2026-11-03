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


class CarFormTemplate(me.Document):
    meta = {"collection": "car_form_templates", "indexes": ["organization"]}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    name = me.StringField(required=True)
    description = me.StringField(default="")
    fields = me.ListField(me.EmbeddedDocumentField(FormFieldDef))
    steps = me.ListField(me.EmbeddedDocumentField(ApprovalStepDef))
    paper_html = me.StringField(default="")
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
