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
        "email",
        "password",
        "status",
    ],
    field_args={
        "first_name": {"label": "ชื่อ"},
        "last_name": {"label": "นามสกุล"},
        "organization": {"label": "องค์กร"},
    },
)


class UserForm(Profile):
    pass
