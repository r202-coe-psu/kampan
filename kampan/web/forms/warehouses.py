from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseWarehouseForm = model_form(
    models.Warehouse,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "owner",
    ],
    field_args={
        "name": {"label": "ชื่อคลังวัสดุ"},
        "description": {
            "label": "คำอธิบาย",
        },
    },
)


class WarehouseForm(BaseWarehouseForm):
    pass
