from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators

from kampan import models

BaseRequisitionTimelineForm = model_form(
    models.RequisitionTimeline,
    FlaskForm,
    exclude=[
        "requisition",
        "purchaser",
        "updated_date",
        "updated_by",
    ],
)


class RequisitionTimelineForm(BaseRequisitionTimelineForm):
    pass
