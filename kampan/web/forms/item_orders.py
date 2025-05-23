from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseOrderItemForm = model_form(
    models.OrderItem,
    FlaskForm,
    exclude=[
        "created_date",
        "updated_date",
        "approval_status",
        "status",
        "created_by",
        "sent_item_date",
    ],
    field_args={
        "description": {"label": "วัตถุประสงค์"},
    },
)


class OrderItemForm(BaseOrderItemForm):
    head_endorser = fields.SelectField(
        "เลือกหัวหน้าฝ่ายที่ต้องการให้อนุมัติ",
        validators=[validators.InputRequired()],
        choices=[("", "เลือกหัวหน้าฝ่ายที่ต้องการให้อนุมัติ")],
    )
    # admin_approver = fields.SelectField(
    #     "เลือกเจ้าหน้าที่พัสดุที่ต้องการให้อนุมัติ",
    #     validators=[validators.InputRequired()],
    #     choices=[("", "เลือกเจ้าหน้าที่พัสดุที่ต้องการให้อนุมัติ")],
    # )


def get_approved_amount_form(items):
    class ApprovedAmountForm(FlaskForm):
        pass

    for item_id, name, quantity, max_range in items:
        setattr(
            ApprovedAmountForm,
            name,
            fields.IntegerField(
                id=item_id,
                label=name,
                default=quantity if quantity <= max_range else max_range,
                validators=[
                    validators.NumberRange(
                        min=0, max=max_range, message="ตัวเลขไม่ตรงตามเงื่อนไข"
                    ),
                ],
            ),
        )
    return ApprovedAmountForm()


class SearchStartEndDateForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สุดท้าย",
        validators=[validators.Optional()],
    )
    item = fields.SelectField(
        "วัสดุ", validate_choice=False, validators=None, choices=[("", "ไม่เลือก")]
    )


class SearchStartEndDateAndStatusForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สุดท้าย",
        validators=[validators.Optional()],
    )
    item = fields.SelectField(
        "สถานะ",
        validate_choice=False,
        validators=None,
        choices=[
            ("", "ทั้งหมด"),
            ("pending", "รอดำเนินการ"),
            ("approved", "อนุมัติ"),
            ("denied", "ปฏิเสธ"),
        ],
    )
