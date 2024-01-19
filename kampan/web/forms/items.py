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
    exclude=["user", "created_date", "updated_date", "รูปอุปกรณ์"],
    field_args={
        "name": {"label": "ชื่ออุปกรณ์"},
        "description": {"label": "คำอธิบาย"},
        "weight": {"label": "น้ำหนัก (กิโลกรัม)"},
        "size": {"label": "ขนาด"},
        "categories": {"label": "หมวดหมุ่"},
        "unit": {"label": "หน่วย"},
        "minimum": {"label": "จำนวนอุปกรณ์ขั้นต่ำ -- (แจ้งเตือน)"},
        "barcode_id": {"label": "บาร์โค้ด"},
    },
)


class ItemForm(BaseItemForm):
    categories = TagListField("หมวดหมู่", validators=[validators.Length(min=1)])
    img = fields.FileField(
        "รูปภาพอุปกรณ์",
        validators=[FileAllowed(["png", "jpg"], "อณุญาตเฉพาะไฟล์ png และ jpg")],
    )


class SearchItemForm(FlaskForm):
    item = fields.SelectField("อุปกรณ์")
