"""ฟอร์มแบบประเมินความพึงพอใจการใช้รถของระบบจองรถ: แบบประเมินปรับแต่งได้ต่อรถ"""

from wtforms import fields, validators, widgets

from kampan.web.forms.thai_messages import ThaiFlaskForm


class CarFeedbackTemplateForm(ThaiFlaskForm):
    name = fields.StringField(
        "ชื่อแบบประเมิน",
        validators=[validators.DataRequired(message="กรุณาระบุชื่อแบบประเมิน")],
    )
    description = fields.StringField("รายละเอียด")
    cars = fields.SelectMultipleField(
        "รถยนต์", validators=[validators.DataRequired(message="กรุณาเลือกรถยนต์")]
    )
    # JSON ของคำถามที่ตัวสร้างคำถามฝั่งเบราว์เซอร์ประกอบขึ้น: view แยกและตรวจด้วย parse_questions_payload
    questions_data = fields.HiddenField()


class CarFeedbackTemplateDeleteForm(ThaiFlaskForm):
    """ฟอร์มเปล่าไว้บังคับตรวจ CSRF token ของคำสั่งลบแบบประเมิน"""


class CarFeedbackResponseFilterForm(ThaiFlaskForm):
    organization_id = fields.HiddenField()
    car_id = fields.SelectField(
        "รถยนต์",
        validators=[validators.Optional()],
        validate_choice=False,
    )
    driver_id = fields.SelectField(
        "พนักงานขับรถ",
        validators=[validators.Optional()],
        validate_choice=False,
    )
    car_reservation_id = fields.SelectField(
        "เที่ยวรถ",
        validators=[validators.Optional()],
        validate_choice=False,
    )


def get_dynamic_feedback_form(template, trip_choices=None, default_trip_id=None):
    class DynamicFeedbackForm(ThaiFlaskForm):
        pass

    if trip_choices:
        setattr(
            DynamicFeedbackForm,
            "car_reservation",
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
