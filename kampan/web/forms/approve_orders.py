from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
from .fields import TagListField, TextListField
import datetime
from flask_mongoengine.wtf import model_form
from kampan import models


class SupplierApproveForm(FlaskForm):
    # admin_approver = fields.SelectField(
    #     "เจ้าหน้าที่พัสดุที่จัดการวัสดุ",
    #     validators=[validators.InputRequired()],
    # )
    pass


class AdminApproveForm(FlaskForm):
    sent_item_date = fields.DateTimeField(
        "วันที่ส่งมอบพัสดุ",
        format="%Y-%m-%dT%H:%M",
        validators=[validators.InputRequired()],
        default=datetime.datetime.now,
    )


class OrderActionForm(FlaskForm):
    """ปุ่มอนุมัติ / ไม่อนุมัติใบเบิก: บังคับ POST + CSRF และรับเหตุผล (ถ้ามี)"""

    reason = fields.StringField("เหตุผล", validators=[validators.Optional()])
