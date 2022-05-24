from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemLostBreakForm = model_form(
    models.LostBreakItem,
    FlaskForm,
    exclude=[
        "created_date",
        "user",
        "lost_from",
    ],
    field_args={
        "item": {"label": "Item", "label_modifier": lambda i: i.name},
        "warehouse": {"label": "Warehouse", "label_modifier": lambda w: w.name},
        "description": {"label": "Description"},
        "quantity": {"label": "Quantity"},
    },
)
class ItemLostBreakForm(BaseItemLostBreakForm):
    pass
