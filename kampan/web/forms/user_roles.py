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


USER_ROLE_CHOICES = [
    ("", "ทั้งหมด"),
    ("admin", "ผู้ดูแลระบบ"),
    ("supervisor", "หัวหน้างาน"),
    ("user", "ผู้ใช้งาน"),
    ("staff", "พนักงาน"),
    ("student", "นักศึกษา"),
    ("lecturer", "อาจารย์"),
]


class UserRolesSearchForm(FlaskForm):
    class Meta:
        csrf = False

    email = fields.StringField(
        "อีเมล",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    name = fields.StringField(
        "ชื่อผู้ใช้งาน",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    role = fields.SelectField(
        "ตำแหน่ง",
        choices=USER_ROLE_CHOICES,
        default="",
        validators=[validators.Optional()],
    )
