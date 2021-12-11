from flask_wtf import FlaskForm
from wtforms import fields,validators
from .fields import TagListField, TextListField

class SupplierForm(FlaskForm):
    
    order_from = fields.StringField(
        validators=[validators.InputRequired()]
    )
    description = fields.StringField()