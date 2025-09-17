from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators

from kampan import models
from kampan.models.procurement import CATEGORY_CHOICES
from kampan.models.requisitions import (
    COMMITTEE_TYPE_CHOICES,
    COMMITTEE_POSITION_CHOICES,
)

BaseRequisitionForm = model_form(
    models.Requisition,
    FlaskForm,
    exclude=[
        "requisition_code",
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "items",
        "committees",
        "type",
    ],
    field_args={
        "phone": {"label": "เบอร์โทรศัพท์"},
        "purchaser": {"label": "ผู้ขอซื้อ"},
        "reason": {"label": "เหตุผล"},
        "start_date": {"label": "วันที่ต้องการใช้งาน"},
    },
)


class RequisitionItemForm(Form):
    product_name = fields.StringField("ชื่อรายการ", [validators.DataRequired()])
    quantity = fields.IntegerField(
        "จำนวน", [validators.DataRequired(), validators.NumberRange(min=1)]
    )
    category = fields.SelectField(
        "หมวดหมู่",
        choices=CATEGORY_CHOICES,
        validators=[validators.DataRequired()],
    )
    amount = fields.DecimalField(
        "จำนวนเงิน",
        [
            validators.DataRequired(),
            validators.NumberRange(max=1e12, message="จำนวนเงินต้องไม่เกิน 1e12"),
        ],
    )
    currency = fields.StringField("หน่วยเงิน")


class CommitteeForm(Form):
    member = fields.SelectField("กรรมการ", choices=[("-", "เลือกกรรมการ")])
    committee_type = fields.SelectField("ประเภทกรรมการ", choices=COMMITTEE_TYPE_CHOICES)
    committee_position = fields.SelectField(
        "ตำแหน่งกรรมการ", choices=COMMITTEE_POSITION_CHOICES
    )


class RequisitionForm(BaseRequisitionForm):
    type = fields.StringField("ประเภท")
    start_date = fields.DateField(
        "วันที่ต้องการใช้งาน",
    )
    purchaser = fields.SelectField(
        "ผู้ขอซื้อ",
        choices=[("-", "เลือกผู้ขอซื้อ")],
    )
    tor_document = fields.FileField(
        "ไฟล์ ToR (PDF เท่านั้น)",
        validators=[
            file.FileAllowed(
                ["pdf"],
                "PDF only",
            ),
        ],
    )

    qt_document = file.MultipleFileField(
        "ใบเสนอราคา (PDF เท่านั้น, แนบได้ 3 ไฟล์)",
        validators=[
            file.FileAllowed(["pdf"], "PDF only"),
        ],
        render_kw={"multiple": True},
    )

    items = fields.FieldList(
        fields.FormField(RequisitionItemForm), min_entries=1, max_entries=4
    )
    committees = fields.FieldList(fields.FormField(CommitteeForm), min_entries=1)
