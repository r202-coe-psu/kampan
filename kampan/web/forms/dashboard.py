from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
import datetime
from kampan import models


class AllItemReport(FlaskForm):
    item = fields.SelectField(
        "วัสดุ",
        choices=[("", "วัสดุ")],
        validators=[validators.Optional()],
    )
    categories = fields.SelectField(
        "หมวดหมู่",
        choices=[("", "หมวดหมู่")],
        validators=[validators.Optional()],
    )
    quarter = fields.SelectField("ไตรมาส")
    # end_date = fields.DateField(
    #     "วันที่สิ้นสุด",
    #     format="%d/%m/%Y",
    #     widget=widgets.TextInput(),
    #     validators=[validators.Optional()],
    #     render_kw={"placeholder": "วันที่สิ้นสุด"},
    # )


class ItemReport(FlaskForm):
    item = fields.SelectField(
        "วัสดุ",
        choices=[("", "วัสดุ")],
        validators=[validators.InputRequired()],
    )
    # start_date = fields.DateField(
    #     "วันที่เริ่มต้น",
    #     format="%d/%m/%Y",
    #     widget=widgets.TextInput(),
    #     validators=[validators.Optional()],
    #     render_kw={"placeholder": "วันที่เริ่มต้น"},
    # )
    # end_date = fields.DateField(
    #     "วันที่สิ้นสุด",
    #     format="%d/%m/%Y",
    #     widget=widgets.TextInput(),
    #     validators=[validators.Optional()],
    #     render_kw={"placeholder": "วันที่สิ้นสุด"},
    # )
    quarter = fields.SelectField("ไตรมาส")
