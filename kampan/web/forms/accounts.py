from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

import io

from PIL import Image, UnidentifiedImageError
from flask_wtf.file import FileAllowed, FileField, FileRequired
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


MAX_PICTURE_BYTES = 2 * 1024 * 1024


def validate_picture_content(form, field):
    """ไฟล์ต้องมีขนาดไม่เกิน 2 MB และเป็นภาพ JPEG/PNG จริง ไม่ใช่แค่นามสกุลถูก"""
    upload = field.data
    content = upload.read(MAX_PICTURE_BYTES + 1)
    upload.seek(0)

    if len(content) > MAX_PICTURE_BYTES:
        raise validators.ValidationError("ไฟล์รูปภาพต้องมีขนาดไม่เกิน 2 MB")

    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, SyntaxError):
        image_format = None

    if image_format not in ("JPEG", "PNG"):
        raise validators.ValidationError("ไฟล์ที่เลือกไม่ใช่รูปภาพ JPEG หรือ PNG")


class PictureForm(FlaskForm):
    picture = FileField(
        "รูปโปรไฟล์",
        validators=[
            FileRequired("กรุณาเลือกไฟล์รูปภาพ"),
            FileAllowed(["jpg", "jpeg", "png"], "อนุญาตเฉพาะไฟล์ภาพ JPEG หรือ PNG"),
            validate_picture_content,
        ],
    )


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
