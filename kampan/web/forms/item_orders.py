from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseOrderItemForm = model_form(
    models.OrderItem,
    FlaskForm,
    exclude=[
        "created_date",
        "approval_status",
        "status",
    ],
    field_args={
        "user": {"label": "ชื่อผู้ใช้งาน"},
        "description": {"label": "คำอธิบาย"},
    },
)


class OrderItemForm(BaseOrderItemForm):
    pass
