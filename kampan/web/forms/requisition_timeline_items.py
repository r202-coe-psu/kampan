from flask_wtf import FlaskForm, file
from flask_mongoengine.wtf import model_form
from wtforms import fields, Form, validators, TextAreaField, HiddenField, DecimalField

from kampan import models


class RequisitionTimelineItemFilterForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น", format="%Y-%m-%d", validators=[validators.Optional()]
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด", format="%Y-%m-%d", validators=[validators.Optional()]
    )
