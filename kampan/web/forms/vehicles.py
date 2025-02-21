from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, widgets
from kampan import models

BaseCarForm = model_form(
    models.vehicles.Car,
    FlaskForm,
    exclude=[
        "organization",
        "created_date",
        "updated_date",
        "creator",
        "updater",
        "status",
        "image",
    ],
    field_args={
        "license_plate": {"label": "ป้ายทะเบียนรถ"},
        "description": {"label": "รายละเอียด/ลักษณะ"},
    },
)


class CarForm(BaseCarForm):
    upload_image = fields.FileField(
        "รูปภาพ",
        validators=[FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )


BaseMotorcycleForm = model_form(
    models.vehicles.Motorcycle,
    FlaskForm,
    exclude=[
        "organization",
        "created_date",
        "updated_date",
        "creator",
        "updater",
        "status",
        "image",
    ],
    field_args={
        "license_plate": {"label": "ป้ายทะเบียนรถ"},
        "description": {"label": "รายละเอียด/ลักษณะ"},
        "last_mileage": {"label": "เลขไมล์สุดท้าย"},
    },
)


class MotorcycleForm(BaseMotorcycleForm):
    upload_image = fields.FileField(
        "รูปภาพ",
        validators=[FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )
