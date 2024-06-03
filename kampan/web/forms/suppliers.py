from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseSupplierForm = model_form(
    models.Supplier,
    FlaskForm,
    exclude=[
        "last_modifier",
        "created_date",
        "updated_date",
        "status",
        "organization",
    ],
    field_args={
        "person_name": {"label": "ชื่อบุคคล"},
        "company_name": {"label": "ชื่อร้าน/บริษัท"},
        "address": {"label": "ที่อยู่"},
        "description": {"label": "คำอธิบาย"},
        "tax_id": {"label": "เลขผู้เสียภาษี"},
        "person_phone": {"label": "เบอร์โทรมือถือ"},
        "company_phone": {"label": "เบอร์โทรร้านค้า/บริษัท"},
        "email": {"label": "อีเมล"},
        "supplier_type": {"label": "ประเภทผู้จัดหาสินค้า"},
    },
)


class SupplierForm(BaseSupplierForm):
    pass
