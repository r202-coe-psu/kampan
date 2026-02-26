from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import fields, widgets, validators, ValidationError

from kampan import models


def file_required(message="กรุณาเลือกไฟล์อย่างน้อย 1 ไฟล์"):
    def _file_required(form, field):
        if not field.data or all(not getattr(f, "filename", None) for f in field.data):
            raise ValidationError(message)

    return _file_required


BaseFileForm = model_form(
    models.Document,
    FlaskForm,
    exclude=[
        "document_name",
        "status",
        "created_date",
        "created_by",
        "updated_date",
        "updated_by",
    ],
    field_args={
        "document": {"label": "Upload file"},
    },
)


class FileForm(BaseFileForm):
    document_upload = file.MultipleFileField(
        "Upload File Type (.xls, xlsx)",
        validators=[
            file_required(),
            file.FileAllowed(
                ["io", "xls", "xlsx"], "อนุญาตเฉพาะไฟล์ .io, .xls และ .xlsx เท่านั้น"
            ),
        ],
    )

    category = fields.SelectField(
        "ประเภทไฟล์",
        choices=[
            ("mas", "MAS (แหล่งเงิน)"),
            ("ma", "ครุภัณฑ์"),
        ],
        validators=[validators.DataRequired(message="กรุณาเลือกประเภทไฟล์")],
    )
