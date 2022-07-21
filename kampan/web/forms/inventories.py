from dataclasses import field
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseInventoryForm = model_form(
    models.Inventory,
    FlaskForm,
    exclude=[
        "registeration_date",
        "expiration_date",
        "user",
        "remain",
    ],
    field_args={
        "item": {"label": "สินค้า", "label_modifier": lambda i: f"{i.barcode_id} ({i.name})"
        },
        "position": {
            "label": "ตำแหน่ง",
            "label_modifier": lambda p: f"{p.description} ({p.warehouse.name})",
        },
        "warehouse": {"label": "คลังสินค้า", "label_modifier": lambda w: w.name},
        "quantity": {"label": "จำนวนทั้งหมด"},
        "price": {"label": "ราคา"},
    },
)


class InventoryForm(BaseInventoryForm):
    bill_file = fields.FileField(
        "*** อัปโหลดเฉพาะบิลที่เป็นไฟล์ PDF เท่านั้น ***", validators=[FileAllowed(["pdf"], "PDF only")]
    )
    calendar_select = fields.DateTimeField("เลือกวันที่เพื่อแสดงข้อมูล", format="%Y-%m-%d")