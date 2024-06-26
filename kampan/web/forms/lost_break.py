from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemLostBreakForm = model_form(
    models.LostBreakItem,
    FlaskForm,
    exclude=["created_date", "user", "lost_from", "quantity", "organization"],
    field_args={
        # "item": {"label": "ชื่อวัสดุ", "label_modifier": lambda i: i.name },
        "warehouse": {"label": "คลังวัสดุ", "label_modifier": lambda w: w.name},
        "description": {"label": "คำอธิบาย"},
        # "quantity": {"label": "จำนวนทั้งหมด"},
    },
)


class ItemLostBreakForm(BaseItemLostBreakForm):
    item = fields.SelectField(label="ชื่อวัสดุ")
    set_ = fields.IntegerField(label="จำนวนหน่วยใหญ่", default=0)
    piece = fields.IntegerField(label="จำนวนหน่วยเล็ก", default=1)
