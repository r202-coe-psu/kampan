import datetime

from flask_wtf import FlaskForm
from wtforms import fields, validators

from kampan.models.vehicle_applications import CAR_APPLICATION_STATUS


def _required(message):
    return [validators.DataRequired(message=message)]


class CarFormRequestForm(FlaskForm):
    """ฟิลด์หลักของคำขอใช้รถ (ทุก template มี) ฟิลด์ของ template ต่อท้ายผ่าน build_details_form(base=...)"""

    phone = fields.StringField(
        "เบอร์โทรศัพท์",
        validators=_required("กรุณากรอกเบอร์โทรศัพท์")
        + [validators.Length(max=32, message="เบอร์โทรศัพท์ยาวเกิน 32 ตัวอักษร")],
    )
    location = fields.StringField(
        "สถานที่ที่ต้องการจะไป", validators=_required("กรุณากรอกสถานที่ที่ต้องการจะไป")
    )
    request_reason = fields.TextAreaField(
        "เหตุผลที่ต้องการใช้รถ", validators=_required("กรุณากรอกเหตุผลที่ต้องการใช้รถ")
    )
    passenger_number = fields.IntegerField(
        "จำนวนผู้โดยสาร",
        validators=[
            validators.InputRequired(message="กรุณากรอกจำนวนผู้โดยสาร"),
            validators.NumberRange(min=0, message="จำนวนผู้โดยสารต้องไม่ติดลบ"),
        ],
    )
    departure_date = fields.DateField(
        "วันที่ออกเดินทาง", validators=_required("กรุณาเลือกวันที่ออกเดินทาง")
    )
    departure_time = fields.TimeField(
        "เวลาออกเดินทาง", validators=_required("กรุณาเลือกเวลาออกเดินทาง")
    )
    return_date = fields.DateField("วันที่กลับ", validators=_required("กรุณาเลือกวันที่กลับ"))
    return_time = fields.TimeField("เวลากลับ", validators=_required("กรุณาเลือกเวลากลับ"))

    def departure_datetime(self):
        return datetime.datetime.combine(self.departure_date.data, self.departure_time.data)

    def return_datetime(self):
        return datetime.datetime.combine(self.return_date.data, self.return_time.data)

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        times = (self.departure_date, self.departure_time, self.return_date, self.return_time)
        if all(field.data and not field.errors for field in times):
            if self.return_datetime() <= self.departure_datetime():
                self.return_date.errors.append("วันเวลากลับต้องอยู่หลังวันเวลาออกเดินทาง")
                valid = False
        return valid


class ApproveStepForm(FlaskForm):
    """อนุมัติขั้นปัจจุบัน ใช้ for_step() สร้างเพื่อใส่ตัวเลือกรถ/คนขับของ org และบังคับเลือกรถในขั้นจัดรถ"""

    car = fields.SelectField("รถ", choices=[], default="", validate_choice=True)
    driver = fields.SelectField("พนักงานขับรถ", choices=[], default="", validate_choice=True)
    comment = fields.TextAreaField("ความเห็น (ถ้ามี)")
    next = fields.HiddenField()

    @classmethod
    def for_step(cls, step, cars, drivers, formdata=None, next_page=""):
        form = cls(formdata=formdata, next=next_page)
        if not (step or {}).get("assigns_vehicle"):
            del form.car
            del form.driver
            return form
        form.car.validators = _required("กรุณาเลือกรถ")
        form.car.flags.required = True
        form.car.choices = [("", "เลือกรถ")] + [
            (
                str(car.id),
                f"{car.license_plate} ({car.get_vehicle_type_display()})" if car.vehicle_type else car.license_plate,
                {"data-vehicle-type": car.vehicle_type or ""},
            )
            for car in cars
        ]
        form.driver.choices = [("", "ไม่ระบุ")] + [
            (str(driver.id), driver.get_resources_fullname_th()) for driver in drivers
        ]
        return form


class DenyStepForm(FlaskForm):
    denied_reason = fields.TextAreaField(
        "เหตุผลที่ปฏิเสธ", validators=_required("กรุณาระบุเหตุผลที่ปฏิเสธ")
    )
    next = fields.HiddenField()


SEARCH_STATUSES = [
    (value, label)
    for value, label in CAR_APPLICATION_STATUS
    if value in ("pending", "active", "completed", "denied", "disactive")
]


class CarRequestSearchForm(FlaskForm):
    """ตัวกรองหน้ารายการ (GET) ไม่ต้องใช้ CSRF"""

    class Meta:
        csrf = False

    q = fields.StringField("ค้นหา")
    template_id = fields.SelectField("แบบฟอร์ม", choices=[], validate_choice=False)
    status = fields.SelectField(
        "สถานะ", choices=[("", "ทุกสถานะ")] + SEARCH_STATUSES, validate_choice=False
    )

    @classmethod
    def from_args(cls, args, templates, with_status=True):
        form = cls(formdata=args)
        form.template_id.choices = [("", "ทุกแบบฟอร์ม")] + [(str(t.id), t.name) for t in templates]
        if not with_status:
            del form.status
        return form

    def search_args(self):
        return {
            "q": (self.q.data or "").strip(),
            "template_id": self.template_id.data or "",
            "status": (self.status.data or "") if "status" in self else "",
        }


class CarTaskFilterForm(FlaskForm):
    class Meta:
        csrf = False

    q = fields.StringField("ค้นหา")
    date = fields.DateField("เลือกวันที่", validators=[validators.Optional()])
    sort_by = fields.SelectField(
        "เรียงลำดับตาม",
        choices=[
            ("departure_datetime", "วันเวลาออกเดินทาง"),
            ("return_datetime", "วันเวลากลับ"),
            ("created_date", "วันที่สร้าง"),
        ],
        default="departure_datetime",
    )
    order = fields.SelectField(
        "ลำดับ", choices=[("asc", "เก่าสุดก่อน"), ("desc", "ใหม่สุดก่อน")], default="asc"
    )
