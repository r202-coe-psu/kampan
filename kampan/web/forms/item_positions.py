from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemPositionForm = model_form(
    models.ItemPosition,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "user",
    ],
    field_args={
        "warehouse": {"label": "Warehouse", "label_modifier": lambda w: w.name},
        "description": {"label": "Description"},
        "rack": {"label": "Rack"},
        "row": {"label": "Row"},
        "locker": {"label": "Locker"},
    },
)


class ItemPositionForm(BaseItemPositionForm):
    pass
