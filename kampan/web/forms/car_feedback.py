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
    car = fields.SelectField(
        "รถยนต์", validators=[validators.DataRequired(message="กรุณาเลือกรถยนต์")]
    )


def get_dynamic_feedback_form(template):
    class DynamicFeedbackForm(FlaskForm):
        pass

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
