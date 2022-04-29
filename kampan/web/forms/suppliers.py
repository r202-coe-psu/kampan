from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField


class SupplierForm(FlaskForm):

    name = fields.StringField(validators=[validators.InputRequired()])
    address = fields.StringField()
    description = fields.StringField()
    tax_id = fields.StringField()
    contact = fields.StringField()
    email = fields.StringField()
