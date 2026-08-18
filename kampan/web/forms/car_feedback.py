from flask_wtf import FlaskForm
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, widgets
from kampan import models


class CarFeedbackTemplateForm(FlaskForm):
    name = fields.StringField(
        "ชื่อแบบประเมิน",
        validators=[validators.DataRequired(message="กรุณาระบุชื่อแบบประเมิน")],
    )
    description = fields.StringField("รายละเอียด")
    cars = fields.SelectMultipleField(
        "รถยนต์", validators=[validators.DataRequired(message="กรุณาเลือกรถยนต์")]
    )


class CarFeedbackTemplateDeleteForm(FlaskForm):
    """ฟอร์มเปล่าไว้บังคับตรวจ CSRF token ของคำสั่งลบแบบประเมิน"""


class CarFeedbackResponseFilterForm(FlaskForm):
    car_id = fields.SelectField(
        "รถยนต์",
        validators=[validators.Optional()],
        validate_choice=False,
    )
    car_application_id = fields.SelectField(
        "เที่ยวรถ",
        validators=[validators.Optional()],
        validate_choice=False,
    )


def get_dynamic_feedback_form(template, trip_choices=None, default_trip_id=None):
    class DynamicFeedbackForm(FlaskForm):
        pass

    if trip_choices:
        setattr(
            DynamicFeedbackForm,
            "car_application",
            fields.SelectField(
                "เที่ยวที่ใช้บริการ",
                choices=trip_choices,
                default=default_trip_id,
                validators=[validators.DataRequired(message="กรุณาเลือกเที่ยวรถ")],
            ),
        )

    for q in template.questions:
        name = f"answer_{q.question_id}"
        req = (
            [validators.DataRequired(message="กรุณาตอบคำถามข้อนี้")]
            if q.is_required
            else []
        )

        if q.question_type == "score":
            setattr(
                DynamicFeedbackForm,
                name,
                fields.RadioField(
                    q.question_text,
                    choices=[
                        ("1", "1"),
                        ("2", "2"),
                        ("3", "3"),
                        ("4", "4"),
                        ("5", "5"),
                    ],
                    validators=req,
                ),
            )
        elif q.question_type == "text":
            setattr(
                DynamicFeedbackForm,
                name,
                fields.TextAreaField(q.question_text, validators=req),
            )
        elif q.question_type == "boolean":
            setattr(
                DynamicFeedbackForm,
                name,
                fields.RadioField(
                    q.question_text,
                    choices=[("True", "ใช่"), ("False", "ไม่ใช่")],
                    validators=req,
                ),
            )
        elif q.question_type == "single_choice":
            setattr(
                DynamicFeedbackForm,
                name,
                fields.RadioField(
                    q.question_text,
                    choices=[(c, c) for c in q.choice_list],
                    validators=req,
                ),
            )
        elif q.question_type == "multiple_choice":
            setattr(
                DynamicFeedbackForm,
                name,
                fields.SelectMultipleField(
                    q.question_text,
                    choices=[(c, c) for c in q.choice_list],
                    option_widget=widgets.CheckboxInput(),
                    widget=widgets.ListWidget(prefix_label=False),
                    validators=req,
                ),
            )

    return DynamicFeedbackForm()
