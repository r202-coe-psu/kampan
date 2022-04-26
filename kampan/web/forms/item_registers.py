from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemRegisterationForm = model_form(
    models.RegistrationItem,
    FlaskForm,
    exclude=[
        "created_date",
        "user",
    ],
    field_args={
        "supplier": {"label": "Supplier", "label_modifier": lambda s: s.name},
        "description": {"label": "Description"},
        "receipt_id": {"label": "Receipt_id"},
    },
)
class ItemRegisterationForm(BaseItemRegisterationForm):
    pass
