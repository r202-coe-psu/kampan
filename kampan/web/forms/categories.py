from flask_mongoengine.wtf import model_form
from flask_wtf import FlaskForm, file
from wtforms import fields, widgets, validators

import datetime

from .fields import TagListField, TextListField

from kampan import models

BaseCategoryForm = model_form(
    models.Category,
    FlaskForm,
    exclude=[
        "organization",
        "created_by",
        "last_updated_by",
        "created_date",
        "updated_date",
        "status",
    ],
    field_args={
        "name": {"label": "ชื่อหมวดหมู่"},
        "description": {"label": "คำอธิบาย"},
    },
)


class CategoryForm(BaseCategoryForm):
    pass
