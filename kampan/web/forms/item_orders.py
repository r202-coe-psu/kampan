from flask_wtf import FlaskForm
from wtforms import fields, validators
from .fields import TagListField, TextListField

from flask_mongoengine.wtf import model_form
from kampan import models

BaseOrderItemForm = model_form(
    models.OrderItem,
    FlaskForm,
    exclude=["created_date", "updated_date", "approval_status", "status", "created_by"],
    field_args={
        "description": {"label": "คำอธิบาย"},
    },
)


class OrderItemForm(BaseOrderItemForm):
    pass


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
