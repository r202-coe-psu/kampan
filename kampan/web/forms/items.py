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
    exclude=["user", "created_date", "updated_date", "รูปสินค้า"],
    field_args={
        "name": {"label": "ชื่อสินค้า"},
        "description": {"label": "คำอธิบาย"},
        "weight": {"label": "น้ำหนัก (กิโลกรัม)"},
        "size": {"label": "ขนาด"},
        "categories": {"label": "หมวดหมุ่"},
        "unit": {"label": "หน่วย"},
        "minimum": {"label": "จำนวนสินค้าขั้นต่ำ -- (แจ้งเตือนเมื่อสินค้าใกล้หมดตามจำนวนสินค้าที่น้อยกว่าหรือเท่ากับจำนวนขั้นต่ำ)"},
        "barcode_id" : {"label": "รหัสบาร์โค้ด"}
    },
)


class ItemForm(BaseItemForm):
    categories = TagListField("หมวดหมู่", validators=[validators.Length(min=1)])
    img = fields.FileField(
        "รูปภาพสินค้า", validators=[FileAllowed(["png", "jpg"], "อณุญาตเฉพาะไฟล์ png และ jpg")]
    )


# class ItemForm(FlaskForm):

#     name = fields.StringField(validators=[validators.InputRequired()])
#     description = fields.StringField()
#     weight = fields.FloatField(default=0)
#     size = fields.EmbeddedDocumentField(ItemSize)
#     categories = TagListField(
#         "Categories", validators=[validators.InputRequired(), validators.Length(min=1)]
#     )
