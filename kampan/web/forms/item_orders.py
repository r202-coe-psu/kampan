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
    ],
    field_args = {
        "user":{"label": "user"},
        "description": {"label": "Description"},
    },
)

class OrderItemForm(BaseOrderItemForm):
    pass