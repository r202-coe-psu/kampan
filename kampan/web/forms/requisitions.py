from bson import ObjectId
from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from flask_wtf.file import FileField, FileAllowed
from wtforms import (
    Form,
    StringField,
    IntegerField,
    DecimalField,
    FieldList,
    FormField,
    SelectField,
    validators,
)
from wtforms.fields import DateField

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
        "tor_document",
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
    product_name = StringField("ชื่อสินค้า", [validators.DataRequired()])
    quantity = IntegerField(
        "จำนวน", [validators.DataRequired(), validators.NumberRange(min=1)]
    )
    category = SelectField(
        "หมวดหมู่",
        choices=CATEGORY_CHOICES,
        validators=[validators.DataRequired()],
    )
    amount = DecimalField("จำนวนเงิน", [validators.DataRequired()])
    company = StringField("บริษัท", [validators.DataRequired()])


class CommitteeForm(Form):
    members = SelectField(
        "กรรมการ", coerce=ObjectId, validators=[validators.DataRequired()]
    )
    committee_type = SelectField(
        "ประเภทกรรมการ",
        choices=COMMITTEE_TYPE_CHOICES,
        validators=[validators.DataRequired()],
    )
    committee_position = SelectField(
        "ตำแหน่งกรรมการ",
        choices=COMMITTEE_POSITION_CHOICES,
        validators=[validators.DataRequired()],
    )


class RequisitionForm(BaseRequisitionForm):
    start_date = DateField(
        "วันที่เริ่มต้น",
    )
    tor_document = FileField(
        "ไฟล์ ToR (PDF เท่านั้น)",
        validators=[FileAllowed(["pdf"], "PDF only")],
    )
    # enforce min 1 and max 4 items at the form level
    items = FieldList(
        FormField(RequisitionItemForm),
        min_entries=1,
        validators=[validators.Length(min=1, max=4)],
    )
    committees = FieldList(
        FormField(CommitteeForm),
        min_entries=1,
    )
