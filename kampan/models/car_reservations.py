import datetime

import mongoengine as me

RESERVATION_TYPES = [
    ("domestic", "ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ"),
    ("airport", "ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่"),
    ("welfare", "ใบขอใช้รถประเภทสวัสดิการบุคลากร"),
    ("abroad", "ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ"),
]

PROVINCE_SCOPES = [
    ("in_province", "ภายในจังหวัด"),
    ("out_of_province", "ต่างจังหวัด"),
]

RESERVATION_STATUS = [
    ("pending", "รออนุมัติ"),
    ("active", "อนุมัติแล้ว"),
    ("completed", "เสร็จสิ้น"),
    ("denied", "ไม่อนุมัติ"),
    ("cancel_requested", "ขอยกเลิก"),
    ("cancelled", "ยกเลิก"),
]

# ประเภทรถที่ผู้ขอเลือกได้ในใบขอ (ตามแบบฟอร์มจริง)
VEHICLE_KINDS = ["บัส", "ตู้", "เก๋ง", "มินิบัส"]

# หน่วยงานใน สนอ. เลือกรับผิดชอบค่าใช้จ่าย (ตารางท้ายใบ ใช้เฉพาะหน่วยงานในสำนักงานอธิการบดี)
COST_FUEL = "ค่าน้ำมันเชื้อเพลิง"
COST_ALLOWANCE = "เบี้ยเลี้ยง"
COST_DRIVER_LODGING = "ค่าที่พักของพนักงานขับรถ"
COST_NONE = "ไม่รับผิดชอบ"
DOMESTIC_COST_RESPONSIBILITIES = [
    COST_FUEL,
    COST_ALLOWANCE,
    COST_DRIVER_LODGING,
    COST_NONE,
]

AIRPORT_TRANSFERS = [("pickup", "รับ"), ("dropoff", "ส่ง")]
AIRPORT_COST_RESPONSIBILITIES = [COST_FUEL, COST_ALLOWANCE, COST_NONE]
AIRPORT_MAX_PASSENGERS = 5

WELFARE_EMPLOYEE_TYPES = ["พนักงานมหาวิทยาลัย", "ลูกจ้างประจำ", "พนักงานเงินรายได้"]
WELFARE_VEHICLE_KINDS = ["บัส", "ตู้"]
WELFARE_EVENT_TYPES = ["อุปสมบท", "มงคลสมรส", "ฌาปนกิจศพ"]

# กรณีค่าใช้จ่ายของทริปที่ พขร. เลือกตอนปิดงาน
EXPENSE_CASES = [
    ("requester_unit_pays", "หน่วยงานผู้ขอใช้รถรับผิดชอบค่าใช้จ่าย"),
    ("fleet_card", "เติมฟลีตการ์ดน้ำมัน"),
]

STEP_DECISIONS = [("approved", "อนุมัติ"), ("denied", "ไม่อนุมัติ")]

AUDIT_ACTIONS = [
    ("submitted", "ยื่นคำขอ"),
    ("edited", "แก้ไขคำขอ"),
    ("approved", "อนุมัติ"),
    ("denied", "ไม่อนุมัติ"),
    ("cancel_requested", "ขอยกเลิก"),
    ("cancel_confirmed", "รับทราบการยกเลิก"),
    ("cancelled", "ยกเลิก"),
    ("completed", "ปิดงาน"),
]


class StepApproval(me.EmbeddedDocument):
    step_key = me.StringField(required=True)
    label = me.StringField()
    decision = me.StringField(choices=STEP_DECISIONS)
    decided_by = me.ReferenceField("User", dbref=True)
    decided_at = me.DateTimeField()
    comment = me.StringField(default="")


class ReservationAuditLog(me.EmbeddedDocument):
    """ประวัติของคำขอ: ใคร ทำอะไร ขั้นไหน เมื่อไร"""

    action = me.StringField(choices=AUDIT_ACTIONS, required=True)
    actor = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    step_key = me.StringField(default="")
    step_label = me.StringField(default="")
    comment = me.StringField(default="")

    def get_action_display(self):
        return dict(AUDIT_ACTIONS).get(self.action, self.action)


class DomesticDetails(me.EmbeddedDocument):
    """ฟิลด์เฉพาะของใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ (`domestic`)

    เรื่อง (subject) เก็บที่ `CarReservation.request_reason` และสถานที่ปฏิบัติงานเก็บที่
    `CarReservation.location` ซึ่งเป็นฟิลด์ร่วมของคำขอ
    """

    vehicle_kind = me.StringField(choices=VEHICLE_KINDS, required=True)
    vehicle_count = me.IntField(min_value=1, required=True)
    district = me.StringField(required=True, max_length=256)  # อำเภอ
    province = me.StringField(required=True, max_length=256)  # จังหวัด
    # ผู้ขอเป็นหน่วยงานใน สนอ. หรือไม่ เก็บ cost_responsibilities เฉพาะเมื่อเป็น True
    in_office_of_president = me.BooleanField(default=False)
    cost_responsibilities = me.ListField(
        me.StringField(choices=DOMESTIC_COST_RESPONSIBILITIES)
    )


class AirportPassenger(me.EmbeddedDocument):
    name = me.StringField(required=True, max_length=256)
    phone = me.StringField(required=True, max_length=32)


class AirportDetails(me.EmbeddedDocument):
    """ฟิลด์เฉพาะของใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่ (`airport`)

    สถานที่ (`CarReservation.location`) คือสนามบินหาดใหญ่ และ `CarReservation.passenger_number`
    นับจาก `passengers`
    """

    transfer = me.StringField(choices=AIRPORT_TRANSFERS, required=True)
    flight_number = me.StringField(required=True, max_length=32)
    flight_date = me.DateField(required=True)
    arrival_time = me.StringField(default="")  # เวลาเครื่องบินถึง "HH:MM"
    departure_time = me.StringField(default="")  # เวลาเครื่องบินออก "HH:MM"
    passengers = me.ListField(
        me.EmbeddedDocumentField(AirportPassenger), max_length=AIRPORT_MAX_PASSENGERS
    )
    requester_position = me.StringField(required=True, max_length=256)
    in_office_of_president = me.BooleanField(default=False)
    cost_responsibilities = me.ListField(
        me.StringField(choices=AIRPORT_COST_RESPONSIBILITIES)
    )

    def get_transfer_display(self):
        return dict(AIRPORT_TRANSFERS).get(self.transfer, self.transfer)


class WelfareDetails(me.EmbeddedDocument):
    """ฟิลด์เฉพาะของใบขอใช้รถประเภทสวัสดิการบุคลากร (`welfare`)

    `CarReservation.requester_unit` คือสังกัด (`affiliation`) และ `CarReservation.location`
    ประกอบจากที่อยู่บ้านเจ้าภาพ แบบฟอร์มจริงไม่มีช่องจำนวนผู้โดยสารและจำนวนคัน
    """

    employee_type = me.StringField(choices=WELFARE_EMPLOYEE_TYPES, required=True)
    affiliation = me.StringField(required=True, max_length=256)  # สังกัด
    vehicle_kind = me.StringField(choices=WELFARE_VEHICLE_KINDS, required=True)
    event_type = me.StringField(choices=WELFARE_EVENT_TYPES, required=True)
    host_name = me.StringField(required=True, max_length=256)  # งานของ (เจ้าภาพ)
    house = me.StringField(required=True, max_length=256)  # สถานที่ไปบ้าน
    subdistrict = me.StringField(required=True, max_length=256)  # ตำบล
    district = me.StringField(required=True, max_length=256)  # อำเภอ
    province = me.StringField(required=True, max_length=256)  # จังหวัด


class AbroadDetails(me.EmbeddedDocument):
    """ฟิลด์เฉพาะของบันทึกข้อความขอใช้รถยนต์ไปปฏิบัติงานต่างประเทศ (`abroad`)

    เรื่อง (subject) เก็บที่ `CarReservation.request_reason`, สถานที่ (`CarReservation.location`)
    ประกอบจากเมือง/ประเทศ และเอกสารโครงการแนบที่ `CarReservation.project_file`
    """

    section = me.StringField(required=True, max_length=256)  # ส่วนงาน
    document_number = me.StringField(required=True, max_length=256)  # ที่ (เลขหนังสือ)
    vehicle_kind = me.StringField(choices=VEHICLE_KINDS, required=True)
    vehicle_count = me.IntField(min_value=1, required=True)
    city_state = me.StringField(required=True, max_length=256)  # เมือง/รัฐ
    country = me.StringField(required=True, max_length=256)  # ประเทศ
    coordinator_name = me.StringField(required=True, max_length=256)
    coordinator_phone = me.StringField(required=True, max_length=32)
    requester_position = me.StringField(required=True, max_length=256)


class CarReservation(me.Document):
    meta = {"collection": "car_reservations"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)

    creator = me.ReferenceField("User", dbref=True)
    updater = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    requester_unit = me.StringField(default="", max_length=256)  # คณะ/หน่วยงานของผู้ขอ
    phone = me.StringField(default="", max_length=32)
    # ผู้ติดต่อรับแจ้งสถานะ: อีเมลนี้ได้รับทุกอีเมลที่ส่งถึงผู้ขอด้วย
    contact_name = me.StringField(default="", max_length=256)
    contact_email = me.StringField(default="", max_length=256)
    location = me.StringField(default="", max_length=516, required=True)
    request_reason = me.StringField(default="", max_length=516, required=True)
    departure_datetime = me.DateTimeField(required=True, default=datetime.datetime.now)
    return_datetime = me.DateTimeField(default=datetime.datetime.now)
    passenger_number = me.IntField(min_value=0, required=True, default=0)
    pickup_place = me.StringField(default="", max_length=516)  # สถานที่ให้รถไปจอดรับ
    pickup_time = me.StringField(default="")  # เวลารับ รูปแบบ "HH:MM"

    request_type = me.StringField(choices=RESERVATION_TYPES, required=True)
    province_scope = me.StringField(choices=PROVINCE_SCOPES)

    # ฟิลด์เฉพาะประเภทใบขอ: embedded document หนึ่งชนิดต่อ request_type
    details = me.GenericEmbeddedDocumentField(
        choices=[DomesticDetails, AirportDetails, WelfareDetails, AbroadDetails]
    )
    # เอกสารโครงการที่แนบกับใบขอไปต่างประเทศ (ประเภทอื่นไม่มี)
    project_file = me.FileField(collection_name="car_reservation_project_files")

    is_urgent = me.BooleanField(default=False)  # ยื่นล่วงหน้าน้อยกว่าที่กำหนดและผู้ขอยืนยันแล้ว

    status = me.StringField(default="pending", choices=RESERVATION_STATUS)
    route_snapshot = me.ListField(me.StringField())  # เส้นทางอนุมัติที่ตรึงไว้ตอนยื่น
    current_step = me.IntField(default=0)
    step_approvals = me.ListField(me.EmbeddedDocumentField(StepApproval))
    audit_logs = me.ListField(me.EmbeddedDocumentField(ReservationAuditLog))

    # ผู้จัดรถขออนุมัติให้ ... เดินทางไปด้วย (เฉพาะ domestic และ abroad)
    extra_travelers = me.StringField(default="", max_length=516)

    car = me.ReferenceField("Car", dbref=True)
    driver = me.ReferenceField("User", dbref=True)
    last_mileage = me.IntField(min_value=0)
    last_mileage_before = me.IntField(min_value=0)

    # รายงานท้ายใบที่ พขร. กรอกตอนปิดงาน (last_mileage_before = เลข กม. ออก, last_mileage = เลข กม. กลับ)
    fuel_liters = me.DecimalField(min_value=0, precision=2)
    expense_case = me.StringField(choices=EXPENSE_CASES)
    cost_baht = me.DecimalField(min_value=0, max_value=1e12, precision=2)
    completed_at = me.DateTimeField()

    @property
    def distance_km(self):
        """ระยะทางรวมของทริป (เลข กม. กลับ - เลข กม. ออก) ยังไม่ปิดงานคือ None"""
        if self.last_mileage is None or self.last_mileage_before is None:
            return None
        return self.last_mileage - self.last_mileage_before
