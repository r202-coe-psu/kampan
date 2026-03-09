from datetime import date
from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import ValidationError
from kampan import models
from wtforms import fields, validators, widgets

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


class MASSearchForm(FlaskForm):
    year = fields.IntegerField(
        "ปีงบประมาณ (พ.ศ.)", render_kw={"placeholder": "ปีงบประมาณ"}
    )
    mas_code = fields.StringField(
        "รหัสแหล่งเงิน (MAS Code)", render_kw={"placeholder": "รหัสแหล่งเงิน"}
    )
    description = fields.StringField(
        "รายละเอียด", render_kw={"placeholder": "รายละเอียด"}
    )
    amount = fields.DecimalField(
        "จำนวนเงินที่ขอจัดตั้ง", render_kw={"placeholder": "จำนวนเงินที่ขอจัดตั้ง"}
    )


class ExportMASExcelForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        default=date(date.today().year, 1, 1),
        render_kw={"placeholder": "วันที่เริ่มต้น"},
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด",
        default=date(date.today().year, 12, 31),
        render_kw={"placeholder": "วันที่สิ้นสุด"},
    )

    def validate(self):
        if not super().validate():
            return False

        if self.start_date.data and self.end_date.data:
            if self.start_date.data > self.end_date.data:
                self.end_date.errors.append("End date must be after start date.")
                return False

        return True
