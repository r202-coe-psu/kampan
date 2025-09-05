from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import (
    fields,
    validators,
    ValidationError,
    Form,
    StringField,
    IntegerField,
    DecimalField,
    FieldList,
    FormField,
)
from kampan import models
from flask_wtf.file import FileField, FileAllowed

BaseRequisitionForm = model_form(
    models.Requisition,
    FlaskForm,
    exclude=[
        "requisition_code",
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
    ],
    field_args={
        "phone": {"label": "เบอร์โทรศัพท์"},
        "purchaser": {"label": "ผู้ขอซื้อ"},
        "product_name": {"label": "ชื่อสินค้า"},
        "category": {"label": "หมวดหมู่"},
        "amount": {"label": "จำนวนเงิน"},
        "company": {"label": "บริษัท"},
        "quantity": {"label": "จำนวน"},
        "reason": {"label": "เหตุผล"},
        "start_date": {"label": "วันที่ต้องการใช้งาน"},
        "fund": {"label": "แหล่งงบประมาณ"},
    },
)


class RequisitionForm(BaseRequisitionForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    tor_document = fields.FileField(
        "ไฟล์ ToR (PDF เท่านั้น)",
        validators=[FileAllowed(["pdf"], "PDF only")],
    )
