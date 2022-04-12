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
        "rack": {"label": "Rack"},
        "row": {"label": "Row"},
        "locker": {"label": "Locker"},
        "warehouse": {"label": "Warehouse", "label_modifier": lambda w: w.name},
    },
)


class ItemPositionForm(BaseItemPositionForm):
    pass
