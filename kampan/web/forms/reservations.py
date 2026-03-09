from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField, HiddenField, DecimalField


class SearchReservationForm(FlaskForm):
    requisition_code = fields.StringField("เลขที่ใบขอซื้อ")
    reserved_by = fields.StringField("ผู้จอง")
    reservation_status = fields.SelectField(
        "สถานะการจอง",
        choices=[("", "ทั้งหมด"), ("reserved", "จองแล้ว"), ("finished", "เบิกแล้ว")],
        validators=[validators.Optional()],
    )
    reserved_date = fields.DateField(
        "วันที่จอง", format="%Y-%m-%d", validators=[validators.Optional()]
    )
    amount = DecimalField(
        "จำนวนเงินที่จอง",
        places=2,
        rounding=None,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )
    actual_amount = DecimalField(
        "จำนวนเงินที่ใช้จริง",
        places=2,
        rounding=None,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
    )
