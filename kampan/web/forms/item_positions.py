from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemPositionForm = model_form(
    models.ItemPosition,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "organization",
        "user",
    ],
    field_args={
        "warehouse": {"label": "คลังวัสดุ", "label_modifier": lambda w: w.name},
        "description": {"label": "คำอธิบาย"},
        "rack": {"label": "ชั้นวาง"},
        "row": {"label": "แถว"},
        "locker": {"label": "ตู้เก็บของ"},
    },
)


class ItemPositionForm(BaseItemPositionForm):
    pass
