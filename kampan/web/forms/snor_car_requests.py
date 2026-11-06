from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets

from kampan import models


class SnorCarRequestForm(FlaskForm):
    """ฟอร์มยื่นคำขอใช้รถแบบ snor ส่วนที่ใช้ร่วมกันทุกประเภท"""

    requester_unit = fields.StringField(
        "คณะ/หน่วยงาน",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    phone = fields.StringField(
        "เบอร์โทรศัพท์ผู้ขอใช้รถ",
        validators=[validators.DataRequired(), validators.Length(max=32)],
    )
    location = fields.StringField(
        "สถานที่ปฏิบัติงาน",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    request_reason = fields.StringField(
        "เรื่อง/เหตุผลที่ต้องการใช้รถ",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    departure_date = fields.DateField(
        "วันออกเดินทาง", validators=[validators.InputRequired()]
    )
    departure_time = fields.TimeField(
        "เวลาออกเดินทาง", validators=[validators.InputRequired()]
    )
    return_date = fields.DateField(
        "วันกลับถึงมหาวิทยาลัย", validators=[validators.InputRequired()]
    )
    return_time = fields.TimeField(
        "เวลากลับถึงมหาวิทยาลัย", validators=[validators.InputRequired()]
    )
    passenger_number = fields.IntegerField(
        "จำนวนผู้โดยสาร",
        validators=[validators.InputRequired(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(),
    )
    province_scope = fields.SelectField(
        "พื้นที่เดินทาง",
        choices=models.snor_car_requests.PROVINCE_SCOPES,
        validators=[validators.Optional()],
    )


class ApprovalDecisionForm(FlaskForm):
    comment = fields.StringField(
        "ความเห็น", validators=[validators.Optional(), validators.Length(max=516)]
    )


class DenyDecisionForm(FlaskForm):
    comment = fields.TextAreaField(
        "เหตุผลที่ไม่อนุมัติ",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
