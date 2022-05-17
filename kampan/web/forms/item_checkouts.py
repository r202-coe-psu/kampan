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
        "order": {"label": "order"},
        "item": {"label": "Item", "label_modifier": lambda obj: obj.name},
        "quantity": {"label": "Quantity" },
        "message": {"label": "Message"},
        "checkout_date": {"label": "Date", "format":'%Y-%m-%d %H:%M'},
    },
)

class BaseCheckoutItemForm(BaseCheckoutItemForm):
    pass
