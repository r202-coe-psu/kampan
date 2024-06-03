from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField
from flask_wtf.file import FileAllowed

from flask_mongoengine.wtf import model_form
from kampan import models

BaseItemRegisterationForm = model_form(
    models.RegistrationItem,
    FlaskForm,
    exclude=["created_date", "created_by", "bill"],
    field_args={
        "description": {"label": "คำอธิบาย"},
        "receipt_id": {"label": "เลขกำกับใบเสร็จ"},
    },
)


class ItemRegisterationForm(BaseItemRegisterationForm):
    bill_file = fields.FileField(
        "*** อัปโหลดเฉพาะบิลที่เป็นไฟล์ PDF เท่านั้น ***",
        validators=[FileAllowed(["pdf"], "PDF only")],
    )
    supplier = fields.SelectField("ร้านค้า")
