from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

class ItemRegisterationForm(FlaskForm):
    item = fields.SelectField("Item")
    description = fields.StringField("Description")

    quantity = fields.IntegerField("Quantity", default=0)
    price = fields.FloatField("Price", default=0)