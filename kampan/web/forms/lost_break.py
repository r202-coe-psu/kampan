from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
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


class SearchLostBreakForm(FlaskForm):
    name = fields.StringField(label="ชื่อวัสดุ", validators=[validators.Optional()])
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        format="%d/%m/%Y",
        widget=widgets.TextInput(),
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สุดท้าย",
        format="%d/%m/%Y",
        widget=widgets.TextInput(),
        validators=[validators.Optional()],
    )
