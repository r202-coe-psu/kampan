import datetime

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import Form, fields, validators, widgets
from wtforms import SelectField, SelectMultipleField

from kampan import models
from kampan.web.forms import accounts


PICKUP_TIME_FORMAT = "%H:%M"


class CommonReservationForm(FlaskForm):
    """ฟิลด์ที่ใช้ร่วมกันทุกประเภทใบขอ: ผู้ขอ วันเวลาไป-กลับ และที่ให้รถไปจอดรับ"""

    requester_unit = fields.StringField(
        "คณะ/หน่วยงาน",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    phone = fields.StringField(
        "เบอร์โทรศัพท์ผู้ขอใช้รถ",
        validators=[validators.DataRequired(), validators.Length(max=32)],
    )
    departure_date = fields.DateField(
        "วันออกเดินทาง", validators=[validators.InputRequired()]
    )
    departure_time = fields.TimeField(
        "เวลาออกเดินทาง", validators=[validators.InputRequired()]
    )
    return_date = fields.DateField(
        "วันกลับถึงมหาวิทยาลัย", validators=[validators.InputRequired()]
    )
    return_time = fields.TimeField(
        "เวลากลับถึงมหาวิทยาลัย", validators=[validators.InputRequired()]
    )
    pickup_place = fields.StringField(
        "ให้รถไปจอดรับที่",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    pickup_time = fields.TimeField(
        "เวลารับ", validators=[validators.InputRequired()]
    )
    confirm_urgent = fields.BooleanField("ยืนยันยื่นคำขอแบบเร่งด่วน")

    def reservation_fields(self):
        """ฟิลด์ร่วมของ CarReservation ที่ได้จากฟอร์ม (ประเภทย่อยเติมของตัวเองต่อ)"""
        return {
            # ฟอร์มที่ตัด requester_unit ออก (เช่น สวัสดิการใช้สังกัด) ตั้งค่านี้เองต่อจากนี้
            "requester_unit": self.requester_unit.data if self.requester_unit else "",
            "phone": self.phone.data,
            "pickup_place": self.pickup_place.data,
            "pickup_time": self.pickup_time.data.strftime(PICKUP_TIME_FORMAT),
        }

    def build_details(self):
        """embedded document ของฟิลด์เฉพาะประเภท (None ถ้าประเภทนั้นไม่มี)"""
        return None

    def attach_files(self, reservation):
        """เก็บไฟล์แนบของฟอร์ม (ถ้ามี) ลงคำขอก่อนบันทึก"""

    # ฟิลด์ที่ตอนแก้ไขไม่ต้องกรอกใหม่ถ้าไม่ต้องการเปลี่ยน (เช่น ไฟล์แนบเดิม)
    def allow_existing_attachments(self):
        pass

    def prefill(self, reservation):
        """ตั้งค่าเริ่มต้นของฟอร์มจากคำขอเดิม (หน้าแก้ไข) โดยดึงจากฟิลด์ร่วมก่อน แล้วจาก details"""
        details = reservation.details
        for name, field in self._fields.items():
            if name in ("csrf_token", "confirm_urgent", "project_file", "passengers"):
                continue
            for source in (reservation, details):
                if source is not None and hasattr(source, name):
                    field.data = getattr(source, name)
                    break
        self.departure_date.data = reservation.departure_datetime.date()
        self.departure_time.data = reservation.departure_datetime.time()
        self.return_date.data = reservation.return_datetime.date()
        self.return_time.data = reservation.return_datetime.time()
        self.pickup_time.data = _parse_hhmm(reservation.pickup_time)


def _parse_hhmm(value):
    if not value:
        return None
    return datetime.datetime.strptime(value, PICKUP_TIME_FORMAT).time()


class DomesticReservationForm(CommonReservationForm):
    """ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ"""

    location = fields.StringField(
        "สถานที่ปฏิบัติงาน",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    request_reason = fields.StringField(
        "เรื่อง",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    passenger_number = fields.IntegerField(
        "จำนวนผู้โดยสาร",
        validators=[validators.InputRequired(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(),
    )

    vehicle_kind = fields.SelectField(
        "ประเภทรถ",
        choices=models.car_reservations.VEHICLE_KINDS,
        validators=[validators.DataRequired()],
    )
    vehicle_count = fields.IntegerField(
        "จำนวนรถ (คัน)",
        validators=[validators.InputRequired(), validators.NumberRange(min=1)],
        widget=widgets.NumberInput(),
    )
    district = fields.StringField(
        "อำเภอ", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    province = fields.StringField(
        "จังหวัด", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    in_office_of_president = fields.BooleanField("หน่วยงานในสำนักงานอธิการบดี")
    cost_responsibilities = fields.SelectMultipleField(
        "ยินดีรับผิดชอบ",
        choices=models.car_reservations.DOMESTIC_COST_RESPONSIBILITIES,
        option_widget=widgets.CheckboxInput(),
        widget=widgets.ListWidget(prefix_label=False),
    )
    province_scope = fields.SelectField(
        "พื้นที่เดินทาง",
        choices=models.car_reservations.PROVINCE_SCOPES,
        validators=[validators.DataRequired()],
    )

    def reservation_fields(self):
        return {
            **super().reservation_fields(),
            "location": self.location.data,
            "request_reason": self.request_reason.data,
            "passenger_number": self.passenger_number.data,
            "province_scope": self.province_scope.data,
        }

    def build_details(self):
        return models.car_reservations.DomesticDetails(
            vehicle_kind=self.vehicle_kind.data,
            vehicle_count=self.vehicle_count.data,
            district=self.district.data,
            province=self.province.data,
            in_office_of_president=self.in_office_of_president.data,
            cost_responsibilities=(
                self.cost_responsibilities.data
                if self.in_office_of_president.data
                else []
            ),
        )


class PassengerRowForm(Form):
    """หนึ่งแถวของรายชื่อผู้โดยสารสนามบิน (แถวว่างทั้งแถวคือไม่ใช้)"""

    name = fields.StringField("ชื่อผู้โดยสาร", validators=[validators.Length(max=256)])
    phone = fields.StringField("โทร", validators=[validators.Length(max=32)])


class AirportReservationForm(CommonReservationForm):
    """ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่"""

    AIRPORT = "สนามบินหาดใหญ่"

    transfer = fields.RadioField(
        "ต้องการให้รถไป",
        choices=models.car_reservations.AIRPORT_TRANSFERS,
        validators=[validators.DataRequired()],
    )
    flight_number = fields.StringField(
        "เที่ยวบินที่",
        validators=[validators.DataRequired(), validators.Length(max=32)],
    )
    flight_date = fields.DateField("วันที่", validators=[validators.InputRequired()])
    # ชื่อฟอร์มต่างจากโมเดลเพื่อไม่ชนกับ departure_time (เวลาออกเดินทางของรถ) ในฟิลด์ร่วม
    flight_arrival_time = fields.TimeField(
        "เครื่องบินถึงสนามบิน เวลา", validators=[validators.Optional()]
    )
    flight_departure_time = fields.TimeField(
        "เครื่องบินออกจากสนามบิน เวลา", validators=[validators.Optional()]
    )
    passengers = fields.FieldList(
        fields.FormField(PassengerRowForm),
        min_entries=models.car_reservations.AIRPORT_MAX_PASSENGERS,
        max_entries=models.car_reservations.AIRPORT_MAX_PASSENGERS,
    )
    requester_position = fields.StringField(
        "ตำแหน่งผู้ขอใช้รถ",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    in_office_of_president = fields.BooleanField("หน่วยงานในสำนักงานอธิการบดี")
    cost_responsibilities = fields.SelectMultipleField(
        "ยินดีรับผิดชอบ",
        choices=models.car_reservations.AIRPORT_COST_RESPONSIBILITIES,
        option_widget=widgets.CheckboxInput(),
        widget=widgets.ListWidget(prefix_label=False),
    )
    eligibility_confirmed = fields.BooleanField(
        "ข้าพเจ้าเป็นผู้บริหารหรือบุคลากรในสำนักงานอธิการบดี",
        validators=[validators.DataRequired("กรุณายืนยันสิทธิ์การขอใช้รถ")],
    )

    def prefill(self, reservation):
        super().prefill(reservation)
        details = reservation.details
        self.flight_arrival_time.data = _parse_hhmm(details.arrival_time)
        self.flight_departure_time.data = _parse_hhmm(details.departure_time)
        self.passengers.process(
            None,
            [{"name": row.name, "phone": row.phone} for row in details.passengers],
        )
        self.eligibility_confirmed.data = True

    def validate_passengers(self, field):
        if not self.filled_passengers():
            raise validators.ValidationError("ต้องระบุผู้โดยสารอย่างน้อย 1 คน")
        for row in self.filled_passengers():
            if not (row.name.data or "").strip() or not (row.phone.data or "").strip():
                raise validators.ValidationError(
                    "ผู้โดยสารแต่ละคนต้องระบุทั้งชื่อและเบอร์โทร"
                )

    def filled_passengers(self):
        return [
            row.form
            for row in self.passengers
            if (row.form.name.data or "").strip() or (row.form.phone.data or "").strip()
        ]

    def reservation_fields(self):
        transfer_label = dict(models.car_reservations.AIRPORT_TRANSFERS)[
            self.transfer.data
        ]
        return {
            **super().reservation_fields(),
            "location": self.AIRPORT,
            "request_reason": f"{transfer_label}ที่{self.AIRPORT}",
            "passenger_number": len(self.filled_passengers()),
        }

    def build_details(self):
        def hhmm(field):
            return field.data.strftime(PICKUP_TIME_FORMAT) if field.data else ""

        return models.car_reservations.AirportDetails(
            transfer=self.transfer.data,
            flight_number=self.flight_number.data,
            flight_date=self.flight_date.data,
            arrival_time=hhmm(self.flight_arrival_time),
            departure_time=hhmm(self.flight_departure_time),
            passengers=[
                models.car_reservations.AirportPassenger(
                    name=(row.name.data or "").strip(), phone=(row.phone.data or "").strip()
                )
                for row in self.filled_passengers()
            ],
            requester_position=self.requester_position.data,
            in_office_of_president=self.in_office_of_president.data,
            cost_responsibilities=(
                self.cost_responsibilities.data
                if self.in_office_of_president.data
                else []
            ),
        )


class WelfareReservationForm(CommonReservationForm):
    """ใบขอใช้รถประเภทสวัสดิการบุคลากร"""

    requester_unit = None  # ใช้สังกัด (affiliation) แทน

    employee_type = fields.RadioField(
        "ข้าพเจ้าเป็น",
        choices=models.car_reservations.WELFARE_EMPLOYEE_TYPES,
        validators=[validators.DataRequired()],
    )
    affiliation = fields.StringField(
        "สังกัด", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    vehicle_kind = fields.RadioField(
        "ขอใช้รถ",
        choices=models.car_reservations.WELFARE_VEHICLE_KINDS,
        validators=[validators.DataRequired()],
    )
    event_type = fields.RadioField(
        "เนื่องในงาน",
        choices=models.car_reservations.WELFARE_EVENT_TYPES,
        validators=[validators.DataRequired()],
    )
    host_name = fields.StringField(
        "ของ", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    house = fields.StringField(
        "สถานที่ไปบ้าน",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    subdistrict = fields.StringField(
        "ตำบล", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    district = fields.StringField(
        "อำเภอ", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    province = fields.StringField(
        "จังหวัด", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    direct_relative_confirmed = fields.BooleanField(
        "ขอใช้สำหรับตนเองหรือญาติสายตรงเท่านั้น",
        validators=[
            validators.DataRequired(
                "กรุณายืนยันว่าขอใช้สำหรับตนเองหรือญาติสายตรงเท่านั้น"
            )
        ],
    )

    def prefill(self, reservation):
        super().prefill(reservation)
        self.direct_relative_confirmed.data = True

    def reservation_fields(self):
        return {
            **super().reservation_fields(),
            "requester_unit": self.affiliation.data,
            "location": (
                f"บ้านเลขที่ {self.house.data} ต.{self.subdistrict.data} "
                f"อ.{self.district.data} จ.{self.province.data}"
            ),
            "request_reason": f"{self.event_type.data} ของ {self.host_name.data}",
        }

    def build_details(self):
        return models.car_reservations.WelfareDetails(
            employee_type=self.employee_type.data,
            affiliation=self.affiliation.data,
            vehicle_kind=self.vehicle_kind.data,
            event_type=self.event_type.data,
            host_name=self.host_name.data,
            house=self.house.data,
            subdistrict=self.subdistrict.data,
            district=self.district.data,
            province=self.province.data,
        )


MAX_PROJECT_FILE_BYTES = 10 * 1024 * 1024
PROJECT_FILE_EXTENSIONS = ["pdf", "doc", "docx", "jpg", "jpeg", "png"]


def validate_project_file_size(form, field):
    upload = field.data
    if not upload:
        return
    upload.stream.seek(0, 2)
    size = upload.stream.tell()
    upload.stream.seek(0)
    if size > MAX_PROJECT_FILE_BYTES:
        raise validators.ValidationError("ไฟล์เอกสารโครงการต้องมีขนาดไม่เกิน 10 MB")


class AbroadReservationForm(CommonReservationForm):
    """บันทึกข้อความขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ"""

    section = fields.StringField(
        "ส่วนงาน", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    document_number = fields.StringField(
        "ที่", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    vehicle_kind = fields.SelectField(
        "ประเภทรถ",
        choices=models.car_reservations.VEHICLE_KINDS,
        validators=[validators.DataRequired()],
    )
    vehicle_count = fields.IntegerField(
        "จำนวนรถ (คัน)",
        validators=[validators.InputRequired(), validators.NumberRange(min=1)],
        widget=widgets.NumberInput(),
    )
    passenger_number = fields.IntegerField(
        "จำนวนผู้โดยสาร",
        validators=[validators.InputRequired(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(),
    )
    city_state = fields.StringField(
        "เมือง/รัฐ", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    country = fields.StringField(
        "ประเทศ", validators=[validators.DataRequired(), validators.Length(max=256)]
    )
    request_reason = fields.StringField(
        "เรื่อง",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    coordinator_name = fields.StringField(
        "ผู้ประสานงาน",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    coordinator_phone = fields.StringField(
        "โทรผู้ประสานงาน",
        validators=[validators.DataRequired(), validators.Length(max=32)],
    )
    requester_position = fields.StringField(
        "ตำแหน่งผู้ขอใช้รถ",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    project_file = FileField(
        "เอกสารโครงการ",
        validators=[
            FileRequired("กรุณาแนบเอกสารโครงการ"),
            FileAllowed(
                PROJECT_FILE_EXTENSIONS,
                "อนุญาตเฉพาะไฟล์ PDF, DOC, DOCX, JPG หรือ PNG",
            ),
            validate_project_file_size,
        ],
    )

    def reservation_fields(self):
        return {
            **super().reservation_fields(),
            "location": f"{self.city_state.data} {self.country.data}",
            "request_reason": self.request_reason.data,
            "passenger_number": self.passenger_number.data,
        }

    def build_details(self):
        return models.car_reservations.AbroadDetails(
            section=self.section.data,
            document_number=self.document_number.data,
            vehicle_kind=self.vehicle_kind.data,
            vehicle_count=self.vehicle_count.data,
            city_state=self.city_state.data,
            country=self.country.data,
            coordinator_name=self.coordinator_name.data,
            coordinator_phone=self.coordinator_phone.data,
            requester_position=self.requester_position.data,
        )

    def allow_existing_attachments(self):
        self.project_file.validators = [
            check
            for check in self.project_file.validators
            if not isinstance(check, FileRequired)
        ]

    def attach_files(self, reservation):
        upload = self.project_file.data
        if not upload:
            return
        if reservation.project_file:
            reservation.project_file.replace(
                upload, filename=upload.filename, content_type=upload.content_type
            )
        else:
            reservation.project_file.put(
                upload, filename=upload.filename, content_type=upload.content_type
            )


FORM_BY_REQUEST_TYPE = {
    "abroad": AbroadReservationForm,
    "welfare": WelfareReservationForm,
    "domestic": DomesticReservationForm,
    "airport": AirportReservationForm,
}


def reservation_form_for(request_type):
    return FORM_BY_REQUEST_TYPE[request_type]()


class ApprovalDecisionForm(FlaskForm):
    comment = fields.StringField(
        "ความเห็น", validators=[validators.Optional(), validators.Length(max=516)]
    )


class DispatchDecisionForm(ApprovalDecisionForm):
    """ขั้นผู้จัดรถ: อนุมัติพร้อมระบุรถและพนักงานขับรถ

    choices ตั้งจากรถ/พนักงานขับรถของ org ตอนสร้างหน้า ส่วนการตรวจสิทธิ์และเวลาชนกัน
    อยู่ที่ engine จึงปิดการตรวจ choice ของ wtforms
    """

    car = fields.SelectField("รถ", choices=[], validate_choice=False)
    driver = fields.SelectField("พนักงานขับรถ", choices=[], validate_choice=False)
    extra_travelers = fields.StringField(
        "ขออนุมัติให้ ... เดินทางไปด้วย",
        validators=[validators.Optional(), validators.Length(max=516)],
    )


def validate_optional_picture(form, field):
    """รูปรถไม่บังคับ แต่ถ้าแนบมาต้องผ่านกฎเดียวกับรูปโปรไฟล์ (JPEG/PNG จริง ไม่เกิน 2 MB)"""
    if field.data:
        accounts.validate_picture_content(form, field)


class CarForm(FlaskForm):
    """ฟอร์มเพิ่ม/แก้ไขรถของระบบจองรถ (ที่นั่งบังคับกรอกในฟอร์มนี้ แต่เป็น optional ที่โมเดล
    เพื่อให้รถของระบบยืมรถ DIIS ยังใช้งานได้)"""

    license_plate = fields.StringField(
        "ป้ายทะเบียนรถ",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    vehicle_type = fields.SelectField(
        "ประเภทรถ",
        choices=models.vehicles.VEHICLE_TYPES,
        validators=[validators.DataRequired()],
    )
    seat_count = fields.IntegerField(
        "จำนวนที่นั่ง",
        validators=[validators.InputRequired(), validators.NumberRange(min=1)],
        widget=widgets.NumberInput(),
    )
    description = fields.TextAreaField(
        "รายละเอียด/ลักษณะ", validators=[validators.Optional()]
    )
    status = fields.SelectField(
        "สถานะ",
        choices=models.vehicles.VEHICLE_STATUS,
        default="active",
        validators=[validators.DataRequired()],
    )
    upload_image = FileField(
        "รูปภาพรถ",
        validators=[
            FileAllowed(["jpg", "jpeg", "png"], "อนุญาตเฉพาะไฟล์ภาพ JPEG หรือ PNG"),
            validate_optional_picture,
        ],
    )


class DenyDecisionForm(FlaskForm):
    comment = fields.TextAreaField(
        "เหตุผลที่ไม่อนุมัติ",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )


class CancelRequestForm(FlaskForm):
    reason = fields.TextAreaField(
        "เหตุผลที่ยกเลิก (ถ้ามี)",
        validators=[validators.Optional(), validators.Length(max=516)],
    )


class TripCloseForm(FlaskForm):
    """พนักงานขับรถปิดงาน: เลข กม. ออก/กลับ น้ำมัน กรณีค่าใช้จ่าย และเป็นเงิน (ท้ายใบขอใช้รถ)"""

    mileage_out = fields.IntegerField(
        "เลข กม. ออก",
        validators=[validators.InputRequired(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(),
    )
    mileage_in = fields.IntegerField(
        "เลข กม. กลับ",
        validators=[validators.InputRequired(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(),
    )
    fuel_liters = fields.DecimalField(
        "น้ำมัน (ลิตร)",
        places=2,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(step="0.01"),
    )
    expense_case = fields.SelectField(
        "กรณีค่าใช้จ่าย",
        choices=models.car_reservations.EXPENSE_CASES,
        validators=[validators.DataRequired()],
    )
    cost_baht = fields.DecimalField(
        "เป็นเงิน (บาท)",
        places=2,
        validators=[validators.Optional(), validators.NumberRange(min=0)],
        widget=widgets.NumberInput(step="0.01"),
    )
