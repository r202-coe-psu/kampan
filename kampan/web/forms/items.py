from email.policy import default
from wsgiref.validate import validator
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators
from .fields import TagListField, TextListField
from kampan import models


BaseItemForm = model_form(
    models.Item,
    FlaskForm,
    exclude=["user", "created_date", "updated_date", "รูปภาพ"],
    field_args={
        "name": {"label": "ชื่อ"},
        "description": {"label": "คำอธิบาย"},
        "categories": {"label": "หมวดหมุ่"},
        "unit": {"label": "หน่วย"},
        "minimum": {"label": "จำนวนขั้นต่ำ -- (แจ้งเตือน)"},
        "barcode_id": {"label": "บาร์โค้ด"},
        "piece_per_set": {"label": "จำนวน (ชิ้น/ชุด)"},
    },
)


class ItemForm(BaseItemForm):
    categories = TagListField("หมวดหมู่", validators=[validators.Length(min=1)])
    img = fields.FileField(
        "รูปภาพ",
        validators=[FileAllowed(["png", "jpg"], "อณุญาตเฉพาะไฟล์ png และ jpg")],
    )


class SearchItemForm(FlaskForm):
    item = fields.SelectField("อุปกรณ์", validate_choice=False)
    categories = fields.SelectField("หมวดหมู่", validate_choice=False)
