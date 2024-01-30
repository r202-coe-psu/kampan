from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseSupplierForm = model_form(
    models.Supplier,
    FlaskForm,
    exclude=[
        "phone",
        "last_modifier",
        "created_date",
        "updated_date",
    ],
    field_args={
        "name": {"label": "ชื่อร้าน"},
        "address": {"label": "ที่อยู่"},
        "description": {"label": "คำอธิบาย"},
        "tax_id": {"label": "เลขกำกับภาษี"},
        "contact": {"label": "ช่องทางการติดต่อ"},
        "email": {"label": "อีเมลล์"},
    },
)


class SupplierForm(BaseSupplierForm):
    pass
