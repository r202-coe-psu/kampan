from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import fields, widgets, validators

from kampan import models

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
        "category": {
            "label": "Category",
            "validators": [validators.DataRequired()],
        },
    },
)


class FileForm(BaseFileForm):
    document_upload = file.MultipleFileField(
        "Upload File Type (.io, .xls, xlsx)",
        validators=[
            file.FileAllowed(
                ["io", "xls", "xlsx"], "Only .io, .xls and .xlsx files are allowed!"
            ),
        ],
    )

    category = fields.SelectField(
        "Category",
        choices=[
            ("mas", "MAS (แหล่งเงิน)"),
            ("ma", "MA (ครุภัณฑ์)"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
    )
