import datetime
import mongoengine as me

STATUS_CHOICES = [
    ("active", "ใช้งาน"),
    ("inactive", "ระงับชั่วคราว"),
    ("closed", "ปิดบัญชี"),
]
RESERVATION_STATUS_CHOICES = [
    ("reserved", "จองแล้ว"),
    ("finished", "เสร็จสิ้น"),
]


class MAS(me.Document):
    meta = {"collection": "mas", "strict": False}

    year = me.IntField(required=True, min_value=2500, max_value=2700)
    mas_code = me.StringField(required=True, max_length=50)
    description = me.StringField(required=True, max_length=200)
    direction = me.StringField(required=True, max_length=100)
    amount = me.DecimalField(required=True, min_value=0, max_value=1e12, precision=2)

    remaining_amount = me.DecimalField(
        required=True, min_value=0, max_value=1e12, precision=2
    )
    reservable_amount = me.DecimalField(
        required=True, min_value=0, max_value=1e12, precision=2
    )
    editable = me.BooleanField(default=True)
    status = me.StringField(max_length=20, choices=STATUS_CHOICES, default="active")
    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )


class Reservation(me.Document):
    meta = {"collection": "reservations"}
    requisition = me.ReferenceField("Requisition", required=True, dbref=True)
    mas = me.ReferenceField(MAS, required=True, dbref=True)
    amount = me.DecimalField(
        required=True, min_value=0, max_value=1e12, precision=2
    )  # ค่าที่จอง
    actual_amount = me.DecimalField(
        min_value=0, max_value=1e12, precision=2
    )  # ค่าที่ใช้จริง (อาจน้อยกว่าหรือเท่ากับ amount)
    reservation_status = me.StringField(
        max_length=20, choices=RESERVATION_STATUS_CHOICES, default="reserved"
    )
    status = me.StringField(max_length=20, default="active")
    reserved_by = me.ReferenceField("User", dbref=True)
    reserved_date = me.DateTimeField(required=True, default=datetime.datetime.now)
