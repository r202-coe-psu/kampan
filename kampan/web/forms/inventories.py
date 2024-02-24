from dataclasses import field
from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from wtforms import fields, validators, widgets
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
        # "item": {
        #     "label": "อุปกรณ์",
        #     "label_modifier": lambda i: f"{i.barcode_id} ({i.name})",
        # },
        "position": {
            "label": "ตำแหน่ง",
            "label_modifier": lambda p: f"{p.description} ({p.warehouse.name})",
        },
        "warehouse": {"label": "คลังอุปกรณ์", "label_modifier": lambda w: w.name},
        "quantity": {"label": "จำนวนทั้งหมด"},
        "price": {"label": "ราคา (ชุดละ)"},
    },
)


class InventoryForm(BaseInventoryForm):
    item = fields.SelectField("อุปกรณ์")
    calendar_select = fields.DateTimeField("วันที่เริ่มต้น", format="%Y-%m-%d")
    calendar_end = fields.DateTimeField("วันที่สุดท้าย", format="%Y-%m-%d")
    calendar_month_year = fields.DateTimeField("กรุณาเลือกเดือนและปี", format="%Y-%m")
    calendar_year = fields.DateTimeField("กรุณาเลือกปี", format="%Y")


class UploadInventoryFileForm(FlaskForm):
    upload_file = fields.FileField(
        "*** อัปโหลดเฉพาะไฟล์ที่เป็นไฟล์ .xlsx เท่านั้น ***",
        validators=[FileAllowed(["xlsx"], "xlsx only")],
    )


class SearchStartEndDateForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น", format="%d/%m/%Y", widget=widgets.TextInput()
    )
    end_date = fields.DateField(
        "วันที่สุดท้าย", format="%d/%m/%Y", widget=widgets.TextInput()
    )
    item = fields.SelectField("อุปกรณ์", validate_choice=False, validators=None)


class SearchMonthYearForm(FlaskForm):
    month_year = fields.MonthField(
        "เดือนที่เลือก", format="%m/%Y", widget=widgets.TextInput()
    )


class SearchYearForm(FlaskForm):
    year = fields.IntegerField("ปีที่เลือก")
