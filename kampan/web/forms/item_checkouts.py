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

        
    ],
    field_args={
        "order": {"label": "คำสั่งเบิก"},
        "item": {"label": "ชื่อสินค้า", "label_modifier": lambda obj: f"{obj.barcode_id} ({obj.name})"},
        "quantity": {"label": "จำนวนทั้งหมด" },
        "message": {"label": "ข้อความ"},
        "checkout_date": {"label": "ลงวันที่คำสั่งเบิก", "format":'%Y-%m-%d %H:%M'},
    },
)

class CheckoutItemForm(BaseCheckoutItemForm):
    pass
