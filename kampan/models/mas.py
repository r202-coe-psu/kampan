import datetime
import mongoengine as me

STATUS_CHOICES = [
    ("active", "ใช้งาน"),
    ("inactive", "ระงับชั่วคราว"),
    ("closed", "ปิดบัญชี"),
]


class MAS(me.Document):
    meta = {"collection": "mas"}

    mas_code = me.StringField(required=True, max_length=50)
    name = me.StringField(required=True, max_length=200)
    actual_amount = me.DecimalField(
        required=True, min_value=0, max_value=1e12, precision=2
    )
    reservable_amount = me.DecimalField(
        required=True, min_value=0, max_value=1e12, precision=2
    )

    status = me.StringField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )


class Reservation(me.Document):
    meta = {"collection": "reservations"}

    mas = me.ReferenceField(MAS, required=True, dbref=True)
    amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)
    reserved_by = me.ReferenceField("User", dbref=True)
    reserved_date = me.DateTimeField(required=True, default=datetime.datetime.now)
