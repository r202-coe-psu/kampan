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
    main_category = me.StringField(required=True, max_length=100)
    sub_category = me.StringField(required=True, max_length=100)
    name = me.StringField(required=True, max_length=200)
    item_description = me.StringField()
    amount = me.DecimalField(required=True, min_value=0, precision=2)
    budget = me.DecimalField(required=True, min_value=0, precision=2)
    actual_cost = me.DecimalField(required=True, min_value=0, precision=2)
    status = me.StringField(max_length=20, choices=STATUS_CHOICES, default="active")

    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
