from flask_wtf import FlaskForm
from wtforms import fields, validators, widgets
from .fields import TagListField, TextListField

from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from kampan import models


BaseDivionForm = model_form(
    models.Division,
    FlaskForm,
    exclude=[
        "endorsers",
        "organization",
        "created_by",
        "last_updated_by",
        "created_date",
        "updated_date",
        "status",
    ],
    field_args={
        "name": {"label": "ชื่อ"},
        "description": {"label": "รายละเอียด"},
    },
)


class DivisionForm(BaseDivionForm):
    pass


class SearchDivisionStartEndDateForm(FlaskForm):
    start_date = fields.DateField(
        "วันที่เริ่มต้น",
        validators=[validators.Optional()],
    )
    end_date = fields.DateField(
        "วันที่สุดท้าย",
        validators=[validators.Optional()],
    )
    name = fields.SelectField(
        "แผนก",
        choices=[("", "Division")],
        validate_choice=False,
        validators=None,
        render_kw={"placeholder": "Division"},
    )


class DivisionAddMemberForm(FlaskForm):
    members = fields.SelectMultipleField(
        "สมาชิก",
        choices=[("", "Member")],
        validate_choice=False,
        validators=None,
        render_kw={"placeholder": "Member"},
    )
