import mongoengine as me
import datetime
from bson import ObjectId

QUESTION_TYPE = (
    ("score", "คะแนน"),
    ("text", "ข้อความ"),
    ("boolean", "ใช่/ไม่ใช่"),
    ("multiple_choice", "เลือกได้หลายข้อ"),
    ("single_choice", "เลือกได้ข้อเดียว"),
)


class QuestionTemplate(me.EmbeddedDocument):
    question_id = me.ObjectIdField(required=True, default=ObjectId)
    question_text = me.StringField(required=True)
    question_type = me.StringField(choices=QUESTION_TYPE, required=True)
    choice_list = me.ListField(me.StringField())
    is_required = me.BooleanField(default=False)


class Answer(me.EmbeddedDocument):
    question_id = me.ObjectIdField(required=True)
    answer_score = me.IntField(min_value=1, max_value=5)
    answer_text = me.StringField()
    answer_boolean = me.BooleanField()
    answer_choices = me.ListField(me.StringField())


class CarFeedbackTemplate(me.Document):
    name = me.StringField(required=True)
    car = me.ReferenceField("Car", required=True)
    description = me.StringField(default="")
    questions = me.ListField(me.EmbeddedDocumentField(QuestionTemplate))
    meta = {"collection": "car_feedback_templates"}


class CarFeedbackResponse(me.Document):
    feedback_template = me.ReferenceField("CarFeedbackTemplate", required=True)
    car = me.ReferenceField("Car", required=True)
    answers = me.ListField(me.EmbeddedDocumentField(Answer))
    created_date = me.DateTimeField(default=datetime.datetime.now)

    meta = {"collection": "car_feedback_responses"}
