import datetime
import io

from flask_wtf import FlaskForm
from PIL import Image, UnidentifiedImageError
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import Form, fields, validators, widgets
from wtforms import SelectField, SelectMultipleField

from kampan import models, utils
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
    contact_name = fields.StringField(
        "ชื่อผู้ติดต่อรับแจ้งสถานะ",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    contact_email = fields.StringField(
        "อีเมลผู้ติดต่อรับแจ้งสถานะ",
        validators=[
            validators.DataRequired(),
            validators.Length(max=256),
            validators.Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="รูปแบบอีเมลไม่ถูกต้อง"),
        ],
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
            "contact_name": self.contact_name.data.strip(),
            "contact_email": self.contact_email.data.strip(),
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

    def _tracked_fields(self):
        return [
            (name, field)
            for name, field in self._fields.items()
            if name not in UNTRACKED_FIELDS
        ]

    def change_labels(self):
        """{ชื่อฟิลด์: ป้ายภาษาไทย} ของข้อมูลคำขอที่ลงประวัติเมื่อแก้ไข เรียงตามฟอร์ม"""
        return {name: field.label.text for name, field in self._tracked_fields()}

    def describe(self, reservation):
        """{ชื่อฟิลด์: ข้อความแสดงผลของค่าที่เก็บในคำขอ} ไว้เทียบก่อน-หลังแก้ไข"""
        return {
            name: self._display(field, self._stored_value(reservation, name))
            for name, field in self._tracked_fields()
        }

    @staticmethod
    def _stored_value(reservation, name):
        if name in TRIP_MOMENT_FIELDS:
            moment = getattr(reservation, TRIP_MOMENT_FIELDS[name])
            return moment.date() if name.endswith("date") else moment.time()
        if name == "project_file":
            return reservation.project_file.filename if reservation.project_file else None
        name = DETAIL_ATTRIBUTES.get(name, name)
        for source in (reservation, reservation.details):
            if source is not None and hasattr(source, name):
                return getattr(source, name)
        return None

    @staticmethod
    def _display(field, value):
        choices = {
            (choice[0] if isinstance(choice, tuple) else choice): (
                choice[1] if isinstance(choice, tuple) else choice
            )
            for choice in (getattr(field, "choices", None) or [])
        }
        if isinstance(value, list):
            if choices:
                value = [key for key in choices if key in value]
            parts = [
                f"{item.name} ({item.phone})" if hasattr(item, "phone") else choices.get(item, item)
                for item in value
            ]
            return ", ".join(parts) or NO_VALUE_TEXT
        if isinstance(value, bool):
            return "ใช่" if value else "ไม่ใช่"
        if isinstance(value, datetime.date):
            return value.strftime(DISPLAY_DATE_FORMAT)
        if isinstance(value, datetime.time):
            return value.strftime(PICKUP_TIME_FORMAT)
        if value in (None, ""):
            return NO_VALUE_TEXT
        return str(choices.get(value, value))

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


NO_VALUE_TEXT = "-"
DISPLAY_DATE_FORMAT = "%d/%m/%Y"
# ฟิลด์ฟอร์มที่ไม่ใช่ข้อมูลของคำขอ (ไม่ลงประวัติการแก้ไข)
UNTRACKED_FIELDS = (
    "csrf_token",
    "confirm_urgent",
    "eligibility_confirmed",
    "direct_relative_confirmed",
)
# ฟิลด์ฟอร์มที่ชื่อต่างจากฟิลด์ใน details
DETAIL_ATTRIBUTES = {
    "flight_arrival_time": "arrival_time",
    "flight_departure_time": "departure_time",
}
TRIP_MOMENT_FIELDS = {
    "departure_date": "departure_datetime",
    "departure_time": "departure_datetime",
    "return_date": "return_datetime",
    "return_time": "return_datetime",
}


class DomesticReservationForm(CommonReservationForm):
    """ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ"""

    location = fields.StringField(
        "สถานที่ปฏิบัติงาน",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    request_reason = fields.StringField(
        "วัตถุประสงค์การเดินทาง",
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


class UrgentDomesticReservationForm(DomesticReservationForm):
    """ผู้จัดรถสร้างใบขอในประเทศเร่งด่วน: ฟิลด์เดียวกับใบปกติ + เลือกรถ พขร. และ OT ในฟอร์มเดียว

    choices ของรถ/พขร. ตั้งจาก org ตอนสร้างหน้า ส่วนสิทธิ์และเวลาชนกันตรวจที่ engine
    """

    car = fields.SelectField("รถ", choices=[], validate_choice=False)
    driver = fields.SelectField("พนักงานขับรถ", choices=[], validate_choice=False)
    is_overtime = fields.BooleanField("งานนอกเวลา (OT)")


class InsertJobForm(FlaskForm):
    """ผู้จัดรถเพิ่มงานแทรกให้ พขร. ที่มีงานอยู่แล้วในวันนั้น: งานสั้น ไม่ผ่านการอนุมัติ

    choices ของรถ/พขร. ตั้งจาก org ตอนสร้างหน้า ส่วนสิทธิ์และเวลาชนกันตรวจที่ engine
    """

    driver = fields.SelectField("พนักงานขับรถ", choices=[], validate_choice=False)
    car = fields.SelectField("รถ", choices=[], validate_choice=False)
    departure_date = fields.DateField(
        "วันเริ่มงาน", validators=[validators.InputRequired()]
    )
    departure_time = fields.TimeField(
        "เวลาเริ่มงาน", validators=[validators.InputRequired()]
    )
    return_date = fields.DateField(
        "วันสิ้นสุดงาน", validators=[validators.InputRequired()]
    )
    return_time = fields.TimeField(
        "เวลาสิ้นสุดงาน", validators=[validators.InputRequired()]
    )
    location = fields.StringField(
        "สถานที่",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    request_reason = fields.StringField(
        "เหตุผล",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    insert_scope = fields.SelectField(
        "พื้นที่",
        choices=models.car_reservations.INSERT_SCOPES,
        validators=[validators.DataRequired()],
    )
    contact_name = fields.StringField(
        "ชื่อผู้ติดต่อรับแจ้งสถานะ",
        validators=[validators.DataRequired(), validators.Length(max=256)],
    )
    contact_email = fields.StringField(
        "อีเมลผู้ติดต่อรับแจ้งสถานะ",
        validators=[
            validators.DataRequired(),
            validators.Length(max=256),
            validators.Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="รูปแบบอีเมลไม่ถูกต้อง"),
        ],
    )
    is_overtime = fields.BooleanField("งานนอกเวลา (OT)")


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
        "รายชื่อผู้โดยสาร",
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
        "วัตถุประสงค์การเดินทาง",
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
    # ปุ่มลัดในกล่องรออนุมัติส่งมา: view ยอมรับเฉพาะ URL กล่องรออนุมัติของ org เป๊ะ ๆ
    next = fields.HiddenField()
    # current_step ตอนเปิดหน้า: กดซ้ำหรือถือหลาย role จะไม่อนุมัติขั้นถัดไปที่ยังไม่เคยเห็น
    step = fields.HiddenField()


class QuickApprovalForm(ApprovalDecisionForm):
    """อนุมัติจากกล่องรออนุมัติ (modal): ความเห็นเป็น textarea ชื่อ field เดียวกับ ApprovalDecisionForm"""

    comment = fields.TextAreaField(
        "ความเห็น (ไม่บังคับ)",
        validators=[validators.Optional(), validators.Length(max=516)],
    )


def with_id_suffix(form, suffix):
    """ให้ id ของทุก field ไม่ซ้ำเมื่อวางหลายฟอร์มชนิดเดียวกันในหน้าเดียว (name คงเดิม จึงโพสต์เหมือนเดิม)"""
    for field in form:
        field.id = f"{field.id}-{suffix}"
        field.label.field_id = field.id
    return form


class DispatchDecisionForm(ApprovalDecisionForm):
    """ขั้นผู้จัดรถ: อนุมัติพร้อมระบุรถและพนักงานขับรถ

    choices ตั้งจากรถ/พนักงานขับรถของ org ตอนสร้างหน้า ส่วนการตรวจสิทธิ์และเวลาชนกัน
    อยู่ที่ engine จึงปิดการตรวจ choice ของ wtforms
    """

    car = fields.SelectField("รถ", choices=[], validate_choice=False)
    driver = fields.RadioField("พนักงานขับรถ", choices=[], validate_choice=False)
    extra_travelers = fields.StringField(
        "ขออนุมัติให้ผู้ร่วมเดินทางไปปฏิบัติงานต่างจังหวัด",
        description="ตามช่อง (3) ของใบขอใช้รถ เช่น ชื่อพนักงานขับรถ หรือผู้ช่วย คั่นด้วยจุลภาค",
        validators=[validators.Optional(), validators.Length(max=516)],
    )
    is_overtime = fields.BooleanField("งานนอกเวลา (OT)")


class OvertimeForm(FlaskForm):
    """ผู้จัดรถสลับสถานะงานนอกเวลา (OT) ของคำขอที่ active"""

    is_overtime = fields.BooleanField("งานนอกเวลา (OT)")


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
    brand = fields.StringField(
        "ยี่ห้อ", validators=[validators.Optional(), validators.Length(max=128)]
    )
    car_model = fields.StringField(
        "รุ่น", validators=[validators.Optional(), validators.Length(max=128)]
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


class SettingsForm(FlaskForm):
    """ตั้งค่าของระบบจองรถที่แอดมินองค์กรแก้ได้"""

    car_reservation_contact_phone = fields.StringField(
        "เบอร์โทรศัพท์ติดต่อฝ่ายจองรถ",
        validators=[validators.Optional(), validators.Length(max=32)],
    )
    car_reservation_campus_networks = fields.TextAreaField(
        "ช่วง IP ของมหาวิทยาลัย (หนึ่งช่วงต่อบรรทัด เช่น 10.0.0.0/8)",
        validators=[validators.Optional()],
    )

    def validate_car_reservation_campus_networks(self, field):
        for line in utils.campus_network.split_lines(field.data):
            if utils.campus_network.parse_network(line) is None:
                raise validators.ValidationError(f"ช่วง IP ไม่ถูกต้อง: {line}")


class DriverStatsFilterForm(FlaskForm):
    """ตัวกรอง dashboard ภาระงาน พขร. (GET จึงไม่มี CSRF) ช่วงเวลาเป็น hidden (ค่าที่ไม่รู้จักถูกแทนด้วยค่าเริ่มต้นใน view)

    organization_id ต้องติดไปกับ query ทุกครั้งที่ส่งฟอร์ม; driver choices ตั้งจาก พขร. ของ org ใน view
    """

    class Meta:
        csrf = False

    organization_id = fields.HiddenField()
    period = fields.HiddenField("ช่วงเวลา")
    driver = fields.SelectField(
        "พนักงานขับรถ",
        choices=[],
        render_kw={"onchange": "this.form.submit()"},
    )


class DenyDecisionForm(FlaskForm):
    comment = fields.TextAreaField(
        "เหตุผลที่ไม่อนุมัติ",
        validators=[validators.DataRequired(), validators.Length(max=516)],
    )
    next = fields.HiddenField()


class CancelRequestForm(FlaskForm):
    reason = fields.TextAreaField(
        "เหตุผลที่ยกเลิก (ถ้ามี)",
        validators=[validators.Optional(), validators.Length(max=516)],
    )


class CloseConfirmationForm(FlaskForm):
    """ผู้ขอยืนยันเวลาปิดงานของ พขร.: ถูกต้อง หรือ ไม่ถูกต้อง พร้อมเวลาสิ้นสุดจริง (และหมายเหตุ)"""

    decision = fields.SelectField(
        "คำตอบ",
        choices=[("correct", "ถูกต้อง"), ("incorrect", "ไม่ถูกต้อง")],
        validators=[validators.DataRequired()],
    )
    actual_end_date = fields.DateField(
        "วันสิ้นสุดงานจริง", validators=[validators.Optional()]
    )
    actual_end_time = fields.TimeField(
        "เวลาสิ้นสุดงานจริง", validators=[validators.Optional()]
    )
    note = fields.StringField(
        "หมายเหตุ", validators=[validators.Optional(), validators.Length(max=516)]
    )


MAX_MILEAGE_PHOTO_BYTES = 5 * 1024 * 1024


def validate_mileage_photo(form, field):
    """รูปเลขไมล์ต้องเป็นภาพ JPEG/PNG จริง ไม่เกิน 5 MB"""
    upload = field.data
    if not upload:
        return
    content = upload.read(MAX_MILEAGE_PHOTO_BYTES + 1)
    upload.seek(0)
    if len(content) > MAX_MILEAGE_PHOTO_BYTES:
        raise validators.ValidationError("รูปเลขไมล์ต้องมีขนาดไม่เกิน 5 MB")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError, SyntaxError):
        image_format = None
    if image_format not in ("JPEG", "PNG"):
        raise validators.ValidationError("รูปเลขไมล์ต้องเป็นภาพ JPEG หรือ PNG")


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
    mileage_photo_in = FileField(
        "รูปเลขไมล์ขากลับ",
        validators=[
            FileRequired("กรุณาถ่ายรูปเลขไมล์ขากลับ"),
            validate_mileage_photo,
        ],
    )
