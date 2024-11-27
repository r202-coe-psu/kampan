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
        "first_name",
        "last_name",
        "organization",
        "user_setting"
    ],
    field_args={
    },
)


class UserRolesForm(Profile):
    roles = fields.SelectMultipleField("ตำแหน่ง")
