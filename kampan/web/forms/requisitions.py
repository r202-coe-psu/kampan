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
    ],
    field_args={
        "phone": {"label": "เบอร์โทรศัพท์"},
        "purchaser": {"label": "ผู้ขอซื้อ"},
        "reason": {"label": "เหตุผล"},
        "start_date": {"label": "วันที่ต้องการใช้งาน"},
        "fund": {"label": "แหล่งงบประมาณ"},
    },
)


class RequisitionItemForm(Form):
    product_name = fields.StringField("ชื่อสินค้า", [validators.DataRequired()])
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
    company = fields.StringField("บริษัท", [validators.DataRequired()])


class CommitteeForm(Form):
    member = fields.SelectField("กรรมการ", choices=[("-", "เลือกกรรมการ")])
    committee_type = fields.SelectField("ประเภทกรรมการ", choices=COMMITTEE_TYPE_CHOICES)
    committee_position = fields.SelectField(
        "ตำแหน่งกรรมการ", choices=COMMITTEE_POSITION_CHOICES
    )


class RequisitionForm(BaseRequisitionForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
    )
    purchaser = fields.SelectField(
        "ผู้ขอซื้อ",
        choices=[("-", "เลือกผู้ขอซื้อ")],
    )
    fund = fields.SelectField(
        "แหล่งงบประมาณ",
        choices=[("-", "เลือกแหล่งงบประมาณ")],
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

    items = fields.FieldList(
        fields.FormField(RequisitionItemForm), min_entries=1, max_entries=4
    )
    committees = fields.FieldList(fields.FormField(CommitteeForm), min_entries=1)
