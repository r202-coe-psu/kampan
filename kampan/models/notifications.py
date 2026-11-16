import datetime

import mongoengine as me

# เก็บแจ้งเตือนไว้ 90 วันแล้วให้ MongoDB ลบเอง (TTL index)
RETENTION_SECONDS = 90 * 24 * 60 * 60


class Notification(me.Document):
    """แจ้งเตือนในระบบหนึ่งรายการต่อผู้รับหนึ่งคน (ใช้ร่วมกันได้ทุก module)"""

    meta = {
        "collection": "notifications",
        "indexes": [
            ("organization", "user", "read_at", "-created_date"),
            {"fields": ["created_date"], "expireAfterSeconds": RETENTION_SECONDS},
        ],
    }

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    user = me.ReferenceField("User", dbref=True, required=True)
    actor = me.ReferenceField("User", dbref=True)

    module = me.StringField(required=True, max_length=64)
    event = me.StringField(required=True, max_length=64)
    ref = me.GenericReferenceField()

    title = me.StringField(required=True, max_length=256)
    message = me.StringField(default="", max_length=1024)
    url = me.StringField(default="", max_length=1024)

    read_at = me.DateTimeField()
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
