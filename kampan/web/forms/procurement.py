from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators
from kampan.models.procurement import Procurement

BaseProcurementForm = model_form(
    Procurement,
    FlaskForm,
    exclude=[
        "product_number",
        "created_date",
        "updated_date",
        "created_by",
        "last_updated_by",
    ],
    field_args={
        "name": {"label": "ชื่อรายการ"},
        "category": {"label": "ประเภท"},
        "asset_code": {"label": "รหัสครุภัณฑ์"},
        "amount": {"label": "จำนวนเงิน"},
        "period": {"label": "จำนวนงวด"},
        "company": {"label": "บริษัท"},
    },
)


class ProcurementForm(BaseProcurementForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด",
        validators=[validators.Optional()],
    )
