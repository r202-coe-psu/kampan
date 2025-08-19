from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, ValidationError
from kampan import models

BaseProcurementForm = model_form(
    models.Procurement,
    FlaskForm,
    exclude=[
        "product_number",
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "image",
        "start_date",
        "end_date",
    ],
    field_args={
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


BaseToRYearForm = model_form(
    models.ToRYear,
    FlaskForm,
    exclude=[
        "created_by",
        "last_updated_by",
        "created_date",
        "updated_date",
        "status",
    ],
    field_args={
        "year": {"label": "ปีงบประมาณ"},
        "started_date": {"label": "วันเริ่มต้นปี", "format": "%Y-%m-%d"},
        "ended_date": {"label": "วันสิ้นสุดปี", "format": "%Y-%m-%d"},
    },
)


class ToRYearForm(BaseToRYearForm):
    pass


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
