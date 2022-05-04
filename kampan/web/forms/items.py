from wsgiref.validate import validator
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators
from .fields import TagListField, TextListField
from kampan import models


BaseItemForm = model_form(
    models.Item,
    FlaskForm,
    exclude=["user", "created_date", "updated_date", "image"],
    field_args={
        "name": {"label": "Name"},
        "description": {"label": "Desctiption"},
        "weight": {"label": "Weight"},
        "size": {"label": "Size"},
        "categories": {"label": "Categories"},
        "unit": {"label": "Unit"},
    },
)


class ItemForm(BaseItemForm):
    categories = TagListField("Categories", validators=[validators.Length(min=1)])
    img = fields.FileField(
        "Image", validators=[FileAllowed(["png", "jpg"], "allow png and jpg")]
    )


# class ItemForm(FlaskForm):

#     name = fields.StringField(validators=[validators.InputRequired()])
#     description = fields.StringField()
#     weight = fields.FloatField(default=0)
#     size = fields.EmbeddedDocumentField(ItemSize)
#     categories = TagListField(
#         "Categories", validators=[validators.InputRequired(), validators.Length(min=1)]
#     )
