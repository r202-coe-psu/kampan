import datetime

import mongoengine as me


class FeedbackScore(me.EmbeddedDocument):
    """คะแนน 1-5 ของคำถามหนึ่งข้อ (key ตรงกับ kampan.utils.car_reservation_feedback.QUESTION_GROUPS)"""

    key = me.StringField(required=True)
    score = me.IntField(required=True, min_value=1, max_value=5)


class CarReservationFeedback(me.Document):
    """ผลประเมินความพึงพอใจของใบขอใช้รถ (ระบบจองรถ) หนึ่งใบขอมีได้หนึ่งผลประเมิน

    คำถามกำหนดตายตัวในโค้ด จึงไม่ต้องมี template ต่อ org และไม่ปะปนกับ
    CarFeedbackTemplate/CarFeedbackResponse ของระบบ DIIS
    """

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    reservation = me.ReferenceField("CarReservation", dbref=True, required=True)
    creator = me.ReferenceField("User", dbref=True)
    car = me.ReferenceField("Car", dbref=True)
    driver = me.ReferenceField("User", dbref=True)
    scores = me.ListField(me.EmbeddedDocumentField(FeedbackScore))
    comment = me.StringField(default="")
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    meta = {
        "collection": "car_reservation_feedbacks",
        "indexes": [
            {"fields": ["reservation"], "unique": True},
            ("organization", "-created_date"),
        ],
    }

    def score_of(self, key):
        for answer in self.scores:
            if answer.key == key:
                return answer.score
        return None
