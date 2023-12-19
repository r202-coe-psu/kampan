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
        "item": {
            "label": "อุปกรณ์",
            "label_modifier": lambda i: f"{i.barcode_id} ({i.name})",
        },
        "position": {
            "label": "ตำแหน่ง",
            "label_modifier": lambda p: f"{p.description} ({p.warehouse.name})",
        },
        "warehouse": {"label": "คลังอุปกรณ์", "label_modifier": lambda w: w.name},
        "quantity": {"label": "จำนวนทั้งหมด"},
        "price": {"label": "ราคา (ชิ้นละ)"},
    },
)


class InventoryForm(BaseInventoryForm):
    calendar_select = fields.DateTimeField("วันที่เริ่มต้น", format="%Y-%m-%d")
    calendar_end = fields.DateTimeField("วันที่สุดท้าย", format="%Y-%m-%d")
    calendar_month_year = fields.DateTimeField("กรุณาเลือกเดือนและปี", format="%Y-%m")
    calendar_year = fields.DateTimeField("กรุณาเลือกปี", format="%Y")


class SearchStartEndDateForm(FlaskForm):
    start_date = fields.DateField("วันที่เริ่มต้น", format="%Y-%m-%d")
    end_date = fields.DateField("วันที่สุดท้าย", format="%Y-%m-%d")
