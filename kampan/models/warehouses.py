import mongoengine as me
import datetime
import bson


class Warehouse(me.Document):
    meta = {"collection": "warehouses"}

    name = me.StringField(required=True, max_length=256)
    # printed_name = me.StringField(required=True)
    description = me.StringField()
    status = me.StringField(default="active")

    organization = me.ReferenceField("Organization", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
