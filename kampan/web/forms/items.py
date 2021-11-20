from flask_wtf import FlaskForm
from wtforms import fields,validators
from .fields import TagListField, TextListField



class ItemForm(FlaskForm):
    
    name = fields.StringField(
        validators=[validators.InputRequired()]
    )
    description = fields.StringField()
    weight = fields.FloatField(default=0)
    categories =  TagListField(
            'categories',
            validators=[validators.InputRequired(),
                        validators.Length(min=1)])

