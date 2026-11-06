from flask_wtf import FlaskForm
from wtforms import SelectField, SelectMultipleField, validators

from kampan.models.car_flow_positions import SNOR_POSITIONS

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
    for key, label in SNOR_POSITIONS:
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

    return type("CarFlowPositionForm", (FlaskForm,), fields)
