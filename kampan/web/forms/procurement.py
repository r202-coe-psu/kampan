from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import ValidationError, fields, validators

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
        "status",
        "organization",
    ],
    field_args={
        "name": {"label": "ชื่อรายการ"},
        "category": {"label": "ประเภท"},
        "amount": {"label": "จำนวนเงินทั้งหมด (บาท)"},
        "period": {"label": "จำนวนงวด"},
        "company": {"label": "บริษัท"},
        "responsible_by": {"label": "ผู้รับผิดชอบ"},
    },
)


class ProcurementForm(BaseProcurementForm):
    organization = None
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด",
        validators=[validators.Optional()],
    )
    asset_codes = fields.FieldList(
        fields.StringField("รหัสครุภัณฑ์", validators=[validators.InputRequired("กรุณาระบุรหัสครุภัณฑ์")]),
        min_entries=1,
    )
    product_numbers = fields.FieldList(
        fields.StringField("เลขที่สินค้า/เลขที่เอกสาร", validators=[validators.InputRequired("กรุณาระบุเลขที่เอกสาร")]),
        min_entries=1,
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
        validators=[file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )


class EditImageForm(FlaskForm):
    image = fields.FileField(
        "รูปภาพใหม่",
        validators=[file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
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
            validators.NumberRange(min=0, max=1e12, message="จำนวนเงินต้องอยู่ระหว่าง 0 ถึง 1,000,000,000,000"),
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


class ProductFilterForm(FlaskForm):
    name = fields.StringField(
        "ชื่อรายการ",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    category = fields.SelectField(
        "ประเภท",
        choices=[("", "ทั้งหมด")] + models.CATEGORY_CHOICES,
        validators=[validators.Optional()],
    )
    payment_status = fields.SelectField(
        "สถานะการจ่ายเงิน",
        choices=[("", "ทั้งหมด")] + models.PAYEMENT_STATUS_CHOICES,
        validators=[validators.Optional()],
    )
