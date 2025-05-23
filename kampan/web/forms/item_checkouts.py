from calendar import calendar
from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField
import datetime

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
        "organization",
    ],
    field_args={
        "order": {"label": "คำสั่งเบิก"},
        "message": {"label": "ข้อความ"},
    },
)


class CheckoutItemForm(BaseCheckoutItemForm):
    item = fields.SelectField("ชื่อวัสดุ")
    piece = fields.IntegerField(
        "จำนวนหน่วยเล็ก",
        validators=[validators.InputRequired(), validators.NumberRange(min=1)],
        default=1,
    )
    calendar_select_checkout = fields.DateTimeField("เลือกวันที่เพื่อแสดงข้อมูล")
    created_date = fields.DateField(
        "ลงวันที่คำสั่งเบิก",
        format="%Y-%m-%dT%H:%M",
        default=datetime.datetime.now,
    )
