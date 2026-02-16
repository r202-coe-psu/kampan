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
        "name": {"label": "ชื่อรายการ"},
        "actual_amount": {"label": "จ่ายจริง"},
        "reservable_amount": {"label": "จำนวนเงินที่สามารถจองได้"},
    },
)


class MASForm(BaseMASForm):
    pass
