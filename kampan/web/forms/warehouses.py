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
        "user",
    ],
    field_args={
        "name": {"label": "ชื่อคลังอุปกรณ์"},
        "description": {
            "label": "คำอธิบาย",
        },
    },
)


class WarehouseForm(BaseWarehouseForm):
    pass
