import mongoengine as me
import datetime


class Warehouse(me.Document):
    meta = {"collection": "warehouses"}
    status = me.StringField(default="active")
    name = me.StringField(required=True, max_length=256)
    description = me.StringField()

    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now())
