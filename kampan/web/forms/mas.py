from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import ValidationError
from kampan import models

BaseMASForm = model_form(
    models.MAS,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "status",
    ],
    field_args={
        "mas_code": {"label": "รหัสแหล่งเงิน (MAS Code)"},
        "main_category": {"label": "หมวดรายจ่าย"},
        "sub_category": {"label": "หมวดรายจ่ายย่อย"},
        "name": {"label": "ชื่อรายการ"},
        "item_description": {"label": "รายละเอียดรายการ"},
        "amount": {"label": "จำนวนเงิน"},
        "budget": {"label": "ประมาณจ่าย"},
        "actual_cost": {"label": "จ่ายจริง"},
    },
)


class MASForm(BaseMASForm):
    def validate_mas_code(self, field):
        form_id = getattr(self, "id", None)
        q = models.MAS.objects(mas_code=field.data)
        if form_id:
            q = q.filter(id__ne=form_id.data)
        if q.first():
            raise ValidationError("รหัส MAS นี้ถูกใช้ไปแล้ว กรุณาใช้รหัสอื่น")
