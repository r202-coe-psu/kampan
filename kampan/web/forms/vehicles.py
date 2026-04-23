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
        "last_mileage": {"label": "เลขไมล์สุดท้าย"},
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


class CarFeedbackForm(FlaskForm):
    start_datetime = fields.DateTimeField(
        "เวลาเริ่มต้น", format="%Y-%m-%dT%H:%M", validators=[validators.DataRequired()]
    )
    end_datetime = fields.DateTimeField(
        "เวลาสิ้นสุด", format="%Y-%m-%dT%H:%M", validators=[validators.DataRequired()]
    )
    driver_politeness_score = fields.IntegerField(
        "คะแนน (1-5)",
        validators=[
            validators.DataRequired(),
            validators.NumberRange(min=1, max=5, message="คะแนนต้องอยู่ระหว่าง 1 ถึง 5"),
        ],
    )
    driving_safety_score = fields.IntegerField(
        "คะแนน (1-5)",
        validators=[
            validators.DataRequired(),
            validators.NumberRange(min=1, max=5, message="คะแนนต้องอยู่ระหว่าง 1 ถึง 5"),
        ],
    )
    car_cleanliness_score = fields.IntegerField(
        "คะแนน (1-5)",
        validators=[
            validators.DataRequired(),
            validators.NumberRange(min=1, max=5, message="คะแนนต้องอยู่ระหว่าง 1 ถึง 5"),
        ],
    )
    overall = fields.IntegerField(
        "คะแนน (1-5)",
        validators=[
            validators.DataRequired(),
            validators.NumberRange(min=1, max=5, message="คะแนนต้องอยู่ระหว่าง 1 ถึง 5"),
        ],
    )
    comment = fields.TextAreaField("ความคิดเห็น", validators=[validators.Optional()])
