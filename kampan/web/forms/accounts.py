from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from kampan import models

BaseProfileForm = model_form(
    models.User,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "email",
        "password",
        "status",
        "roles",
        "user_setting",
        "student_id",
        "pic",
        "thai_first_name",
        "thai_last_name",
    ],
    field_args={
        "first_name": {"label": "First Name"},
        "last_name": {"label": "Last Name"},
        # "citizen_id": {"label": "เลขบัตรประจำตัวประชาชน"},
    },
)


class ProfileForm(BaseProfileForm):
    # pic = fields.FileField(
    #     "Picture", validators=[FileAllowed(["png", "jpg"], "allow png and jpg")]
    # )

    # thai_first_name = fields.StringField("ชื่อ")
    # thai_last_name = fields.StringField("นามสกุล")
    pass


BaseUserSettingForm = model_form(
    models.users.UserSetting,
    FlaskForm,
    exclude=["updated_date"],
    field_args={
        "organization": {"label": "Organization", "label_modifier": lambda o: o.name},
    },
)


class UserSettingForm(BaseUserSettingForm):
    organizations = fields.SelectMultipleField("Organizations")
