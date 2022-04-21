from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators
from .fields import TagListField, TextListField
from kampan import models


BaseItemForm = model_form(
    models.Item,
    FlaskForm,
    exclude=[
        "user",
        "created_date",
        "updated_date",
    ],
    field_args={
        "name": {"label": "Name"},
        "description": {"label": "Desctiption"},
        "width": {"label": "Width"},
        "height": {"label": "Height"},
        "deep": {"label": "Deep"},
        "weight": {"label": "Weight"},
        "categories": {"label": "Categories"},
    },
)


class ItemForm(BaseItemForm):
    pass


# class ItemForm(FlaskForm):

#     name = fields.StringField(validators=[validators.InputRequired()])
#     description = fields.StringField()
#     weight = fields.FloatField(default=0)
#     size = fields.EmbeddedDocumentField(ItemSize)
#     categories = TagListField(
#         "Categories", validators=[validators.InputRequired(), validators.Length(min=1)]
#     )
