import datetime

import mongoengine as me

CAR_APPLICATION_STATUS = [
    ("pending on header", "รอหัวหน้าฝ่ายอนุมัติ"),
    ("pending on director", "รอ ผอ. อนุมัติ"),
    ("pending on admin", "รอพัสดุอนุมัติ"),
    ("active", "อนุมัติสำเร็จ"),
    ("completed", "เสร็จสิ้น"),
    ("denied by header", "ปฏิเสธ"),
    ("denied by director", "ปฏิเสธ"),
    ("denied by admin", "ปฏิเสธ"),
    ("pending", "รออนุมัติ"),
    ("denied", "ปฏิเสธ"),
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

AIRPORT_TRANSFER_TYPE = [
    ("pickup", "รับ"),
    ("dropoff", "ส่ง"),
]

USING_TYPE = [
    ("general", "ใช้รถทั่วไป"),
    ("airport transfer", "รับส่งสนามบิน"),
    # เสนอผอ.
    ("out of town", "ไปต่างจังหวัด"),
]


class VehicleApplication:
    request_reason = me.StringField(default="", max_length=516, required=True)  # เหตุผลที่ต้องการใช้
    approved_reason = me.StringField(default="", max_length=516)  # เหตุผลที่อนุมัติ
    denied_reason = me.StringField(default="", max_length=516)  # เหตุผลที่ไม่อนุมัติ

    location = me.StringField(default="", max_length=516, required=True)  # สถานที่ต้องการจะไป

    departure_datetime = me.DateTimeField(required=True, default=datetime.datetime.now)  # วันเวลาออกเดินทาง
    return_datetime = me.DateTimeField(default=datetime.datetime.now)  # วันเวลากลับ

    creator = me.ReferenceField("User", dbref=True)
    updater = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now, auto_now=True)
    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)


class CarApplicationApproval(me.EmbeddedDocument):
    approved_by = me.ReferenceField("User", dbref=True)
    approved_at = me.DateTimeField()


class StepApproval(me.EmbeddedDocument):
    step_key = me.StringField(required=True)
    label = me.StringField()
    decision = me.StringField(choices=[("approved", "อนุมัติ"), ("denied", "ปฏิเสธ")])
    decided_by = me.ReferenceField("User", dbref=True)
    decided_at = me.DateTimeField()
    comment = me.StringField(default="")


AUDIT_ACTIONS = [
    ("submitted", "ยื่นคำขอ"),
    ("edited", "แก้ไขคำขอ"),
    ("approved", "อนุมัติ"),
    ("denied", "ปฏิเสธ"),
]


class CarApplicationAuditLog(me.EmbeddedDocument):
    """ประวัติการเปลี่ยนแปลงของคำขอ: ใคร ทำอะไร ขั้นไหน เมื่อไร และค่าที่เปลี่ยน"""

    action = me.StringField(choices=AUDIT_ACTIONS, required=True)
    actor = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    step_key = me.StringField(default="")
    step_label = me.StringField(default="")
    comment = me.StringField(default="")
    # [{"field": "car", "label": "รถ", "old": "", "new": "กข-1234"}, ...]
    changes = me.ListField(me.DictField())

    def get_action_display(self):
        return dict(AUDIT_ACTIONS).get(self.action, self.action)

    def display_changes(self):
        """changes สำหรับแสดงผล: ค่าสถานะแปลงเป็นป้ายภาษาไทย"""
        labels = dict(CAR_APPLICATION_STATUS)
        return [
            {
                **change,
                "old": labels.get(change.get("old"), change.get("old")) if change.get("field") == "status" else change.get("old"),
                "new": labels.get(change.get("new"), change.get("new")) if change.get("field") == "status" else change.get("new"),
            }
            for change in self.changes
        ]


class CarApplication(VehicleApplication, me.Document):
    meta = {"collection": "car_applications"}
    phone = me.StringField(default="", max_length=32)
    # ประเภทการใช้รถ (ว่างได้สำหรับคำขอจาก car form template)
    using_type = me.StringField(default="", choices=USING_TYPE + [("", "-")])
    travel_type = me.StringField(default="one way", choices=TRAVEL_TYPE)  # ประเภทการเดินทาง
    airport_transfer_type = me.StringField()  # ประเภทการรับส่งสนามบิน (ตัวเลือกเสริม ไม่ตรวจสอบค่า)
    passenger_location = me.StringField(default="", max_length=516)  # รับผู้โดยสารที่ไหน
    flight_datetime = me.DateTimeField(default=datetime.datetime.now)  # วันเวลาบินไป
    flight_return_datetime = me.DateTimeField(default=datetime.datetime.now)  # วันเวลาบินกลับ
    flight_number = me.StringField(max_length=128, default="")
    flight_return_number = me.StringField(max_length=128, default="")

    passenger_number = me.IntField(min_value=0, required=True, default=0)

    car = me.ReferenceField("Car", dbref=True)
    # ประเภทของรถที่จัดให้ ณ ตอนอนุมัติ (เทียบกับ details.vehicle_kind ที่ผู้ขอเลือก)
    assigned_vehicle_type = me.StringField()
    driver = me.ReferenceField("User", dbref=True)
    division = me.ReferenceField("Division", dbref=True)

    status = me.StringField(default="pending on header", choices=CAR_APPLICATION_STATUS)
    last_mileage = me.IntField(min_value=0)
    last_mileage_before = me.IntField(min_value=0)

    # Embedded approvals
    header_approval = me.EmbeddedDocumentField(CarApplicationApproval)
    director_approval = me.EmbeddedDocumentField(CarApplicationApproval)
    admin_approval = me.EmbeddedDocumentField(CarApplicationApproval)

    # Car form template flow (None form_template = flow เดิม)
    form_template = me.ReferenceField("CarFormTemplate", dbref=True)
    template_snapshot = me.DictField()
    details = me.DictField(default=dict)
    current_step = me.IntField(min_value=0, default=0)
    step_approvals = me.ListField(me.EmbeddedDocumentField(StepApproval))
    audit_logs = me.ListField(me.EmbeddedDocumentField(CarApplicationAuditLog))

    def has_vehicle_type_mismatch(self):
        requested = (self.details or {}).get("vehicle_kind")
        return bool(
            requested
            and self.assigned_vehicle_type
            and requested != self.assigned_vehicle_type
        )

    def get_mile_before(self):
        last_car_application = (
            CarApplication.objects(
                status="completed",
                departure_datetime__lt=self.departure_datetime,
                car=self.car,
            )
            .order_by("-departure_datetime")
            .first()
        )
        if not last_car_application:
            return 0
        last_mileage = last_car_application.last_mileage
        return last_mileage

    @staticmethod
    def get_first_per_car(organization, status, order_by):
        # Mileage is tracked per car, so only one trip per car may have it entered: the oldest active task
        # or the latest completed trip (editing that also overwrites the car's current mileage)
        first_per_car = {}
        for car in CarApplication.objects(organization=organization, status=status).distinct("car"):
            first = (
                CarApplication.objects(organization=organization, status=status, car=car)
                .order_by(order_by)
                .only("id", "car", "departure_datetime", "driver")
                .first()
            )
            if first:
                first_per_car[car.id] = first
        return first_per_car

    @staticmethod
    def get_first_ids_per_car(organization, status, order_by):
        return {first.id for first in CarApplication.get_first_per_car(organization, status, order_by).values()}

    @staticmethod
    def get_oldest_active_per_car(organization):
        return CarApplication.get_first_per_car(organization, "active", "departure_datetime")

    @staticmethod
    def get_latest_completed_ids(organization):
        return CarApplication.get_first_ids_per_car(organization, "completed", "-departure_datetime")

    @staticmethod
    def get_oldest_active_ids(organization):
        return {first.id for first in CarApplication.get_oldest_active_per_car(organization).values()}

    def get_status(self):
        key_color = {
            "denied by header": "text-error",
            "denied by director": "text-error",
            "denied by admin": "text-error",
            "denied": "text-error",
            "pending": "text-primary",
            "approved": "text-green-500",
            "pending on director": "text-primary",
            "pending on admin": "text-primary",
            "pending on header": "text-primary",
            "disactive": "text-error",
            "active": "text-green-500",
            "completed": "text-gray-500",
        }
        return f'<td class="table-style" data-label="Status"><span class="{key_color[self.status]} font-medium">{self.get_status_display()}</span></td>'

    def get_reason(self):
        return self.approved_reason if self.status == "active" else self.denied_reason

    def get_departure_datetime(self):
        if self.travel_type == "one way":
            text = f"{self.departure_datetime.strftime('%d/%m/%Y %H:%M')} น."
        else:
            if self.departure_datetime.date() != self.return_datetime.date():
                text = (
                    f"{self.departure_datetime.strftime('%d/%m/%Y %H:%M')} น. - {self.return_datetime.strftime('%d/%m/%Y %H:%M')} น."
                )
            else:
                text = f"{self.departure_datetime.strftime('%d/%m/%Y %H:%M')} น. - {self.return_datetime.strftime('%H:%M')} น."
        return text

    def get_airport_transfer_type_display(self):
        if self.using_type != "airport transfer":
            return "-"
        if not self.airport_transfer_type:
            return "-"
        mapping = dict(AIRPORT_TRANSFER_TYPE)
        return mapping.get(self.airport_transfer_type, self.airport_transfer_type)


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
        # last_motorcycle_application = (
        #     MotorcycleApplication.objects(
        #         status="returned",
        #         created_date__lt=self.created_date,
        #         motorcycle=self.motorcycle,
        #     )
        #     .order_by("-created_date")
        #     .first()
        # )
        # if not last_motorcycle_application or self.status != "returned":
        #     return "-"
        # last_mileage = last_motorcycle_application.last_mileage
        return self.last_mileage

    def get_reason(self):
        return self.approved_reason if self.status == "active" or self.status == "returned" else self.denied_reason
