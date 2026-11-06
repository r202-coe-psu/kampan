import datetime

import mongoengine as me

RESERVATION_POSITIONS = [
    ("dispatcher", "ผู้จัดรถ"),
    ("vehicle_unit_head", "หัวหน้าหน่วยยานพาหนะ"),
    ("strategy_head", "หัวหน้างานยุทธศาสตร์และบริการกลาง"),
    ("physical_director", "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม"),
    ("vice_president_hatyai", "รองอธิการบดีวิทยาเขตหาดใหญ่"),
    ("president", "อธิการบดี"),
]


class CarReservationPosition(me.Document):
    meta = {
        "collection": "car_reservation_positions",
        "indexes": [{"fields": ["organization", "position_key"], "unique": True}],
    }

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    position_key = me.StringField(choices=RESERVATION_POSITIONS, required=True)
    user = me.ReferenceField("User", dbref=True)
    delegates = me.ListField(me.ReferenceField("User", dbref=True))
    updated_by = me.ReferenceField("User", dbref=True)
    updated_date = me.DateTimeField(default=datetime.datetime.now)

    @classmethod
    def holder(cls, organization, position_key):
        """ผู้ดำรงตำแหน่งขององค์กร (None ถ้ายังไม่ได้ตั้ง)"""
        position = cls.objects(
            organization=organization, position_key=position_key
        ).first()
        return position.user if position else None

    @classmethod
    def can_act(cls, organization, position_key, user):
        """ผู้ใช้ทำแทนตำแหน่งนี้ได้ ถ้าเป็นผู้ดำรงตำแหน่งหรือผู้รักษาการ"""
        position = cls.objects(
            organization=organization, position_key=position_key
        ).first()
        if not position or user is None:
            return False
        return user in ([position.user] + list(position.delegates))
