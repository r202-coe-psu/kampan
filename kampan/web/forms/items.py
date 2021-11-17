from flask_wtf import FlaskForm
from wtforms import fields,validators



class ItemForm(FlaskForm):
    
    name = fields.StringField(
        validators=[validators.InputRequired()]
    )
    description = fields.StringField()
    weight = fields.FloatField(default=0)
    categories = fields.StringField()

