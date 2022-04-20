from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemRegisterationForm = model_form(
    models.CheckinItem,
    FlaskForm,
    exclude=[
        "created_date",
        "user",
    ],
    field_args={
        "item": {"label": "Item", "label_modifier": lambda i: i.name},
        "warehouse": {"label": "Warehouse", "label_modifier": lambda w: w.name},
        "quantity": {"label": "Quantity"},
        "price": {"label": "Price"},
    },
)
class ItemRegisterationForm(BaseItemRegisterationForm):
    pass