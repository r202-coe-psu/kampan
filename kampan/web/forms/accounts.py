from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

Profile = model_form(
    models.User,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
    ],
    field_args={
        "first_name": {"label": "first_name"},
        "last_name": {"label": "last_name"},
        "student_id": {"label": "student_id"},
        "organization": {"label": "organization"},
    },
)


class UserForm(Profile):
    pass
