import mongoengine as me
import datetime


CAR_APPLICATION_STATUS = [
    ("pending on header", "รอหัวหน้าฝ่ายอนุมัติ"),
    ("pending on director", "รอพัสดุเสนอ ผอ."),
    ("pending on admin", "รอพัสดุอนุมัติ"),
    ("active", "อนุมัติสำเร็จ"),
    ("denied by header", "ปฏิเสธ"),
    ("denied by director", "ปฏิเสธ"),
    ("denied by admin", "ปฏิเสธ"),
    ("disactive", "ยกเลิก"),
]


MOTORCYCLE_APPLICATION_STATUS = [
    ("pending", "รอการอนุมัติ"),
    ("active", "อนุมัติสำเร็จ"),
    ("returned", "ส่งคืนสำเร็จ"),
    ("denied", "ปฏิเสธ"),
    ("disactive", "ยกเลิก"),
]


TRAVEL_TYPE = [
    ("round trip", "ไป-กลับ"),
    ("one way", "เที่ยวเดียว"),
]

USING_TYPE = [
    ("general", "ใช้รถทั่วไป"),
    ("airport transfer", "รับส่งสนามบิน"),
    # เสนอผอ.
    ("out of town", "ไปต่างจังหวัด"),
]


class VehicleApplication:
    request_reason = me.StringField(
        default="", max_length=516, required=True
    )  # เหตุผลที่ต้องการใช้
    approved_reason = me.StringField(default="", max_length=516)  # เหตุผลที่อนุมัติ
    denied_reason = me.StringField(default="", max_length=516)  # เหตุผลที่ไม่อนุมัติ

    location = me.StringField(
        default="", max_length=516, required=True
    )  # สถานที่ต้องการจะไป

    departure_datetime = me.DateTimeField(
        required=True, default=datetime.datetime.now
    )  # วันเวลาออกเดินทาง
    return_datetime = me.DateTimeField(default=datetime.datetime.now)  # วันเวลากลับ

    creator = me.ReferenceField("User", dbref=True)
    updater = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)


class CarApplication(VehicleApplication, me.Document):
    meta = {"collection": "car_applications"}

    using_type = me.StringField(default="", choices=USING_TYPE)  # ประเภทการใช้รถ
    travel_type = me.StringField(
        default="one way", choices=TRAVEL_TYPE
    )  # ประเภทการเดินทาง

    flight_datetime = me.DateTimeField(default=datetime.datetime.now)  # วันเวลาบิน

    passenger_number = me.IntField(min_value=0, required=True, default=0)

    car = me.ReferenceField("Car", dbref=True, required=True)

    status = me.StringField(default="pending on header", choices=CAR_APPLICATION_STATUS)

    def get_status(self):
        key_color = {
            "denied by header": "red",
            "denied by director": "red",
            "denied by admin": "red",
            "approved": "green",
            "pending on director": "orange",
            "pending on admin": "orange",
            "pending on header": "orange",
            "disactive": "red",
            "active": "blue",
        }
        return f'<td data-label="Status" class="{key_color[self.status]}"><span class="ui {key_color[self.status]} text">{self.get_status_display()}</span></td>'


class MotorcycleApplication(VehicleApplication, me.Document):
    meta = {"collection": "motorcycle_applications"}

    motorcycle = me.ReferenceField("Motorcycle", dbref=True, required=True)
    last_mileage = me.IntField(min_value=0, required=True, default=0)

    status = me.StringField(default="pending", choices=MOTORCYCLE_APPLICATION_STATUS)

    def get_status(self):
        key_color = {
            "denied": "red",
            "returned": "green",
            "pending": "orange",
            "disactive": "red",
            "active": "blue",
        }
        return f'<td data-label="Status" class="{key_color[self.status]}"><span class="ui {key_color[self.status]} text">{self.get_status_display()}</span></td>'
