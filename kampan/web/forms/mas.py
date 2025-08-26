from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, ValidationError
from kampan import models

BaseMASProjectForm = model_form(
    models.MASProject,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
        "organization",
    ],
    field_args={
        "mas_code": {
            "label": "รหัสแหล่งเงิน (MAS Code)",
            "validators": [validators.DataRequired(message="กรุณากรอกรหัสแหล่งเงิน")],
            "render_kw": {"placeholder": "เช่น 0.0EU310108.N28.66"},
        },
        "expense_category": {
            "label": "หมวดรายจ่าย",
            "validators": [validators.DataRequired(message="กรุณาเลือกหมวดรายจ่าย")],
        },
        "expense_subcategory": {
            "label": "หมวดรายจ่ายย่อย",
            "validators": [validators.DataRequired(message="กรุณาเลือกหมวดรายจ่ายย่อย")],
        },
        "project_name": {
            "label": "ชื่อโครงการ/รายการ",
            "validators": [validators.DataRequired(message="กรุณากรอกชื่อโครงการ")],
            "render_kw": {"placeholder": "เช่น โครงการจ้างเหมาพัฒนาฐานโครงสร้างระบบ..."},
        },
        "project_description": {
            "label": "รายละเอียดโครงการ",
            "render_kw": {"rows": 4, "placeholder": "อธิบายรายละเอียดโครงการ"},
        },
        "amount": {
            "label": "จำนวนเงิน (Amount)",
            "validators": [validators.DataRequired(message="กรุณากรอกจำนวนเงิน")],
            "render_kw": {"step": "0.01", "min": "0"},
        },
        "budget": {
            "label": "ประมาณจ่าย (Budget)",
            "validators": [validators.DataRequired(message="กรุณากรอกงบประมาณ")],
            "render_kw": {"step": "0.01", "min": "0"},
        },
        "actual_payment": {
            "label": "จ่ายจริง (Actual Payment)",
            "validators": [validators.Optional()],
            "render_kw": {"step": "0.01", "min": "0"},
        },
        "fiscal_year": {
            "label": "ปีงบประมาณ",
            "validators": [validators.Optional()],
            "render_kw": {"placeholder": "เช่น 2567"},
        },
        "start_date": {"label": "วันที่เริ่มโครงการ", "validators": [validators.Optional()]},
        "end_date": {"label": "วันที่สิ้นสุดโครงการ", "validators": [validators.Optional()]},
        "status": {
            "label": "สถานะ",
            "validators": [validators.DataRequired(message="กรุณาเลือกสถานะ")],
        },
        "responsible_by": {"label": "ผู้รับผิดชอบ"},
    },
)


class MASProjectForm(BaseMASProjectForm):
    """Form for creating and editing MAS projects"""

    def validate_end_date(self, field):
        """Validate that end date is after start date"""
        if self.start_date.data and field.data:
            if field.data < self.start_date.data:
                raise ValidationError("วันที่สิ้นสุดต้องมากกว่าหรือเท่ากับวันที่เริ่มต้น")

    def validate_amount(self, field):
        """Validate that amount is not negative"""
        if field.data is not None and field.data < 0:
            raise ValidationError("จำนวนเงินต้องมากกว่าหรือเท่ากับ 0")

    def validate_budget(self, field):
        """Validate that budget is not negative"""
        if field.data is not None and field.data < 0:
            raise ValidationError("งบประมาณต้องมากกว่าหรือเท่ากับ 0")

    def validate_actual_payment(self, field):
        """Validate that actual payment is not negative"""
        if field.data is not None and field.data < 0:
            raise ValidationError("จำนวนเงินที่จ่ายจริงต้องมากกว่าหรือเท่ากับ 0")

    def validate_fiscal_year(self, field):
        """Validate fiscal year format"""
        if field.data:
            try:
                year = int(field.data)
                if year < 2500 or year > 2700:  # Buddhist year range
                    raise ValidationError("ปีงบประมาณต้องอยู่ในช่วง 2500-2700")
            except ValueError:
                raise ValidationError("ปีงบประมาณต้องเป็นตัวเลข")

    def validate(self, extra_validators=None):
        """Custom validation for the entire form"""
        if not super().validate(extra_validators):
            return False

        # Check if actual payment exceeds budget
        if (
            self.actual_payment.data
            and self.budget.data
            and self.actual_payment.data > self.budget.data
        ):
            self.actual_payment.errors.append("จำนวนเงินที่จ่ายจริงไม่ควรเกินงบประมาณ")
            return False

        return True


class MASProjectSearchForm(FlaskForm):
    """Form for searching and filtering MAS projects"""

    fiscal_year = fields.SelectField(
        "ปีงบประมาณ", choices=[("", "ทั้งหมด")], validators=[validators.Optional()]
    )

    expense_category = fields.StringField(
        "หมวดรายจ่าย",
        validators=[validators.Optional()],
    )

    status = fields.StringField(
        "สถานะ",
        validators=[validators.Optional()],
    )

    search_term = fields.StringField(
        "ค้นหา",
        validators=[validators.Optional()],
        render_kw={"placeholder": "ค้นหาชื่อโครงการ, รหัส MAS หรือรายละเอียด"},
    )
