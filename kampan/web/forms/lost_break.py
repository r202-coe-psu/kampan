from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemLostBreakForm = model_form(
    models.LostBreakItem,
    FlaskForm,
    exclude=["created_date", "user", "lost_from", "quantity"],
    field_args={
        # "item": {"label": "ชื่ออุปกรณ์", "label_modifier": lambda i: i.name },
        "warehouse": {"label": "คลังอุปกรณ์", "label_modifier": lambda w: w.name},
        "description": {"label": "คำอธิบาย"},
        # "quantity": {"label": "จำนวนทั้งหมด"},
    },
)


class ItemLostBreakForm(BaseItemLostBreakForm):
    item = fields.SelectField(label="ชื่ออุปกรณ์")
    set_ = fields.IntegerField(label="จำนวนชุด", default=0)
    piece = fields.IntegerField(label="จำนวนชิ้น", default=0)
