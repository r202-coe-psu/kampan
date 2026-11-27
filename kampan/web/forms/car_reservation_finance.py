from wtforms import fields, validators, widgets

from kampan.utils import car_reservation_finance as finance
from kampan.web.forms.thai_messages import ThaiFlaskForm


def money_field(label, step="0.01"):
    return fields.DecimalField(
        label,
        places=2,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(step=step, min=0),
    )


class FinanceForm(ThaiFlaskForm):
    """การเงินกรอกตัวเลขของใบเบิกค่าใช้จ่ายของ พขร. (ช่องที่ไม่กรอกถือเป็น 0)"""

    memo_number = fields.StringField(
        "ตามบันทึก ที่",
        render_kw={"placeholder": "เช่น มอ 123/2569"},
        validators=[
            validators.Optional(),
            validators.Length(
                max=finance.max_chars(finance.MEMO_NUMBER),
                message="ยาวเกินช่องในแบบฟอร์มใบเบิก (ไม่เกิน %(max)d ตัวอักษร)",
            ),
        ],
    )
    memo_date = fields.DateField("ลงวันที่", validators=[validators.Optional()])
    allowance_type = fields.StringField(
        "ประเภทค่าเบี้ยเลี้ยง",
        default="ประเภท ก",
        validators=[validators.Optional(), validators.Length(max=32)],
    )
    allowance_days = money_field("ค่าเบี้ยเลี้ยง จำนวน (วัน)", step="0.5")
    allowance_amount = money_field("ค่าเบี้ยเลี้ยง รวม (บาท)")
    lodging_days = money_field("ค่าเช่าที่พัก จำนวน (วัน)", step="0.5")
    lodging_amount = money_field("ค่าเช่าที่พัก รวม (บาท)")
    vehicle_cost = money_field("ค่าพาหนะ (บาท)")
    meal_rate_1 = money_field("เงินช่วยเหลือค่าอาหาร พขร. แถว 1 อัตรา (บาท/วัน)")
    meal_days_1 = money_field("เงินช่วยเหลือค่าอาหาร พขร. แถว 1 จำนวน (วัน)", step="0.5")
    meal_rate_2 = money_field("เงินช่วยเหลือค่าอาหาร พขร. แถว 2 อัตรา (บาท/วัน)")
    meal_days_2 = money_field("เงินช่วยเหลือค่าอาหาร พขร. แถว 2 จำนวน (วัน)", step="0.5")
    evidence_count = fields.IntegerField(
        "จำนวนเอกสารหลักฐาน (ฉบับ)",
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(min=0),
    )
