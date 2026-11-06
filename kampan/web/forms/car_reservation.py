from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
from wtforms import SelectField, SelectMultipleField

from kampan import models
from kampan.models.car_reservation_positions import RESERVATION_POSITIONS


class CarReservationForm(FlaskForm):
    """ฟอร์มยื่นคำขอใช้รถของระบบจองรถ ส่วนที่ใช้ร่วมกันทุกประเภท"""

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
        choices=models.car_reservations.PROVINCE_SCOPES,
        validators=[validators.Optional()],
    )
    confirm_urgent = fields.BooleanField("ยืนยันยื่นคำขอแบบเร่งด่วน")


class ApprovalDecisionForm(FlaskForm):
    comment = fields.StringField(
        "ความเห็น", validators=[validators.Optional(), validators.Length(max=516)]
    )


class DispatchDecisionForm(ApprovalDecisionForm):
    """ขั้นผู้จัดรถ: อนุมัติพร้อมระบุรถและพนักงานขับรถ

    choices ตั้งจากรถ/พนักงานขับรถของ org ตอนสร้างหน้า ส่วนการตรวจสิทธิ์และเวลาชนกัน
    อยู่ที่ engine จึงปิดการตรวจ choice ของ wtforms
    """

    car = fields.SelectField("รถ", choices=[], validate_choice=False)
    driver = fields.SelectField("พนักงานขับรถ", choices=[], validate_choice=False)


class DenyDecisionForm(FlaskForm):
    comment = fields.TextAreaField(
        "เหตุผลที่ไม่อนุมัติ",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )


class CancelRequestForm(FlaskForm):
    reason = fields.TextAreaField(
        "เหตุผลที่ยกเลิก (ถ้ามี)",
        validators=[validators.Optional(), validators.Length(max=516)],
    )


DRIVER_CANNOT_APPROVE = "พนักงานขับรถเป็นผู้อนุมัติไม่ได้"
NO_HOLDER_CHOICE = ("", "-- ยังไม่ระบุ --")


def build_position_form(member_choices, driver_ids):
    """ฟอร์มตั้งผู้ดำรงตำแหน่งทุกตำแหน่งในหน้าเดียว

    member_choices คือ [(user_id, ชื่อ)] ของสมาชิกที่ active ขององค์กร
    ผู้ใช้นอกรายการนี้จะไม่ผ่านการตรวจ choice ส่วน driver_ids คือ id ของคนขับรถ
    ซึ่งอยู่ในรายการเลือกแต่เป็นผู้อนุมัติไม่ได้
    """

    def not_a_driver(form, field):
        selected = field.data if isinstance(field.data, list) else [field.data]
        if any(user_id in driver_ids for user_id in selected if user_id):
            raise validators.ValidationError(DRIVER_CANNOT_APPROVE)

    fields = {}
    for key, label in RESERVATION_POSITIONS:
        fields[f"{key}_user"] = SelectField(
            label,
            choices=[NO_HOLDER_CHOICE] + list(member_choices),
            validators=[validators.Optional(), not_a_driver],
        )
        fields[f"{key}_delegates"] = SelectMultipleField(
            f"ผู้รักษาการ{label}",
            choices=list(member_choices),
            validators=[not_a_driver],
        )

    return type("CarReservationPositionForm", (FlaskForm,), fields)
