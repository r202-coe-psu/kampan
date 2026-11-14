import datetime

from flask_wtf import FlaskForm
from wtforms import Form, ValidationError, fields, validators

from kampan import models
from kampan.models.procurement import (
    MAX_INSTALLMENTS_MESSAGE,
    MAX_INSTALLMENTS_PER_ITEM,
    MAX_SUB_ITEMS_MESSAGE,
    MAX_SUB_ITEMS_PER_ITEM,
    MAX_REMINDER_OFFSET_DAYS,
    check_item_sum,
)
from kampan.utils.date_utils import parse_thai_date

from .money_validators import MoneyPlaces

MONEY_RANGE_MESSAGE = "จำนวนเงินต้องอยู่ระหว่าง 0 ถึง 1,000,000,000,000"
REQUIRED_MESSAGE = "กรุณากรอกข้อมูล"
MONEY_INVALID_MESSAGE = "จำนวนเงินไม่ถูกต้อง"


class MoneyDecimalField(fields.DecimalField):
    """DecimalField ที่ไม่รับ NaN / sNaN / Infinity (sNaN ทำให้ NumberRange ล่มเป็น 500)"""

    def process_formdata(self, valuelist):
        super().process_formdata(valuelist)
        if self.data is not None and not self.data.is_finite():
            self.data = None
            raise ValueError(MONEY_INVALID_MESSAGE)


def money_field(label: str, required: bool = True) -> fields.DecimalField:
    presence = validators.InputRequired(message=REQUIRED_MESSAGE) if required else validators.Optional()
    return MoneyDecimalField(
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


class DivisionMultipleField(fields.SelectMultipleField):
    """เลือกฝ่ายได้หลายฝ่าย choices ต้องเป็นฝ่ายของหน่วยงานที่กำลังดูอยู่เท่านั้น (view เติมให้)"""

    def pre_validate(self, form):
        allowed = {str(value) for value, _ in self.choices or []}
        if any(str(value) not in allowed for value in self.data or []):
            raise ValidationError("ฝ่ายต้องเป็นของหน่วยงานนี้")


class OffsetCheckboxField(fields.SelectMultipleField):
    """checkbox ช่วงเตือนล่วงหน้า ค่าต้องอยู่ใน REMINDER_OFFSET_CHOICES"""

    def pre_validate(self, form):
        allowed = {value for value, _ in self.choices or []}
        if any(value not in allowed for value in self.data or []):
            raise ValidationError("ช่วงเตือนไม่ถูกต้อง")


OFFSET_DAYS_MESSAGE = f"จำนวนวันเตือนต้องเป็นจำนวนเต็ม 1–{MAX_REMINDER_OFFSET_DAYS}"


def _filled(field_list) -> list[str]:
    return [(entry.data or "").strip() for entry in field_list.entries if (entry.data or "").strip()]


class InstallmentForm(Form):
    """งวด: วันครบกำหนด และจำนวนเงินของงวด"""

    installment_id = fields.HiddenField()
    due_date = DateInputField(
        "วันที่",
        validators=[validators.InputRequired(message="กรุณาระบุวันครบกำหนด")],
    )
    amount = money_field("จำนวนเงิน (บาท)", required=False)


class ItemDetailForm(Form):
    brand = fields.StringField("ยี่ห้อ", validators=[validators.Optional(), validators.Length(max=100)])
    model_name = fields.StringField("รุ่น", validators=[validators.Optional(), validators.Length(max=100)])
    serial_number = fields.StringField("S/N", validators=[validators.Optional(), validators.Length(max=100)])
    asset_code = fields.StringField("รหัสครุภัณฑ์", validators=[validators.Optional(), validators.Length(max=100)])
    details = fields.StringField(
        "รายละเอียด",
        validators=[validators.Optional(), validators.Length(max=255)],
    )

    def is_blank(self) -> bool:
        return not any(
            (field.data or "").strip()
            for field in (self.brand, self.model_name, self.serial_number, self.asset_code, self.details)
        )


class ProcurementItemForm(Form):
    item_id = fields.HiddenField()
    name = fields.StringField(
        "ชื่อรายการ",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    category = fields.SelectField("ประเภท", choices=models.MA_CATEGORY_CHOICES, default="ma")
    quantity = fields.IntegerField(
        "จำนวน",
        default=1,
        validators=[validators.Optional(), validators.NumberRange(min=1, message="จำนวนต้องไม่น้อยกว่า 1")],
    )
    unit = fields.StringField("หน่วยนับ", validators=[validators.Optional(), validators.Length(max=50)])
    unit_price = money_field("จำนวนเงินต่อหน่วย (บาท)", required=False)
    amount = money_field("จำนวนเงินรวม (บาท)")
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
    has_sub_item_sn = fields.BooleanField("ระบุ S/N")
    has_sub_item_asset = fields.BooleanField("ระบุรหัสครุภัณฑ์")
    # อ่านไม่เกิน MAX + 1 แถว แล้วให้ validate_sub_items ปฏิเสธ ไม่ตัดทิ้งเงียบ ๆ
    sub_items = fields.FieldList(fields.FormField(ItemDetailForm), min_entries=0, max_entries=MAX_SUB_ITEMS_PER_ITEM + 1)
    winner = fields.StringField("ผู้ชนะ", validators=[validators.Optional(), validators.Length(max=200)])
    note = fields.TextAreaField("หมายเหตุ", validators=[validators.Optional()])
    responsible_divisions = DivisionMultipleField("ฝ่ายที่มองเห็น", choices=[], coerce=str)
    responsible_by = MemberMultipleField("ผู้รับผิดชอบ", choices=[], coerce=str)
    reminder_kind = fields.SelectField("ประเภทการเตือน", choices=models.REMINDER_KIND_CHOICES, default="ma")
    requires_activation = fields.BooleanField("ต้อง activate เมื่อครบกำหนด")
    expiry_reminder_offsets = OffsetCheckboxField("เตือนหมดอายุล่วงหน้า", choices=models.REMINDER_OFFSET_CHOICES)
    payment_reminder_offsets = OffsetCheckboxField(
        "เตือนจ่ายงวดล่วงหน้า", choices=models.PAYMENT_REMINDER_OFFSET_CHOICES
    )
    # ช่องว่างไม่นับ (แถวที่ยังไม่กรอก)
    reminder_offsets_days = fields.FieldList(fields.StringField(), label="เตือนหมดอายุล่วงหน้า (วัน) กำหนดเอง")
    custom_reminder_dates = fields.FieldList(fields.StringField(), label="วันที่เตือนเจาะจง (พ.ศ.)")
    # เปิด = แบ่งจ่ายเป็นงวด (กรอกวันครบกำหนดเอง) ปิด = จ่ายครั้งเดียว งวดเดียวครบกำหนดในวันสิ้นสุด (ระบบตั้งให้)
    installment_mode = fields.BooleanField("แบ่งจ่ายเป็นงวด")
    # อ่านไม่เกิน MAX + 1 งวด (กัน request ที่ส่งงวดมาหลักหมื่น) แล้วให้ validate_installments ปฏิเสธ ไม่ตัดทิ้งเงียบ ๆ
    installments = fields.FieldList(
        fields.FormField(InstallmentForm), min_entries=1, max_entries=MAX_INSTALLMENTS_PER_ITEM + 1
    )

    def validate(self, extra_validators=None):
        # ปิดแบ่งงวด: ไม่ใช้แถวงวดที่ส่งมา (ระบบสร้างงวดเดียวจากวันสิ้นสุด) จึงไม่ validate
        if not self.installment_mode.data:
            self.installments.entries = []
        return super().validate(extra_validators=extra_validators)

    def validate_end_date(self, field):
        if self.start_date.data and field.data and field.data < self.start_date.data:
            raise ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

    def validate_sub_items(self, field):
        if len(field.entries) > MAX_SUB_ITEMS_PER_ITEM:
            raise ValidationError(MAX_SUB_ITEMS_MESSAGE)

    def validate_installments(self, field):
        if not self.installment_mode.data:
            return
        if not getattr(self, "is_draft", False) and not field.entries:
            raise ValidationError("รายการย่อยต้องมีอย่างน้อย 1 งวด")
        if len(field.entries) > MAX_INSTALLMENTS_PER_ITEM:
            raise ValidationError(MAX_INSTALLMENTS_MESSAGE)

    def validate_reminder_offsets_days(self, field):
        days = []
        for text in _filled(field):
            if not text.isdigit() or not 1 <= int(text) <= MAX_REMINDER_OFFSET_DAYS:
                raise ValidationError(f"{OFFSET_DAYS_MESSAGE} ({text})")
            if int(text) in days:
                raise ValidationError(f"จำนวนวันเตือนซ้ำ ({text})")
            days.append(int(text))

    def validate_custom_reminder_dates(self, field):
        dates = []
        for text in _filled(field):
            try:
                value = parse_thai_date(text)
            except ValueError as error:
                raise ValidationError(f"{error} ({text})")
            if value in dates:
                raise ValidationError(f"วันที่เตือนซ้ำ ({text})")
            dates.append(value)

    def get_reminder_offsets_days(self) -> list[int]:
        """จำนวนวันที่กรอกเอง (เรียกหลัง validate ผ่านแล้ว)"""
        return [int(text) for text in _filled(self.reminder_offsets_days)]

    def get_custom_reminder_dates(self) -> list[datetime.datetime]:
        """วันที่เตือนเจาะจงเป็น ค.ศ. เที่ยงคืน (เรียกหลัง validate ผ่านแล้ว)"""
        return [
            datetime.datetime.combine(parse_thai_date(text), datetime.time.min)
            for text in _filled(self.custom_reminder_dates)
        ]


PSU_NUMBER_REQUIRED_MESSAGE = (
    "กรุณากรอกเลขที่ ม.อ.เบิกจ่าย เมื่อมีรายการที่ไม่แบ่งจ่ายเป็นงวด (จ่ายแล้วตอนสร้าง MA)"
)


class ProcurementHeaderForm(FlaskForm):
    # บังคับเมื่อมีรายการที่ไม่แบ่งจ่ายเป็นงวด (จ่ายแล้วตอนสร้าง MA) ถ้าทุกรายการแบ่งจ่ายเป็นงวด
    # ใส่เลขที่เบิกจ่ายตอนบันทึกจ่ายแต่ละงวดแทน ดู validate()
    psu_disbursement_number = fields.StringField(
        "เลขที่ มอ เบิกจ่าย",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    disbursement_date = DateInputField(
        "ลงวันที่",
        validators=[validators.Optional()],
    )
    name = fields.StringField(
        "ชื่อโครงการ",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    company = fields.StringField(
        "ซื้อจาก (บริษัท)",
        validators=[validators.InputRequired(message=REQUIRED_MESSAGE), validators.Length(max=255)],
    )
    total_amount = money_field("ยอดเงินรวม (บาท)")
    items = fields.FieldList(fields.FormField(ProcurementItemForm), min_entries=1)
    # เวลาแก้ไขล่าสุดตอนเปิดฟอร์มแก้ไข (กันบันทึกทับการแก้ / การจ่ายงวดของคนอื่นที่เกิดระหว่างนั้น)
    version = fields.HiddenField()

    sum_error = None

    def __init__(self, *args, is_draft=False, mode="full", **kwargs):
        """mode: full = ฟอร์มเต็ม (สร้าง / ต่ออายุ / แก้แบบร่าง) · header = แก้เฉพาะหัว MA ที่ไม่ใช่แบบร่าง
        · item = แก้รายการย่อยเดียวของ MA ที่ไม่ใช่แบบร่าง (ยอดรวมหัวคำนวณจากผลรวมรายการ ไม่รับจากฟอร์ม)

        ช่องที่ mode นั้นไม่รับถูกตัดออกจากฟอร์ม ค่าที่ส่งมาเกินจึงถูกเมินที่ฝั่ง server
        """
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.is_draft = is_draft
        if mode == "header":
            del self.items
            del self.total_amount
        elif mode == "item":
            del self.total_amount
            for name in ("psu_disbursement_number", "disbursement_date", "name", "company"):
                delattr(self, name)
        if is_draft:
            self.prepare_for_draft()

    def item_entries(self) -> list:
        return list(self._fields["items"]) if "items" in self._fields else []

    def prepare_for_draft(self):
        self.psu_disbursement_number.validators = [
            v
            for v in self.psu_disbursement_number.validators
            if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
        ]
        self.psu_disbursement_number.validators.insert(0, validators.Optional())
        self.psu_disbursement_number.flags.required = False

        self.company.validators = [
            v
            for v in self.company.validators
            if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
        ]
        self.company.validators.insert(0, validators.Optional())
        self.company.flags.required = False

        self.total_amount.validators = [
            v
            for v in self.total_amount.validators
            if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
        ]
        self.total_amount.validators.insert(0, validators.Optional())
        self.total_amount.flags.required = False

        for entry in self.items:
            entry.form.is_draft = True
            entry.form.start_date.validators = [
                v
                for v in entry.form.start_date.validators
                if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
            ]
            entry.form.start_date.validators.insert(0, validators.Optional())
            entry.form.start_date.flags.required = False

            entry.form.end_date.validators = [
                v
                for v in entry.form.end_date.validators
                if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
            ]
            entry.form.end_date.validators.insert(0, validators.Optional())
            entry.form.end_date.flags.required = False

            entry.form.amount.validators = [
                v
                for v in entry.form.amount.validators
                if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
            ]
            entry.form.amount.validators.insert(0, validators.Optional())
            entry.form.amount.flags.required = False

            entry.form.name.validators = [
                v
                for v in entry.form.name.validators
                if not isinstance(v, (validators.InputRequired, validators.DataRequired, validators.Optional))
            ]
            entry.form.name.validators.insert(0, validators.Optional())
            entry.form.name.flags.required = False

    def set_member_choices(self, choices: list[tuple[str, str]]) -> None:
        for entry in self.item_entries():
            entry.form.responsible_by.choices = choices

    def set_division_choices(self, choices: list[tuple[str, str]]) -> None:
        for entry in self.item_entries():
            entry.form.responsible_divisions.choices = choices

    def validate(self, extra_validators=None):
        if getattr(self, "is_draft", False):
            self.prepare_for_draft()
        valid = super().validate(extra_validators=extra_validators)
        if getattr(self, "is_draft", False) or self.mode != "full":
            return valid

        if not (self.psu_disbursement_number.data or "").strip() and any(
            not entry.form.installment_mode.data for entry in self.items
        ):
            self.psu_disbursement_number.errors = [*self.psu_disbursement_number.errors, PSU_NUMBER_REQUIRED_MESSAGE]
            valid = False
        # ตรวจผลรวมเมื่อยอดทุกช่องอ่านได้แล้วเท่านั้น (ช่องที่ผิดรูปแบบมี error ของตัวเองอยู่แล้ว)
        amount_fields = [self.total_amount] + [entry.form.amount for entry in self.items]
        if any(field.errors or field.data is None for field in amount_fields):
            return valid

        self.sum_error = check_item_sum(self.total_amount.data, (entry.form.amount.data for entry in self.items))
        if self.sum_error:
            self.total_amount.errors.append(self.sum_error)
            return False
        return valid


class ConfirmActionForm(FlaskForm):
    """ปุ่มยืนยันที่ไม่มีช่องกรอก (ยกเลิกบันทึกจ่าย, ไม่ต่ออายุ): บังคับ POST + CSRF ผ่าน validate_on_submit"""


PAYMENT_NUMBER_REQUIRED_MESSAGE = "กรุณากรอกเลขที่ ม.อ.เบิกจ่ายของงวดนี้ก่อนบันทึกจ่าย"


class InstallmentPaymentForm(FlaskForm):
    paid_date = DateInputField(
        "วันที่จ่าย",
        default=datetime.date.today,
        validators=[validators.InputRequired(message="กรุณาระบุวันที่จ่าย")],
    )
    payment_number = fields.StringField(
        "เลขที่ ม.อ.เบิกจ่าย / เลขที่เอกสาร",
        validators=[validators.DataRequired(message=PAYMENT_NUMBER_REQUIRED_MESSAGE), validators.Length(max=128)],
    )
    paid_amount = money_field("ยอดที่จ่ายจริง (บาท)", required=False)


class ManualReminderLogForm(FlaskForm):
    """บันทึกการแจ้งเตือนที่ทำเอง เช่น โทรแจ้ง (#30)"""

    contact_date = fields.StringField(
        "วันที่ติดต่อ (พ.ศ.)",
        validators=[validators.InputRequired(message="กรุณาระบุวันที่ติดต่อ")],
    )
    recipients = fields.StringField(
        "ผู้ที่ติดต่อ",
        validators=[validators.Optional(), validators.Length(max=255)],
    )
    note = fields.TextAreaField(
        "บันทึก",
        validators=[validators.InputRequired(message="กรุณากรอกบันทึก"), validators.Length(max=2000)],
    )

    def validate_contact_date(self, field):
        try:
            parse_thai_date(field.data)
        except ValueError as error:
            raise ValidationError(f"วันที่ติดต่อ: {error}")

    def get_contact_date(self) -> datetime.datetime:
        return datetime.datetime.combine(parse_thai_date(self.contact_date.data), datetime.time.min)


# ตัวเลือกเรียงลำดับของหน้ารายการ MA (query string ``sort``) ดู views/procurement/ma_pagination.py
SORT_OPTIONS = [
    ("created_desc", "สร้างล่าสุด → เก่าสุด"),
    ("created_asc", "สร้างเก่าสุด → ล่าสุด"),
    ("end_asc", "ใกล้หมดอายุที่สุด"),
    ("end_desc", "หมดอายุหลังสุด"),
    ("due_asc", "ใกล้วันจ่ายงวดที่สุด"),
    ("name_asc", "ชื่อ ก → ฮ"),
]


def sort_field() -> fields.SelectField:
    return fields.SelectField("เรียงลำดับ", choices=SORT_OPTIONS, validators=[validators.Optional()])


# สถานะการต่ออายุที่กรองในรายการ MA ได้ (ไม่มีแบบร่าง และไม่แสดงค่าเดิม active / pending แยก)
RENEWAL_FILTER_STATUSES = ("review", "renewal-requested", "renewed", "disactive")


class ProductFilterForm(FlaskForm):
    name = fields.StringField(
        "ค้นหา",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    category = fields.SelectField(
        "ประเภท",
        choices=[("", "ทั้งหมด")] + models.MA_CATEGORY_CHOICES,
        validators=[validators.Optional()],
    )
    payment_status = fields.SelectField(
        "สถานะการจ่ายเงิน",
        choices=[("", "ทั้งหมด")] + models.PAYEMENT_STATUS_CHOICES,
        validators=[validators.Optional()],
    )
    usage_status = fields.SelectField(
        "สถานะการใช้งาน",
        choices=[("", "ทั้งหมด")] + models.USAGE_STATUS_CHOICES,
        validators=[validators.Optional()],
    )
    renewal_status = fields.SelectField(
        "สถานะการต่ออายุ",
        choices=[("", "ทั้งหมด")]
        + [(value, label) for value, label in models.RENEWAL_STATUS_CHOICES if value in RENEWAL_FILTER_STATUSES],
        validators=[validators.Optional()],
    )
    sort = sort_field()


class NonRenewalFilterForm(FlaskForm):
    """ตัวกรองหน้ารายการไม่ต่ออายุ (query string ทั้งหมดเป็น GET จึงไม่ใช้ CSRF)"""

    class Meta:
        csrf = False

    name = fields.StringField(
        "ค้นหา",
        validators=[validators.Optional(), validators.Length(max=128)],
    )
    category = fields.SelectField(
        "ประเภท",
        choices=[("", "ทั้งหมด")] + models.MA_CATEGORY_CHOICES,
        validators=[validators.Optional()],
    )
    company = fields.StringField("บริษัท", validators=[validators.Optional(), validators.Length(max=128)])
    # choices เติมจากสมาชิกของหน่วยงานที่กำลังดูอยู่ (view)
    responsible = fields.SelectField("ผู้รับผิดชอบ", choices=[("", "ทั้งหมด")], validators=[validators.Optional()])
    end_from = DateInputField("สิ้นสุดตั้งแต่", validators=[validators.Optional()])
    end_to = DateInputField("สิ้นสุดถึง", validators=[validators.Optional()])
    sort = sort_field()
