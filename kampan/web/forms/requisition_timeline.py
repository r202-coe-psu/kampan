from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField

from kampan import models

BaseRequisitionTimelineForm = model_form(
    models.RequisitionTimeline,
    FlaskForm,
    exclude=[
        "requisition",
        "purchaser",
        "updated_date",
        "updated_by",
        "created_date",
        "created_by",
        "status",
    ],
)


class RequisitionTimelineForm(BaseRequisitionTimelineForm):
    pass


class RequisitionCancelForm(FlaskForm):
    note = TextAreaField(
        "เหตุผลการยกเลิก",
        [validators.DataRequired(), validators.Length(max=500)],
    )
