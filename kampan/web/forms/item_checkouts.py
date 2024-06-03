from calendar import calendar
from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseCheckoutItemForm = model_form(
    models.CheckoutItem,
    FlaskForm,
    exclude=[
        "checkout_from",
        "price",
        "warehouse",
        "user",
        "status",
        "quantity",
        "inventories",
        "set_",
    ],
    field_args={
        "order": {"label": "คำสั่งเบิก"},
        # "item": {
        #     "label": "ชื่อวัสดุ",
        #     "label_modifier": lambda obj: f"{obj.barcode_id} ({obj.name})",
        # },
        # "set_": {"label": "จำนวนหน่วยใหญ่"},
        "piece": {"label": "จำนวนหน่วยเล็ก"},
        "message": {"label": "ข้อความ"},
        "checkout_date": {"label": "ลงวันที่คำสั่งเบิก", "format": "%Y-%m-%d %H:%M"},
    },
)


class CheckoutItemForm(BaseCheckoutItemForm):
    item = fields.SelectField("ชื่อวัสดุ")
    calendar_select_checkout = fields.DateTimeField(
        "เลือกวันที่เพื่อแสดงข้อมูล", format="%Y-1%m-%d %H:%M"
    )
