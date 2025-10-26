from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators

from kampan import models

BaseRequisitionProgressForm = model_form(
    models.RequisitionProgress,
    FlaskForm,
    exclude=[
        "requisition",
        "purchaser",
        "updated_date",
        "updated_by",
    ],
)


class RequisitionProgressForm(BaseRequisitionProgressForm):
    pass
