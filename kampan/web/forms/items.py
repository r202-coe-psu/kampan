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
    exclude=[
        "created_by",
        "created_date",
        "updated_date",
        "image",
        "last_updated_by",
        "notification_status",
    ],
    field_args={
        "name": {"label": "ชื่อ"},
        "description": {"label": "คำอธิบาย"},
        # "categories": {"label": "หมวดหมู่"},
        "minimum": {"label": "จำนวนขั้นต่ำที่ต้องการแจ้งเตือน (ขั้นต่ำของหน่วยนับใหญ่)"},
        "barcode_id": {"label": "บาร์โค้ด"},
        "set_": {"label": "จำนวน (หน่วยนับใหญ่)"},
        "set_unit": {"label": "หน่วยนับใหญ่"},
        "piece_per_set": {"label": "จำนวน (หน่วยนับเล็กต่อหน่วยนับใหญ่)"},
        "piece_unit": {"label": "หน่วยนับเล็ก"},
        "remark": {"label": "หมายเหตุ"},
    },
)


class ItemForm(BaseItemForm):
    categories = fields.SelectField("หมวดหมู่")
    img = fields.FileField(
        "รูปภาพ",
        validators=[FileAllowed(["png", "jpg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )
    item_format = fields.SelectField("รูปแบบวัสดุ", choices=models.items.ITEM_FORMAT)


class SearchItemForm(FlaskForm):
    item = fields.SelectField("วัสดุ", validate_choice=False)
    categories = fields.SelectField("หมวดหมู่", validate_choice=False)


class UploadFileForm(FlaskForm):
    upload_file = fields.FileField(
        "อัปโหลดไฟล์",
        validators=[FileAllowed(["xlsx"], "อนุญาตเฉพาะไฟล์ xlsx")],
    )
