"""ตารางรถ (resource timeline) ของระบบจองรถ: แถว = รถ จัดกลุ่มตามประเภท, คอลัมน์ = วัน, แท่ง = ชุดรถ/พขร. ของคำขอ

ไฟล์นี้เป็น data builder ล้วน (ไม่ผูกกับ request) หน้าตารางรถของผู้จัดรถและตัวเลือกรถในฟอร์มจัดรถใช้ร่วมกัน

- `parse_query(args)` แปลง query string เป็น (start_date, days, TimelineFilters) ค่าที่ผิดรูปแบบถูกแทนด้วยค่าเริ่มต้น
- `build_timeline(organization, start_date, days, filters, now=None)` คืน `Timeline`
- `query_args(start_date, days, filters)` แปลงกลับเป็นพารามิเตอร์ของลิงก์ (เฉพาะค่าที่ไม่ใช่ค่าเริ่มต้น)

ตำแหน่งแท่งคำนวณจากเวลาจริงเทียบกับช่วงที่แสดง [start 00:00, start + days 00:00) แถวหนึ่งเป็น track ต่อเนื่องทุกวัน
ความกว้างขั้นต่ำของแท่งแคบให้ CSS จัดการ แท่งที่เวลาทับกันในแถวเดียวกันถูกจัดเป็นเลน (lane) เรียงซ้อนกัน

ตัวเลือกรถในฟอร์มจัดรถ (#79 ส่วน B) ใช้ตารางเดียวกันผ่าน `build_picker(...)`: ช่วงที่แสดงคือช่วงของคำขอ ±2 วัน (ไม่เกิน 31 วัน)
มีแถบไฮไลต์ช่วงของคำขอ กลุ่มประเภทที่ผู้ขอขอขึ้นก่อน และทุกแถวบอกว่าเลือกได้หรือไม่ (ชนกับคำขอไหน/ใบยืม DIIS)
โดยใช้ `overlapping_reservations` / `diis_bookings_overlapping` ชุดเดียวกับที่ server ใช้บล็อกตอนจัดรถ
"""

import dataclasses
import datetime

import bson

from kampan import models
from kampan.utils import car_reservation_flow as flow

DAY_CHOICES = (1, 7, 14, 30)
DEFAULT_DAYS = 14

# ค่าเริ่มต้นของ filter สถานะ: งานที่ยังจองรถอยู่ + เสร็จสิ้น (ยกเลิก/ไม่อนุมัติซ่อนไว้ ต้องเลือกเอง)
DEFAULT_STATUSES = ("pending", "active", "cancel_requested", "completed")
STATUS_LABELS = dict(models.car_reservations.RESERVATION_STATUS)
STATUS_CHOICES = models.car_reservations.RESERVATION_STATUS_DISPLAY
ALL_STATUSES = tuple(key for key, _ in STATUS_CHOICES)

# ลำดับกลุ่มประเภทรถ ประเภทอื่นต่อท้ายตามตัวอักษร "ไม่ระบุประเภท" อยู่ท้ายสุด
GROUP_ORDER = ("บัส", "มินิบัส", "ตู้", "เก๋ง")
VEHICLE_TYPE_LABELS = dict(models.vehicles.VEHICLE_TYPES)
UNKNOWN_TYPE_LABEL = "ไม่ระบุประเภท"

THAI_WEEKDAYS = ("จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา.")
THAI_MONTHS = (
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
)

# ตัวเลือกรถ: แสดงช่วงของคำขอ + ก่อน/หลังข้างละกี่วัน และเพดานจำนวนวันทั้งหมด
PICKER_PADDING_DAYS = 2
PICKER_MAX_DAYS = 31
PICKER_NEEDS_WINDOW = "กรอกวัน-เวลาออกและกลับให้ครบ แล้วตารางรถจะแสดงที่นี่"
PICKER_END_BEFORE_START = "เวลากลับต้องหลังเวลาออก"
PICKER_MAX_SLOTS = 10

# ปีที่รับเป็น start (กัน overflow ของ datetime และค่าขยะ)
MIN_YEAR = 2000
MAX_YEAR = 2100

# งานที่ไม่มีเวลากลับ (หรือกลับก่อนออก) วาดยาวเท่านี้
FALLBACK_DURATION = datetime.timedelta(hours=1)

RESERVATION_FIELDS = (
    "status",
    "departure_datetime",
    "return_datetime",
    "creator",
    "location",
    "passenger_number",
    "contact_name",
    "assignments.assignment_id",
    "assignments.car",
    "assignments.driver",
    "assignments.is_overtime",
)

DATETIME_LOCAL_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M")


@dataclasses.dataclass
class TimelineFilters:
    """ตัวกรองของตารางรถ (ไม่รวมวันเริ่ม/จำนวนวัน)"""

    vehicle_types: list = dataclasses.field(default_factory=list)  # ว่าง = ทุกประเภท
    q: str = ""  # ค้นทะเบียน (ส่วนหนึ่งของทะเบียน ไม่สนตัวพิมพ์)
    driver_id: str = ""  # id ผู้ใช้ของ พขร. ว่าง = ทุกคน
    statuses: list = dataclasses.field(default_factory=lambda: list(DEFAULT_STATUSES))
    free_from: datetime.datetime | None = None  # ว่างช่วง: ซ่อนรถที่มีงานทับ [free_from, free_to)
    free_to: datetime.datetime | None = None
    free_error: str = ""  # ช่วง "ว่างช่วง" ที่กรอกมาใช้ไม่ได้ (ไม่ถูกนำไปกรอง)

    @property
    def free_window(self):
        """(free_from, free_to) เมื่อกรอกครบและถูกต้อง ไม่เช่นนั้น None"""
        if self.free_from and self.free_to and self.free_to > self.free_from:
            return self.free_from, self.free_to
        return None


@dataclasses.dataclass
class DayColumn:
    date: datetime.date
    weekday_label: str
    day_number: int
    month_label: str
    is_weekend: bool
    is_today: bool
    is_holiday: bool = False
    holiday_name: str = ""
    index: int = 0
    left_pct: float = 0.0
    width_pct: float = 0.0


@dataclasses.dataclass
class MonthSpan:
    label: str  # เช่น "พ.ย. 2569"
    span: int  # จำนวนวันที่อยู่ในเดือนนี้ของช่วงที่แสดง


@dataclasses.dataclass
class Bar:
    """แท่งหนึ่งแท่ง = หนึ่ง assignment (คำขอ 2 คันมีแท่งในแถวของแต่ละคัน)"""

    reservation_id: str
    assignment_id: str
    status: str
    status_label: str
    departure: datetime.datetime
    return_: datetime.datetime  # เวลากลับจริง (ถ้าไม่มี ใช้ departure + 1 ชม.)
    left_pct: float
    width_pct: float
    clipped_left: bool
    clipped_right: bool
    requester_name: str
    contact_name: str
    driver_name: str  # พขร. ของชุดนี้
    driver_names: list  # พขร. ทุกชุดของคำขอ (คำขอหลายคัน)
    location: str
    passenger_number: int
    is_overtime: bool
    car_id: str
    driver_id: str
    lane: int = 0

    @property
    def label(self):
        """ข้อความหลักบนแท่ง: ปลายทาง (ไม่มีใช้ชื่อผู้ขอ)"""
        return self.location or self.requester_name or "-"


@dataclasses.dataclass
class Conflict:
    """งานที่ทับช่วงของคำขอที่กำลังจัดรถ (ใช้ในตัวเลือกรถ): คำขอในระบบนี้ (มีลิงก์) หรือใบยืมรถ DIIS (ไม่มีหน้ารายละเอียด)"""

    source: str  # "reservation" | "diis"
    reservation_id: str = ""
    requester_name: str = ""
    departure: datetime.datetime | None = None
    return_: datetime.datetime | None = None

    @property
    def is_reservation(self):
        return self.source == "reservation"


@dataclasses.dataclass
class CarRow:
    car: object
    bars: list
    lane_count: int  # จำนวนเลนที่แถวต้องสูง อย่างน้อย 1
    conflict: Conflict | None = None  # เฉพาะตัวเลือกรถ: มีงานทับช่วงของคำขอ = เลือกไม่ได้
    chosen_slot: int = 0  # เฉพาะตัวเลือกรถ: คันที่ (1..N) ที่เลือกรถคันนี้ไว้แล้ว 0 = ยังไม่ได้เลือก

    @property
    def selectable(self):
        return self.conflict is None


@dataclasses.dataclass
class TypeGroup:
    key: str  # ค่า vehicle_type ("" = ไม่ระบุประเภท) ใช้เป็น data-group
    label: str
    rows: list
    is_requested: bool = False  # เฉพาะตัวเลือกรถ: ประเภทที่ผู้ขอขอ
    collapsed: bool = False  # เฉพาะตัวเลือกรถ: เริ่มต้นพับไว้

    @property
    def car_count(self):
        return len(self.rows)


@dataclasses.dataclass
class PickerInfo:
    """ข้อมูลเฉพาะของตัวเลือกรถที่แนบกับ Timeline (Timeline.picker เป็น None = หน้าตารางรถปกติ)"""

    window_start: datetime.datetime
    window_end: datetime.datetime
    left_pct: float  # แถบไฮไลต์ช่วงของคำขอ (% ของช่วงที่แสดง ตัดขอบแล้ว)
    width_pct: float
    kind: str = ""  # ประเภทรถที่ผู้ขอขอ
    active_slot: int = 0  # คันที่กำลังเลือก (1..N) 0 = ไม่ระบุ


@dataclasses.dataclass
class Timeline:
    start_date: datetime.date
    day_count: int
    range_start: datetime.datetime
    range_end: datetime.datetime
    columns: list
    months: list
    groups: list
    now_pct: float | None  # ตำแหน่งเส้นเวลาปัจจุบัน (% ของช่วง) None ถ้าอยู่นอกช่วง
    filters: TimelineFilters
    hour_ticks: list  # [(label, left_pct)] เฉพาะมุมมอง 1 วัน
    car_count: int = 0
    picker: PickerInfo | None = None
    now: datetime.datetime | None = None  # เวลาที่สร้างตาราง ใช้แสดงเวลาปัจจุบันใน legend

    @property
    def end_date(self):
        """วันสุดท้ายที่แสดง"""
        return self.start_date + datetime.timedelta(days=self.day_count - 1)

    @property
    def rows(self):
        return [row for group in self.groups for row in group.rows]


# ---------------------------------------------------------------- parsing


def normalize_days(value):
    try:
        days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return days if days in DAY_CHOICES else DEFAULT_DAYS


def parse_date(value):
    """YYYY-MM-DD เป็น date ค่าผิดรูปแบบหรือนอกช่วงปีที่รับคืน None"""
    try:
        parsed = datetime.date.fromisoformat((value or "").strip())
    except (TypeError, ValueError, AttributeError):
        return None
    return parsed if MIN_YEAR <= parsed.year <= MAX_YEAR else None


def parse_datetime_local(value):
    """ค่าจาก <input type=datetime-local> ค่าผิดรูปแบบหรือนอกช่วงปีที่รับคืน None"""
    text = (value or "").strip() if isinstance(value, str) else ""
    for fmt in DATETIME_LOCAL_FORMATS:
        try:
            parsed = datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed if MIN_YEAR <= parsed.year <= MAX_YEAR else None
    return None


def parse_time(value):
    """HH:MM (หรือ HH:MM:SS) จากช่องเวลา ค่าผิดรูปแบบคืน None"""
    text = (value or "").strip() if isinstance(value, str) else ""
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def parse_free_datetime(args, name, default_time):
    """เวลาเริ่ม/สิ้นสุดของ "ว่างช่วง" (name = free_from / free_to)

    ช่องแยกวัน-เวลา (<name>_date, <name>_time จากปฏิทินและตัวเลือกเวลา) ใช้เมื่อมีส่งมา: ใส่แต่วันที่ใช้ default_time
    (เริ่ม = 00:00, สิ้นสุด = 23:59 คือว่างทั้งวัน) ไม่งั้นอ่านรูปแบบเดิม <name>=YYYY-MM-DDTHH:MM จากลิงก์ที่เก็บไว้
    """
    if f"{name}_date" in args or f"{name}_time" in args:
        date = parse_date(args.get(f"{name}_date"))
        if date is None:
            return None
        return datetime.datetime.combine(date, parse_time(args.get(f"{name}_time")) or default_time)
    return parse_datetime_local(args.get(name))


def _valid_object_id(value):
    return value if value and bson.ObjectId.is_valid(value) else ""


def parse_query(args, today=None):
    """(start_date, days, TimelineFilters) จาก query string (Mapping ที่มี .get/.getlist เช่น request.args)

    ค่าที่ผิดรูปแบบไม่ทำให้พัง: start → วันนี้, days → 14, ประเภท/สถานะที่ไม่รู้จักถูกทิ้ง,
    "ว่างช่วง" ที่ไม่ครบหรือสิ้นสุดไม่หลังเริ่มไม่ถูกนำไปกรอง (free_error บอกกรณีหลัง)
    """
    today = today or datetime.date.today()
    start_date = parse_date(args.get("start")) or today
    days = normalize_days(args.get("days"))

    vehicle_types = [
        value for value in dict.fromkeys(args.getlist("vehicle_type")) if value in VEHICLE_TYPE_LABELS
    ]
    statuses = [value for value in dict.fromkeys(args.getlist("status")) if value in ALL_STATUSES]
    free_from = parse_free_datetime(args, "free_from", datetime.time.min)
    free_to = parse_free_datetime(args, "free_to", datetime.time(23, 59))
    free_error = ""
    if free_from and free_to and free_to <= free_from:
        free_error = "เวลาสิ้นสุดของ \"ว่างช่วง\" ต้องหลังเวลาเริ่ม"
        free_from = free_to = None
    elif not (free_from and free_to):
        # ต้องมีทั้งสองช่องจึงกรองได้
        free_from = free_to = None

    filters = TimelineFilters(
        vehicle_types=vehicle_types,
        q=(args.get("q") or "").strip()[:64],
        driver_id=_valid_object_id((args.get("driver") or "").strip()),
        statuses=statuses or list(DEFAULT_STATUSES),
        free_from=free_from,
        free_to=free_to,
        free_error=free_error,
    )
    return start_date, days, filters


def query_args(start_date, days, filters, today=None):
    """พารามิเตอร์ query ของลิงก์ที่พากลับมาหน้าเดิม (ข้ามค่าที่เป็นค่าเริ่มต้น)

    start ใส่เสมอยกเว้นเป็นวันนี้ (ลิงก์ "วันนี้" จึงไม่มี start)
    """
    today = today or datetime.date.today()
    filters = filters or TimelineFilters()
    args = {}
    if start_date != today:
        args["start"] = start_date.isoformat()
    if days != DEFAULT_DAYS:
        args["days"] = days
    if filters.vehicle_types:
        args["vehicle_type"] = list(filters.vehicle_types)
    if filters.q:
        args["q"] = filters.q
    if filters.driver_id:
        args["driver"] = filters.driver_id
    if sorted(filters.statuses) != sorted(DEFAULT_STATUSES):
        args["status"] = list(filters.statuses)
    window = filters.free_window
    if window:
        args["free_from"] = window[0].strftime("%Y-%m-%dT%H:%M")
        args["free_to"] = window[1].strftime("%Y-%m-%dT%H:%M")
    return args


# ---------------------------------------------------------------- building


def _group_sort_key(vehicle_type):
    if vehicle_type in GROUP_ORDER:
        return (0, GROUP_ORDER.index(vehicle_type), "")
    if vehicle_type:
        return (1, 0, vehicle_type)
    return (2, 0, "")


def _ref_id(ref):
    """id ของ reference ที่ไม่ได้ dereference (DBRef) หรือเอกสารเต็ม"""
    return getattr(ref, "id", ref) if ref is not None else None


def _occupied_car_ids(organization, window):
    """id ของรถที่มีงานทับช่วง (ใบขอในระบบนี้ + ใบยืม DIIS) ใช้ helper ตัวเดียวกับที่ server ใช้บล็อกตอนจัดรถ"""
    start, end = window
    ids = set()
    reservations = flow.overlapping_reservations(organization, start, end).only(
        "assignments.car"
    ).no_dereference()
    for reservation in reservations:
        ids.update(_ref_id(a.car) for a in reservation.assignments if a.car is not None)
    diis = (
        flow.diis_bookings_overlapping(organization, start, end)
        .only("car")
        .no_dereference()
    )
    ids.update(_ref_id(application.car) for application in diis if application.car is not None)
    return ids


def _user_names(user_ids):
    """{id ผู้ใช้: ชื่อไทย} ดึงทีเดียวแทน dereference ทีละคน"""
    user_ids = {uid for uid in user_ids if uid is not None}
    if not user_ids:
        return {}
    users = models.User.objects(id__in=list(user_ids)).only("first_name", "last_name", "resources")
    return {user.id: user.get_name() for user in users}


def _effective_end(reservation):
    departure = reservation.departure_datetime
    end = reservation.return_datetime
    if end is None or end <= departure:
        return departure + FALLBACK_DURATION
    return end


def assign_lanes(bars):
    """จัดแท่งที่เวลาทับกันลงเลนคนละเลน (greedy เรียงตามเวลาออก) คืนจำนวนเลน (อย่างน้อย 1) แท่งต่อกันพอดีใช้เลนเดียวกัน"""
    lane_ends = []
    for bar in sorted(bars, key=lambda b: (b.departure, b.return_)):
        for index, lane_end in enumerate(lane_ends):
            if bar.departure >= lane_end:
                bar.lane = index
                lane_ends[index] = bar.return_
                break
        else:
            bar.lane = len(lane_ends)
            lane_ends.append(bar.return_)
    return max(len(lane_ends), 1)


def _build_bar(reservation, assignment, range_start, range_end, names):
    total = (range_end - range_start).total_seconds()
    departure = reservation.departure_datetime
    end = _effective_end(reservation)
    shown_start = max(departure, range_start)
    shown_end = min(end, range_end)
    left = (shown_start - range_start).total_seconds() / total * 100
    width = (shown_end - shown_start).total_seconds() / total * 100
    creator_id = _ref_id(reservation.creator)
    driver_id = _ref_id(assignment.driver)
    return Bar(
        reservation_id=str(reservation.id),
        assignment_id=str(assignment.assignment_id),
        status=reservation.status,
        status_label=STATUS_LABELS.get(reservation.status, reservation.status),
        departure=departure,
        return_=end,
        left_pct=round(left, 4),
        width_pct=round(width, 4),
        clipped_left=departure < range_start,
        clipped_right=end > range_end,
        requester_name=names.get(creator_id, ""),
        contact_name=reservation.contact_name or "",
        driver_name=names.get(driver_id, ""),
        driver_names=[
            names[_ref_id(a.driver)]
            for a in reservation.assignments
            if _ref_id(a.driver) in names
        ],
        location=reservation.location or "",
        passenger_number=reservation.passenger_number or 0,
        is_overtime=bool(assignment.is_overtime),
        car_id=str(_ref_id(assignment.car)),
        driver_id=str(driver_id) if driver_id is not None else "",
    )


def _day_columns(organization, start_date, days, today):
    end_date = start_date + datetime.timedelta(days=days)
    holidays = {
        holiday.date: holiday.name or ""
        for holiday in models.CarHoliday.objects(
            organization=organization, date__gte=start_date, date__lt=end_date
        )
    }
    columns = []
    for index in range(days):
        day = start_date + datetime.timedelta(days=index)
        columns.append(
            DayColumn(
                date=day,
                weekday_label=THAI_WEEKDAYS[day.weekday()],
                day_number=day.day,
                month_label=f"{THAI_MONTHS[day.month - 1]} {day.year + 543}",
                is_weekend=day.weekday() >= 5,
                is_today=day == today,
                is_holiday=day in holidays,
                holiday_name=holidays.get(day, ""),
                index=index,
                left_pct=round(index / days * 100, 4),
                width_pct=round(100 / days, 4),
            )
        )
    return columns


def _month_spans(columns):
    spans = []
    for column in columns:
        if spans and spans[-1].label == column.month_label:
            spans[-1].span += 1
        else:
            spans.append(MonthSpan(label=column.month_label, span=1))
    return spans


def build_timeline(organization, start_date, days, filters=None, now=None):
    """ตารางรถของ org ช่วง [start_date, start_date + days วัน)

    แสดงเฉพาะรถ active ของ org และคำขอของ org ที่มีชุดรถ/พขร. แล้ว (คำขอที่ยังไม่จัดรถไม่ถูกวาด)
    ใช้ query คำขอครั้งเดียวทั้งช่วง และดึงชื่อผู้ใช้ทีเดียว (ไม่ dereference ทีละแท่ง)
    """
    return _build(organization, start_date, normalize_days(days), filters, now)


def _build(organization, start_date, days, filters=None, now=None, exclude_id=None):
    """ตัวสร้างตารางจริง: days ใช้ตามที่ให้มา (หน้าตารางรถ normalize ก่อน ตัวเลือกรถกำหนดเองจากช่วงของคำขอ)

    exclude_id = ไม่วาดแท่งของคำขอนี้ (ตัวคำขอที่กำลังจัดรถ)
    """
    now = now or datetime.datetime.now()
    filters = filters or TimelineFilters()
    range_start = datetime.datetime.combine(start_date, datetime.time.min)
    range_end = range_start + datetime.timedelta(days=days)

    cars = models.vehicles.Car.objects(organization=organization, status="active")
    if filters.vehicle_types:
        cars = cars.filter(vehicle_type__in=filters.vehicle_types)
    if filters.q:
        cars = cars.filter(license_plate__icontains=filters.q)
    cars = list(cars.order_by("license_plate"))

    window = filters.free_window
    if window and cars:
        occupied = _occupied_car_ids(organization, window)
        cars = [car for car in cars if car.id not in occupied]

    statuses = [s for s in filters.statuses if s in ALL_STATUSES] or list(DEFAULT_STATUSES)
    bars_by_car = {car.id: [] for car in cars}
    if cars:
        reservations = models.CarReservation.objects(
            organization=organization,
            status__in=statuses,
            departure_datetime__lt=range_end,
            return_datetime__gt=range_start,
            assignments__car__in=cars,
            **(
                {"assignments__driver": bson.ObjectId(filters.driver_id)}
                if filters.driver_id
                else {}
            ),
            **({"id__ne": exclude_id} if exclude_id is not None else {}),
        )
        # โหลดเฉพาะฟิลด์ที่วาดแท่ง (ไม่ดึงรายงานปิดงาน/ไฟล์ของแต่ละชุด) และไม่ dereference ผู้ขอ/พขร./รถ
        reservations = list(reservations.only(*RESERVATION_FIELDS).no_dereference())
        names = _user_names(
            {_ref_id(r.creator) for r in reservations}
            | {_ref_id(a.driver) for r in reservations for a in r.assignments}
        )
        for reservation in reservations:
            for assignment in reservation.assignments:
                car_id = _ref_id(assignment.car)
                if car_id not in bars_by_car:
                    continue
                if filters.driver_id and str(_ref_id(assignment.driver)) != filters.driver_id:
                    continue
                bars_by_car[car_id].append(
                    _build_bar(reservation, assignment, range_start, range_end, names)
                )

    rows_by_type = {}
    for car in cars:
        bars = bars_by_car[car.id]
        if filters.driver_id and not bars:
            continue  # ตัวกรอง พขร.: แสดงเฉพาะรถที่ พขร. คนนั้นมีงาน
        lane_count = assign_lanes(bars)
        bars.sort(key=lambda b: (b.lane, b.departure))
        rows_by_type.setdefault(car.vehicle_type or "", []).append(
            CarRow(car=car, bars=bars, lane_count=lane_count)
        )
    groups = [
        TypeGroup(
            key=vehicle_type,
            label=VEHICLE_TYPE_LABELS.get(vehicle_type, vehicle_type) or UNKNOWN_TYPE_LABEL,
            rows=rows,
        )
        for vehicle_type, rows in sorted(
            rows_by_type.items(), key=lambda item: _group_sort_key(item[0])
        )
    ]

    columns = _day_columns(organization, start_date, days, now.date())
    now_pct = None
    if range_start <= now < range_end:
        now_pct = round(
            (now - range_start).total_seconds() / (range_end - range_start).total_seconds() * 100,
            4,
        )
    hour_ticks = (
        [(f"{hour:02d}:00", round(hour / 24 * 100, 4)) for hour in range(0, 24, 3)]
        if days == 1
        else []
    )
    return Timeline(
        start_date=start_date,
        day_count=days,
        range_start=range_start,
        range_end=range_end,
        columns=columns,
        months=_month_spans(columns),
        groups=groups,
        now_pct=now_pct,
        filters=filters,
        hour_ticks=hour_ticks,
        car_count=sum(len(group.rows) for group in groups),
        now=now,
    )


# ---------------------------------------------------------------- car picker


def picker_window_error(start, end):
    """ข้อความบอกว่าช่วงเวลาของคำขอใช้ไม่ได้ (ว่าง = ใช้ได้) ใช้แสดงเป็นคำใบ้แทน error"""
    if start is None or end is None:
        return PICKER_NEEDS_WINDOW
    if end <= start:
        return PICKER_END_BEFORE_START
    return ""


def parse_id_list(value, limit=PICKER_MAX_SLOTS):
    """id รถแยกด้วยจุลภาค เก็บตำแหน่งของแต่ละช่อง (ช่องว่างหรือค่าขยะเป็น "") เช่น "a,,c" = คันที่ 1 และ 3

    ตัดท้ายที่ว่างทิ้งและจำกัดจำนวนช่อง
    """
    items = [
        item.strip() if bson.ObjectId.is_valid(item.strip()) else ""
        for item in (value or "").split(",")[:limit]
    ]
    while items and not items[-1]:
        items.pop()
    return items


def picker_range(start, end):
    """(วันแรก, จำนวนวัน) ของตัวเลือกรถ: ช่วงของคำขอ ±PICKER_PADDING_DAYS วัน ไม่เกิน PICKER_MAX_DAYS วัน"""
    padding = datetime.timedelta(days=PICKER_PADDING_DAYS)
    first = start.date() - padding
    # เวลากลับ 00:00 พอดีถือว่าวันสุดท้ายคือวันก่อนหน้า
    last = (end - datetime.timedelta(microseconds=1)).date() + padding
    return first, min((last - first).days + 1, PICKER_MAX_DAYS)


def _conflicts_by_car(organization, start, end, exclude_id=None, except_driver_id=None):
    """{id รถ: Conflict} ของรถที่มีงานทับ [start, end) ใช้ query คำขอหนึ่งครั้งและ DIIS หนึ่งครั้ง แล้วจับคู่ใน Python

    ใช้ predicate เดียวกับ `_car_is_taken` ของ server: คำขอ (สถานะใน OCCUPYING_STATUSES) ก่อน แล้วค่อยใบยืม DIIS
    except_driver_id = ไม่นับชุดที่ พขร. คนนี้ขับ (งานแทรกใช้รถร่วมกับงานหลักของ พขร. คนเดิมได้ DIIS ไม่ยกเว้น)
    """
    reservations = list(
        flow.overlapping_reservations(organization, start, end, exclude_id=exclude_id)
        .only(
            "creator",
            "contact_name",
            "departure_datetime",
            "return_datetime",
            "assignments.car",
            "assignments.driver",
        )
        .no_dereference()
        .order_by("departure_datetime")
    )
    diis = list(
        flow.diis_bookings_overlapping(organization, start, end)
        .only("car", "departure_datetime", "return_datetime")
        .no_dereference()
    )
    names = _user_names({_ref_id(reservation.creator) for reservation in reservations})

    conflicts = {}
    for reservation in reservations:
        for assignment in reservation.assignments:
            car_id = _ref_id(assignment.car)
            if car_id is None or car_id in conflicts:
                continue
            if except_driver_id is not None and _ref_id(assignment.driver) == except_driver_id:
                continue
            conflicts[car_id] = Conflict(
                source="reservation",
                reservation_id=str(reservation.id),
                requester_name=names.get(_ref_id(reservation.creator))
                or reservation.contact_name
                or "",
                departure=reservation.departure_datetime,
                return_=reservation.return_datetime,
            )
    for application in diis:
        car_id = _ref_id(application.car)
        if car_id is not None and car_id not in conflicts:
            conflicts[car_id] = Conflict(
                source="diis",
                departure=application.departure_datetime,
                return_=application.return_datetime,
            )
    return conflicts


def build_picker(
    organization,
    start,
    end,
    *,
    kind="",
    exclude_id=None,
    driver_id=None,
    selected=(),
    active_slot=0,
    now=None,
):
    """ตัวเลือกรถของฟอร์มจัดรถ: Timeline ของช่วง [start, end) ±2 วัน (ไม่เกิน 31 วัน) พร้อมข้อมูลเลือกรถ

    - `Timeline.picker` ถือแถบไฮไลต์ช่วงของคำขอ; กลุ่มประเภท `kind` (ที่ผู้ขอขอ) มาก่อนและขยายไว้ ประเภทอื่นพับไว้
    - แต่ละ CarRow มี `conflict` (มีงานทับ = เลือกไม่ได้) และ `chosen_slot` จาก `selected`
      (รายการ id รถตามลำดับช่อง ช่องว่างเป็น "")
    - exclude_id = คำขอที่กำลังจัดรถ (ไม่นับว่าชน), driver_id = พขร. ของงานแทรก (ดู `_conflicts_by_car`)
    ต้องมีช่วงเวลาที่ถูกต้อง (`picker_window_error` ว่าง) ไม่เช่นนั้นยก ValueError
    """
    error = picker_window_error(start, end)
    if error:
        raise ValueError(error)
    first, days = picker_range(start, end)
    timeline = _build(organization, first, days, now=now, exclude_id=exclude_id)

    conflicts = _conflicts_by_car(
        organization, start, end, exclude_id=exclude_id, except_driver_id=driver_id
    )
    chosen = {}
    for number, car_id in enumerate(selected, start=1):
        if car_id:
            chosen.setdefault(car_id, number)
    for row in timeline.rows:
        row.conflict = conflicts.get(row.car.id)
        row.chosen_slot = chosen.get(str(row.car.id), 0)

    kind = kind if kind in VEHICLE_TYPE_LABELS else ""
    for group in timeline.groups:
        group.is_requested = bool(kind) and group.key == kind
        group.collapsed = bool(kind) and not group.is_requested
    if kind:
        # sorted เสถียร: ประเภทที่ขอขึ้นก่อน ที่เหลือคงลำดับมาตรฐาน
        timeline.groups.sort(key=lambda group: not group.is_requested)

    total = (timeline.range_end - timeline.range_start).total_seconds()
    shown_start = max(start, timeline.range_start)
    shown_end = min(end, timeline.range_end)
    timeline.picker = PickerInfo(
        window_start=start,
        window_end=end,
        left_pct=round((shown_start - timeline.range_start).total_seconds() / total * 100, 4),
        width_pct=round(max((shown_end - shown_start).total_seconds(), 0) / total * 100, 4),
        kind=kind,
        active_slot=active_slot,
    )
    return timeline


def picker_or_hint(organization, start, end, **kwargs):
    """(timeline, hint) สำหรับ partial ตัวเลือกรถ: ช่วงเวลาใช้ไม่ได้ได้ (None, คำใบ้) ไม่ใช่ error

    kwargs ส่งต่อให้ `build_picker` endpoint `timeline.picker` และหน้าฟอร์มจัดรถ (ตอน render ครั้งแรก) ใช้ตัวเดียวกัน
    """
    error = picker_window_error(start, end)
    if error:
        return None, error
    return build_picker(organization, start, end, **kwargs), ""
