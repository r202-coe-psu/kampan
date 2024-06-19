from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
import datetime
from kampan import models


class AllItemReport(FlaskForm):
    categories = fields.SelectField(
        "หมวดหมู่",
        choices=[("", "หมวดหมู่")],
        validators=[validators.Optional()],
    )
    start_date = fields.DateField(
        "วันที่เริ่ม",
        format="%d/%m/%Y",
        widget=widgets.TextInput(),
        validators=[validators.Optional()],
        render_kw={"placeholder": "วันที่เริ่ม"},
    )
    end_date = fields.DateField(
        "วันที่สิ้นสุด",
        format="%d/%m/%Y",
        widget=widgets.TextInput(),
        validators=[validators.Optional()],
        render_kw={"placeholder": "วันที่สิ้นสุด"},
    )


class ItemReport(AllItemReport):
    item = fields.SelectField(
        "วัสดุ",
        validators=[validators.InputRequired()],
    )
