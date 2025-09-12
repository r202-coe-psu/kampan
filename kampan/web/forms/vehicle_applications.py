from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed
from flask_mongoengine.wtf import model_form
from wtforms import fields, validators, widgets
from kampan import models


BaseCarApplicationForm = model_form(
    models.vehicle_applications.CarApplication,
    FlaskForm,
    exclude=[
        "organization",
        "division",
        "created_date",
        "updated_date",
        "creator",
        "updater",
        "status",
        "approved_reason",
        "denied_reason",
        "departure_datetime",
        "return_datetime",
        "flight_datetime",
        "flight_return_datetime",
        "division",
    ],
    field_args={
        "request_reason": {"label": "เหตุผลที่ต้องการใช้"},
        # "approved_reason": {"label": "เหตุผลที่อนุมัติ"},
        # "denied_reason": {"label": "เหตุผลที่ไม่อนุมัติ"},
        "location": {"label": "สถานที่ต้องการจะไป"},
        # "using_type": {"label": "ประเภทการใช้รถ"},
        # "travel_type": {"label": "ประเภทการเดินทาง"},
        "passenger_number": {"label": "จำนวนผู้โดยสาร"},
        "flight_number": {"label": "หมายเลขเที่ยวบินไป"},
        "flight_return_number": {"label": "หมายเลขเที่ยวบินกลับ"},
    },
)


class CarApplicationForm(BaseCarApplicationForm):
    car = fields.SelectField("รถยนต์", validate_choice=True)
    using_type = fields.RadioField(
        "ประเภทการใช้รถ",
        choices=models.vehicle_applications.USING_TYPE,
        default=models.vehicle_applications.USING_TYPE[0][0],
    )
    travel_type = fields.RadioField(
        "ประเภทการเดินทาง",
        choices=models.vehicle_applications.TRAVEL_TYPE,
        default=models.vehicle_applications.TRAVEL_TYPE[0][0],
    )
    departure_date = fields.DateField(
        "วันเวลาออกเดินทาง",
        validators=[validators.InputRequired()],
    )
    departure_time = fields.TimeField(
        "เวลาออกเดินทาง",
        # format="%I:%M %p",
        validators=[validators.InputRequired()],
    )

    return_date = fields.DateField(
        "วันกลับ",
        validators=[validators.Optional()],
    )
    return_time = fields.TimeField(
        "เวลากลับ",
        # format="%I:%M %p",
        validators=[validators.Optional()],
    )

    flight_return_time = fields.TimeField(
        "เวลาไฟล์ทบินกลับ",
        validators=[validators.Optional()],
    )
    flight_time = fields.TimeField(
        "เวลาไฟล์ทบินไป",
        # format="%I:%M %p",
        validators=[validators.Optional()],
    )


class ReturnCarApplicationForm(FlaskForm):
    last_mileage = fields.IntegerField(
        "เลขไมล์หลังกลับ",
        validators=[validators.InputRequired()],
        widget=widgets.NumberInput(),
    )
    return_date = fields.DateField(
        "วันกลับ",
        validators=[validators.InputRequired()],
    )
    return_time = fields.TimeField(
        "เวลากลับ",
        # format="%I:%M %p",
        validators=[validators.InputRequired()],
    )


class DateRangeForm(FlaskForm):
    start_date = fields.DateField(
        "จากวันที่",
        validators=[validators.Optional()],
        render_kw={"placeholder": "เลือกวันที่"},
    )
    end_date = fields.DateField(
        "ถึงวันที่",
        validators=[validators.Optional()],
        render_kw={"placeholder": "เลือกวันที่"},
    )


BaseMotorcycleApplicationForm = model_form(
    models.vehicle_applications.MotorcycleApplication,
    FlaskForm,
    exclude=[
        "organization",
        "division",
        "created_date",
        "updated_date",
        "creator",
        "updater",
        "status",
        "approved_reason",
        "denied_reason",
        "departure_datetime",
        "return_datetime",
        "last_mileage",
    ],
    field_args={
        "request_reason": {"label": "เหตุผลที่ต้องการใช้"},
        # "approved_reason": {"label": "เหตุผลที่อนุมัติ"},
        # "denied_reason": {"label": "เหตุผลที่ไม่อนุมัติ"},
        "location": {"label": "สถานที่ต้องการจะไป"},
        # "last_mileage": {"label": "เลขไมล์สุดท้าย"},
    },
)


class MotorcycleApplicationForm(BaseMotorcycleApplicationForm):
    motorcycle = fields.SelectField("รถมอเตอร์ไซค์", validate_choice=True)
    departure_date = fields.DateField(
        "วันเวลาออกเดินทาง",
        validators=[validators.InputRequired()],
    )
    departure_time = fields.TimeField(
        "เวลาออกเดินทาง",
        # format="%I:%M %p",
        validators=[validators.InputRequired()],
    )


BaseReturnMotorcycleApplicationForm = model_form(
    models.vehicle_applications.MotorcycleApplication,
    FlaskForm,
    exclude=[
        "organization",
        "division",
        "created_date",
        "updated_date",
        "creator",
        "updater",
        "status",
        "approved_reason",
        "denied_reason",
        "departure_datetime",
        "return_datetime",
        "motorcycle",
        "location",
        "request_reason",
    ],
    field_args={
        # "request_reason": {"label": "เหตุผลที่ต้องการใช้"},
        # "approved_reason": {"label": "เหตุผลที่อนุมัติ"},
        # "denied_reason": {"label": "เหตุผลที่ไม่อนุมัติ"},
        # "location": {"label": "สถานที่ต้องการจะไป"},
        "last_mileage": {"label": "เลขไมล์สุดท้าย"},
    },
)


class ReturnMotorcycleApplicationForm(BaseReturnMotorcycleApplicationForm):

    return_date = fields.DateField(
        "วันกลับ",
        validators=[validators.InputRequired()],
    )
    return_time = fields.TimeField(
        "เวลากลับ",
        # format="%I:%M %p",
        validators=[validators.InputRequired()],
    )
