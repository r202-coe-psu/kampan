import datetime

from flask_wtf import FlaskForm, file
from wtforms import Form, ValidationError, fields, validators

from kampan import models
from kampan.models.procurement import check_item_sum

from .money_validators import MoneyPlaces

MONEY_RANGE_MESSAGE = "จำนวนเงินต้องอยู่ระหว่าง 0 ถึง 1,000,000,000,000"
REQUIRED_MESSAGE = "กรุณากรอกข้อมูล"


def money_field(label: str, required: bool = True) -> fields.DecimalField:
    presence = validators.InputRequired(message=REQUIRED_MESSAGE) if required else validators.Optional()
    return fields.DecimalField(
        label,
        places=2,
        rounding=None,
        validators=[
            presence,
            validators.NumberRange(min=0, max=1e12, message=MONEY_RANGE_MESSAGE),
            MoneyPlaces(),
        ],
    )


class DateInputField(fields.DateField):
    """DateField ที่ใช้กับ <input type="date"> พร้อมข้อความ error ภาษาไทย"""

    def process_formdata(self, valuelist):
        try:
            super().process_formdata(valuelist)
        except ValueError:
            raise ValueError("รูปแบบวันที่ไม่ถูกต้อง")


class MemberMultipleField(fields.SelectMultipleField):
    """เลือกผู้รับผิดชอบได้หลายคน choices ต้องเป็นสมาชิกของหน่วยงานที่กำลังดูอยู่เท่านั้น (view เติมให้)"""

    def pre_validate(self, form):
        allowed = {str(value) for value, _ in self.choices or []}
        if any(str(value) not in allowed for value in self.data or []):
            raise ValidationError("ผู้รับผิดชอบต้องเป็นสมาชิกของหน่วยงานนี้")


class InstallmentForm(Form):
    installment_id = fields.HiddenField()
    due_date = DateInputField(
        "วันครบกำหนด",
        validators=[validators.InputRequired(message="กรุณาระบุวันครบกำหนด")],
    )
    paid_date = DateInputField("วันที่จ่าย", validators=[validators.Optional()])
    payment_number = fields.StringField(
        "เลขที่เอกสาร",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    paid_amount = money_field("ยอดที่จ่ายจริง (บาท)", required=False)

    def validate_paid_date(self, field):
        if field.data is None and (self.payment_number.data or self.paid_amount.data is not None):
            raise ValidationError("กรุณาระบุวันที่จ่าย")


class ProcurementItemForm(Form):
    item_id = fields.HiddenField()
    name = fields.StringField(
        "ชื่อรายการย่อย",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    category = fields.SelectField("ประเภท", choices=models.ITEM_CATEGORY_CHOICES)
    account_code = fields.SelectField(
        "ผังบัญชี",
        choices=[("", "- ไม่ระบุ -")] + models.ACCOUNT_CODE_CHOICES,
        validators=[validators.Optional()],
    )
    start_date = DateInputField(
        "วันที่เริ่มต้น",
        validators=[validators.InputRequired(message="กรุณาระบุวันที่เริ่มต้น")],
    )
    end_date = DateInputField(
        "วันที่สิ้นสุด",
        validators=[validators.InputRequired(message="กรุณาระบุวันที่สิ้นสุด")],
    )
    amount = money_field("ยอดเงินของรายการย่อย (บาท)")
    details = fields.TextAreaField(
        "รายละเอียด (S/N, รหัสครุภัณฑ์ ฯลฯ)",
        validators=[validators.Optional()],
    )
    brand = fields.StringField("ยี่ห้อ", validators=[validators.Optional(), validators.Length(max=100)])
    model_name = fields.StringField("รุ่น", validators=[validators.Optional(), validators.Length(max=100)])
    winner = fields.StringField("ผู้ชนะ", validators=[validators.Optional(), validators.Length(max=200)])
    unit_price = money_field("ราคาต่อหน่วย (บาท)", required=False)
    note = fields.TextAreaField("หมายเหตุ", validators=[validators.Optional()])
    responsible_by = MemberMultipleField("ผู้รับผิดชอบ", choices=[], coerce=str)
    reminder_kind = fields.SelectField("ประเภทการเตือน", choices=models.REMINDER_KIND_CHOICES, default="ma")
    requires_activation = fields.BooleanField("ต้อง activate เมื่อครบกำหนด")
    installments = fields.FieldList(fields.FormField(InstallmentForm), min_entries=1)

    def validate_end_date(self, field):
        if self.start_date.data and field.data and field.data < self.start_date.data:
            raise ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

    def validate_installments(self, field):
        if not field.entries:
            raise ValidationError("รายการย่อยต้องมีอย่างน้อย 1 งวด")


class ProcurementHeaderForm(FlaskForm):
    psu_disbursement_number = fields.StringField(
        "เลขที่ ม.อ.เบิกจ่าย",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=128)],
    )
    name = fields.StringField(
        "ชื่อ MA",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    company = fields.StringField(
        "บริษัท",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    total_amount = money_field("ยอดเงินรวมของ MA (บาท)")
    image = fields.FileField(
        "รูปภาพ",
        validators=[file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )
    items = fields.FieldList(fields.FormField(ProcurementItemForm), min_entries=1)
    # เวลาแก้ไขล่าสุดตอนเปิดฟอร์มแก้ไข (กันบันทึกทับการแก้ / การจ่ายงวดของคนอื่นที่เกิดระหว่างนั้น)
    version = fields.HiddenField()

    sum_error = None

    def set_member_choices(self, choices: list[tuple[str, str]]) -> None:
        for entry in self.items:
            entry.form.responsible_by.choices = choices

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators=extra_validators)

        # ตรวจผลรวมเมื่อยอดทุกช่องอ่านได้แล้วเท่านั้น (ช่องที่ผิดรูปแบบมี error ของตัวเองอยู่แล้ว)
        amount_fields = [self.total_amount] + [entry.form.amount for entry in self.items]
        if any(field.errors or field.data is None for field in amount_fields):
            return valid

        self.sum_error = check_item_sum(self.total_amount.data, (entry.form.amount.data for entry in self.items))
        if self.sum_error:
            self.total_amount.errors.append(self.sum_error)
            return False
        return valid


class InstallmentPaymentForm(FlaskForm):
    paid_date = DateInputField(
        "วันที่จ่าย",
        default=datetime.date.today,
        validators=[validators.InputRequired(message="กรุณาระบุวันที่จ่าย")],
    )
    payment_number = fields.StringField(
        "เลขที่เอกสาร",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    paid_amount = money_field("ยอดที่จ่ายจริง (บาท)", required=False)


class EditImageForm(FlaskForm):
    image = fields.FileField(
        "รูปภาพใหม่",
        validators=[file.FileAllowed(["png", "jpg", "jpeg"], "อนุญาตเฉพาะไฟล์ png และ jpg")],
    )


class ProductFilterForm(FlaskForm):
    name = fields.StringField(
        "ค้นหา",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    category = fields.SelectField(
        "ประเภท",
        choices=[("", "ทั้งหมด")] + models.ITEM_CATEGORY_CHOICES,
        validators=[validators.Optional()],
    )
    payment_status = fields.SelectField(
        "สถานะการจ่ายเงิน",
        choices=[("", "ทั้งหมด")] + models.PAYEMENT_STATUS_CHOICES,
        validators=[validators.Optional()],
    )
