from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
from .fields import TagListField, TextListField
import datetime
from flask_mongoengine.wtf import model_form
from kampan import models


class AdminApproveForm(FlaskForm):
    sent_item_date = fields.DateTimeField(
        "วันที่ส่งมอบพัสดุ",
        format="%d/%m/%Y %H:%M",
        widget=widgets.TextInput(),
        validators=[validators.InputRequired()],
        default=datetime.datetime.now,
    )
