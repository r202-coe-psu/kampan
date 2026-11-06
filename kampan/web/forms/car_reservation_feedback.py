from flask_wtf import FlaskForm
from wtforms import fields, validators

from kampan.utils import car_reservation_feedback as questions

SCORE_CHOICES = [
    (score, str(score))
    for score in range(questions.SCORE_MIN, questions.SCORE_MAX + 1)
]


def _score_field(label):
    return fields.RadioField(
        label,
        choices=SCORE_CHOICES,
        coerce=int,
        validators=[validators.InputRequired(message="กรุณาให้คะแนน")],
    )


# คำถามกำหนดในโค้ด จึงสร้างฟิลด์คะแนนต่อข้อจาก QUESTION_GROUPS
FeedbackForm = type(
    "FeedbackForm",
    (FlaskForm,),
    {
        **{key: _score_field(text) for key, text in questions.SCORE_QUESTIONS},
        "comment": fields.TextAreaField(
            "ข้อเสนอแนะเพิ่มเติม",
            validators=[validators.Optional(), validators.Length(max=2000)],
        ),
    },
)
