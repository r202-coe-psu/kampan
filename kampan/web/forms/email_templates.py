from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import fields, widgets, validators

import datetime

from .fields import TagListField, TextListField

from kampan import models

BaseEmailTemplateForm = model_form(
    models.EmailTemplate,
    FlaskForm,
    exclude=[
        "organization",
        "created_by",
        "last_updated_by",
        "is_default",
        "created_date",
        "updated_date",
        "type",
    ],
    field_args={
        "name": {"label": "Template Name"},
        # "type": {"label": "Type"},
        "subject": {"label": "Subject"},
        "body": {"label": "Body"},
    },
)


class EmailTemplateForm(BaseEmailTemplateForm):
    pass


class EmailTemplateFileForm(FlaskForm):
    email_template_file = file.FileField(
        "Email Template File",
        validators=[
            file.FileRequired(),
            file.FileAllowed(["html"], "รับเฉพาะไฟล์ html เท่านั้น"),
        ],
    )
