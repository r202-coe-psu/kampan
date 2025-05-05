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
            "denied by header": "text-error",
            "denied by director": "text-error",
            "denied by admin": "text-error",
            "approved": "text-green-500",
            "pending on director": "text-primary",
            "pending on admin": "text-primary",
            "pending on header": "text-primary",
            "disactive": "text-error",
            "active": "text-green-500",
        }
        return f'<td class="table-style" data-label="Status"><span class="{key_color[self.status]} font-medium">{self.get_status_display()}</span></td>'

    def get_reason(self):
        return self.approved_reason if self.status == "active" else self.denied_reason


class MotorcycleApplication(VehicleApplication, me.Document):
    meta = {"collection": "motorcycle_applications"}

    motorcycle = me.ReferenceField("Motorcycle", dbref=True, required=True)
    last_mileage = me.IntField(min_value=0, required=True, default=0)

    status = me.StringField(default="pending", choices=MOTORCYCLE_APPLICATION_STATUS)

    def get_status(self):
        key_color = {
            "denied": "text-error",
            "returned": "text-green-500",
            "pending": "text-orange-500",
            "disactive": "text-error",
            "active": "text-primary",
        }
        return f'<td class="table-style" data-label="Status"><span class="{key_color[self.status]} font-medium">{self.get_status_display()}</span></td>'

    def get_changed_mileage(self):
        last_motorcycle_application = (
            MotorcycleApplication.objects(
                status="returned",
                created_date__lt=self.created_date,
                motorcycle=self.motorcycle,
            )
            .order_by("-created_date")
            .first()
        )
        if not last_motorcycle_application or self.status != "returned":
            return "-"
        last_mileage = last_motorcycle_application.last_mileage
        return self.last_mileage - last_mileage

    def get_reason(self):
        return (
            self.approved_reason
            if self.status == "active" or self.status == "returned"
            else self.denied_reason
        )
