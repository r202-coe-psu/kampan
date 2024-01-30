import mongoengine as me
import datetime


class Supplier(me.Document):
    meta = {"collection": "suppliers"}

    name = me.StringField(required=True, max_length=256)
    description = me.StringField()
    address = me.StringField(required=True, max_length=256)

    status = me.StringField(default="active")
    tax_id = me.StringField(required=True, max_length=256, default="")
    contact = me.StringField(max_length=256)
    email = me.StringField(required=True, max_length=256)
    phone = me.ListField(me.StringField())

    organization = me.ReferenceField("Organization", dbref=True)

    created_by = me.ReferenceField("User", dbref=True)
    last_modifier = me.ReferenceField("User", dbref=True, required=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
