from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, ValidationError
from kampan import models

BaseProcurementForm = model_form(
    models.Procurement,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "image",
        "start_date",
        "end_date",
        "status",
    ],
    field_args={
        "product_number": {"label": "เลขที่สินค้า/เลขที่เอกสาร"},
        "name": {"label": "ชื่อรายการ"},
        "category": {"label": "ประเภท"},
        "asset_code": {"label": "รหัสครุภัณฑ์"},
        "amount": {"label": "จำนวนเงิน"},
        "period": {"label": "จำนวนงวด"},
        "company": {"label": "บริษัท"},
        "responsible_by": {"label": "ผู้รับผิดชอบ"},
    },
)


class ProcurementForm(BaseProcurementForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด",
        validators=[validators.Optional()],
    )

    def validate_end_date(self, field):
        if self.start_date.data and field.data:
            if field.data < self.start_date.data:
                raise ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

    def validate_amount(self, field):
        if field.data is not None and field.data < 0:
            raise ValidationError("จำนวนเงินต้องมากกว่าหรือเท่ากับ 0")

    def validate_period(self, field):
        if field.data is not None and field.data < 1:
            raise ValidationError("จำนวนงวดต้องมากกว่า 0")

    image = fields.FileField(
        "รูปภาพ",
        validators=[
            file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")
        ],
    )


class FileForm(FlaskForm):
    document_upload = file.MultipleFileField(
        "Upload File Type (.xls, xlsx)",
        validators=[
            file.FileAllowed(["xls", "xlsx"], "Only .xls and .xlsx files are allowed!"),
        ],
    )


class EditImageForm(FlaskForm):
    image = fields.FileField(
        "รูปภาพใหม่",
        validators=[
            file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")
        ],
    )


BasePaymentRecordForm = model_form(
    models.PaymentRecord,
    FlaskForm,
    exclude=[
        "period_index",
        "paid_date",
        "due_date",
        "paid_by",
    ],
    field_args={
        "product_number": {"label": "เลขที่สินค้า/เลขที่เอกสาร"},
        "amount": {"label": "จำนวนเงิน"},
    },
)


class PaymentRecordForm(BasePaymentRecordForm):
    amount = fields.DecimalField(
        "จำนวนเงิน",
        places=2,
        rounding=None,
        validators=[
            validators.InputRequired(),
            validators.NumberRange(
                min=0, max=1e12, message="จำนวนเงินต้องอยู่ระหว่าง 0 ถึง 1,000,000,000,000"
            ),
        ],
    )


class PaymentForm(FlaskForm):
    amount = fields.DecimalField(
        "จำนวนเงิน",
        places=2,
        validators=[
            validators.InputRequired(),
            validators.NumberRange(min=0, message="จำนวนเงินต้องมากกว่าหรือเท่ากับ 0"),
        ],
    )
    product_number = fields.StringField(
        "เลขที่สินค้า/เลขที่เอกสาร",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
