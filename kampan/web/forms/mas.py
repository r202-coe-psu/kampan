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
        "reservable_amount",
        "status",
        "editable",
        "remaining_amount",
        "reservable_amount",
    ],
    field_args={
        "mas_code": {"label": "รหัสแหล่งเงิน (MAS Code)"},
        "description": {"label": "รายละเอียด"},
        "amount": {"label": "งบประมาณทั้งหมด"},
        "direction": {"label": "ทิศทาง"},
        "year": {"label": "ปีงบประมาณ (พ.ศ.)"},
    },
)


class MASForm(BaseMASForm):
    pass
