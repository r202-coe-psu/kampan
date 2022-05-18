from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseSupplierForm = model_form(
    models.Supplier,
    FlaskForm,
    exclude=[
    "phone",
    ],

field_args={
    "name" :{"label":"Name"},
    "address" : {"label": "Address"},
    "description": {"label": "Description"},
    "tex_id": {"label": "Tax ID"},
    "contact": {"label": "Contact"},
    "email": {"label": "Email"},
    }
    )

class SupplierForm(BaseSupplierForm):
    pass

