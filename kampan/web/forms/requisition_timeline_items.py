from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField, HiddenField, DecimalField
from datetime import date
from kampan import models


class RequisitionTimelineItemFilterForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น", format="%Y-%m-%d", validators=[validators.Optional()]
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด", format="%Y-%m-%d", validators=[validators.Optional()]
    )
    user = fields.SelectField(
        "ผู้รับผิดชอบ",
        choices=[],
    )


class ExportExcelForm(FlaskForm):
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
