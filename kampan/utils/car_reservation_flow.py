"""ขั้นอนุมัติใบขอใช้รถของระบบจองรถออนไลน์

เส้นทางกำหนดในโค้ดตามประเภทใบขอ ตอนยื่นจะตรึงเส้นทางลงคำขอ (route_snapshot)
เปลี่ยน RESERVATION_ROUTES ภายหลังแล้วคำขอเก่ายังเดินตามเส้นทางเดิม
"""

import dataclasses
import datetime

from kampan import models, utils
from kampan.utils.template_filters import format_amount

RESERVATION_STEP_LABELS = {
    "supervisor": "ผู้บังคับบัญชา",
    **{
        key: label
        for key, label in models.organizations.ORGANIZATION_ROLES
        if key in models.organizations.RESERVATION_APPROVER_ROLE_KEYS
    },
}

RESERVATION_ROUTES = {
    ("domestic", "in_province"): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ],
    ("domestic", "out_of_province"): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
    ],
    ("airport", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ],
    ("welfare", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
    ],
    ("abroad", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
        "vice_president_hatyai",
        "president",
    ],
}


# คำขอเร่งด่วนที่ผู้จัดรถสร้างเอง: ขั้นผู้จัดรถอนุมัติไปแล้วตอนสร้าง เหลือผู้อำนวยการกองกายภาพ
URGENT_ROUTE = ["dispatcher", "physical_director"]
URGENT_REQUEST_TYPE = "domestic"

# งานแทรก: ผู้จัดรถเพิ่มเอง ไม่ผ่านการอนุมัติ (ลงชื่อขั้นผู้จัดรถไว้ให้เห็นในหน้ารายละเอียด)
INSERT_ROUTE = ["dispatcher"]
INSERT_REQUEST_TYPE = "domestic"
INSERT_PROVINCE_SCOPE = "in_province"
INSERT_COMMENT = "งานแทรก"
INSERT_END_NOT_AFTER_START = "เวลาสิ้นสุดต้องหลังเวลาเริ่ม"
CLOSE_REPORTED_END_REQUIRED = "กรุณาระบุเวลาสิ้นสุดงานจริง"
INSERT_DRIVER_HAS_NO_JOB = "พนักงานขับรถไม่มีงานในวันนี้"

MAX_ADVANCE_DAYS = 30
TOO_FAR_AHEAD = "ขอใช้รถล่วงหน้าได้ไม่เกิน 30 วัน"


MIN_BUSINESS_DAYS = {"abroad": 10}
DEFAULT_MIN_BUSINESS_DAYS = 3


CAR_AND_DRIVER_REQUIRED = "กรุณาเลือกรถและพนักงานขับรถ"


CAR_OR_DRIVER_NOT_ASSIGNABLE = "รถหรือพนักงานขับรถที่เลือกไม่พร้อมใช้งาน"


# ใบที่ผู้จัดรถระบุผู้ร่วมเดินทางเพิ่มได้ตอนจัดรถ ("ขออนุมัติให้ ... เดินทางไปด้วย")
EXTRA_TRAVELER_TYPES = ("domestic", "abroad")

HOLIDAY_ONLY_VEHICLES = ("เก๋ง", "มินิบัส")
HOLIDAY_ONLY_VEHICLE_ERROR = (
    "รถเก๋ง/มินิบัสให้บริการเฉพาะวันเสาร์-อาทิตย์และวันหยุดนักขัตฤกษ์"
)


class FlowError(Exception):
    pass


class MileageError(FlowError):
    pass


MILEAGE_IN_BELOW_OUT = "เลข กม. กลับต้องไม่น้อยกว่าเลข กม. ออก"


def is_too_far_ahead(departure_date, today=None):
    today = today or datetime.date.today()
    return (departure_date - today).days > MAX_ADVANCE_DAYS


def min_business_days(request_type):
    return MIN_BUSINESS_DAYS.get(request_type, DEFAULT_MIN_BUSINESS_DAYS)


def is_short_notice(organization, request_type, departure_date, today=None):
    today = today or datetime.date.today()
    lead = utils.business_days.business_days_between(
        organization, today, departure_date
    )
    return lead < min_business_days(request_type)


def vehicle_allowed_for_trip(organization, vehicle_kind, first_day, last_day):
    """รถเก๋ง/มินิบัสใช้ได้เฉพาะเมื่อทุกวันของการเดินทางเป็นวันเสาร์-อาทิตย์หรือวันหยุด"""
    if vehicle_kind not in HOLIDAY_ONLY_VEHICLES:
        return True
    return utils.business_days.all_days_off(organization, first_day, last_day)


def route_for(request_type, province_scope):
    if request_type == "domestic":
        return list(RESERVATION_ROUTES[(request_type, province_scope)])
    return list(RESERVATION_ROUTES[(request_type, None)])


def step_label(step_key):
    return RESERVATION_STEP_LABELS.get(step_key, step_key)


NO_CHANGES_COMMENT = "ไม่มีการเปลี่ยนแปลง"


def diff_fields(before, after, labels):
    """ช่องที่ค่าเปลี่ยน (before/after = {ชื่อช่อง: ข้อความแสดงผล}) เรียงตาม labels"""
    return [
        models.car_reservations.FieldChange(
            field=name, label=label, old=before[name], new=after[name]
        )
        for name, label in labels.items()
        if before.get(name) != after.get(name)
    ]


NO_VALUE_TEXT = "-"
ASSIGNMENT_LABELS = {
    "car": "รถ",
    "driver": "พนักงานขับรถ",
    "is_overtime": "งานนอกเวลา (OT)",
    "extra_travelers": "ขออนุมัติให้ ... เดินทางไปด้วย",
}
TRIP_REPORT_LABELS = {
    "mileage_out": "เลข กม. ออก",
    "mileage_in": "เลข กม. กลับ",
    "fuel_liters": "น้ำมัน (ลิตร)",
    "expense_case": "กรณีค่าใช้จ่าย",
    "cost_baht": "เป็นเงิน (บาท)",
}


def _yes_no(value):
    return "ใช่" if value else "ไม่ใช่"


def _text_or_dash(value):
    return NO_VALUE_TEXT if value in (None, "") else str(value)


def _amount_or_dash(value):
    return NO_VALUE_TEXT if value is None else format_amount(value)


def _assignment_snapshot(app):
    """ค่าที่ขั้นผู้จัดรถกำหนด (รถ พขร. OT ผู้ร่วมเดินทาง) เป็นข้อความแสดงผล"""
    return {
        "car": app.car.license_plate if app.car else NO_VALUE_TEXT,
        "driver": app.driver.get_name() if app.driver else NO_VALUE_TEXT,
        "is_overtime": _yes_no(app.is_overtime),
        "extra_travelers": _text_or_dash(app.extra_travelers),
    }


def _trip_report_snapshot(app):
    """รายงานท้ายใบที่ พขร. กรอกตอนปิดงาน เป็นข้อความแสดงผล"""
    return {
        "mileage_out": _text_or_dash(app.last_mileage_before),
        "mileage_in": _text_or_dash(app.last_mileage),
        "fuel_liters": _amount_or_dash(app.fuel_liters),
        "expense_case": _text_or_dash(
            dict(models.car_reservations.EXPENSE_CASES).get(
                app.expense_case, app.expense_case
            )
        ),
        "cost_baht": _amount_or_dash(app.cost_baht),
    }


def _log(app, action, actor, step_key="", comment="", changes=()):
    app.audit_logs.append(
        models.car_reservations.ReservationAuditLog(
            action=action,
            actor=actor,
            step_key=step_key,
            step_label=step_label(step_key) if step_key else "",
            comment=comment,
            changes=list(changes),
        )
    )


def submit(app, actor):
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.current_step = 0
    app.status = "pending"
    _log(app, "submitted", actor)
    app.save()


def can_create_urgent(organization, user):
    """เฉพาะผู้ที่ถือ role ผู้จัดรถของ org สร้างคำขอเร่งด่วนได้ (system admin ก็ต้องถือ role นี้)"""
    return has_role(organization, user, "dispatcher")


def submit_urgent(app, dispatcher, car, driver, is_overtime=False):
    """ผู้จัดรถสร้างคำขอเร่งด่วน: ตรึงเส้นทางสั้นแล้วอนุมัติขั้นผู้จัดรถพร้อมรถ/พขร. ในทีเดียว

    ถ้าจัดรถไม่ผ่าน (รถชน ไม่พร้อมใช้) FlowError จะถูกยกก่อนบันทึกอะไรลงฐานข้อมูล
    """
    if app.request_type != URGENT_REQUEST_TYPE or not can_create_urgent(
        app.organization, dispatcher
    ):
        raise FlowError("ไม่มีสิทธิ์สร้างคำขอเร่งด่วน")
    app.is_urgent = True
    app.route_snapshot = list(URGENT_ROUTE)
    app.current_step = 0
    app.status = "pending"
    _log(app, "submitted", dispatcher)
    approve(app, dispatcher, car=car, driver=driver, is_overtime=is_overtime)


def can_create_insert(organization, user):
    """เฉพาะผู้ที่ถือ role ผู้จัดรถของ org เพิ่มงานแทรกได้"""
    return has_role(organization, user, "dispatcher")


def submit_insert(app, dispatcher, car, driver, is_overtime=False):
    """ผู้จัดรถเพิ่มงานแทรก: ใบขอในประเทศในจังหวัดที่ active ทันที ไม่มีขั้นอนุมัติ"""
    if not can_create_insert(app.organization, dispatcher):
        raise FlowError("ไม่มีสิทธิ์เพิ่มงานแทรก")
    if app.return_datetime <= app.departure_datetime:
        raise FlowError(INSERT_END_NOT_AFTER_START)
    if car is None or driver is None:
        raise FlowError(CAR_AND_DRIVER_REQUIRED)
    if car not in assignable_cars(app.organization) or driver not in (
        assignable_drivers(app.organization)
    ):
        raise FlowError(CAR_OR_DRIVER_NOT_ASSIGNABLE)
    if not _has_active_job_that_day(app, driver):
        raise FlowError(INSERT_DRIVER_HAS_NO_JOB)
    if _overlapping_bookings(app, car=car).first():
        raise FlowError(f"รถ {car.license_plate} มีงานช่วงเวลานี้แล้ว")
    app.is_insert = True
    app.request_type = INSERT_REQUEST_TYPE
    app.province_scope = INSERT_PROVINCE_SCOPE
    app.car = car
    app.driver = driver
    app.is_overtime = bool(is_overtime)
    app.route_snapshot = list(INSERT_ROUTE)
    app.current_step = len(app.route_snapshot)
    app.status = "active"
    app.step_approvals.append(
        models.car_reservations.StepApproval(
            step_key="dispatcher",
            label=step_label("dispatcher"),
            decision="approved",
            decided_by=dispatcher,
            decided_at=datetime.datetime.now(),
            comment=INSERT_COMMENT,
        )
    )
    _log(app, "submitted", dispatcher, comment=INSERT_COMMENT)
    app.save()


def _has_active_job_that_day(app, driver):
    """driver มีงาน active อื่นที่คาบเกี่ยววันเดียวกับวันเริ่มของงานนี้"""
    day_start = datetime.datetime.combine(
        app.departure_datetime.date(), datetime.time.min
    )
    return (
        models.CarReservation.objects(
            organization=app.organization,
            driver=driver,
            status="active",
            id__ne=app.id,
            departure_datetime__lt=day_start + datetime.timedelta(days=1),
            return_datetime__gte=day_start,
        ).first()
        is not None
    )


def can_edit(app, user):
    """ผู้ขอแก้ไขคำขอตัวเองได้จนกว่าผู้บังคับบัญชา (ขั้นแรก) จะตัดสิน"""
    return (
        user is not None
        and user == app.creator
        and app.status == "pending"
        and app.current_step == 0
        and not app.step_approvals
    )


def edit(app, user, changes=()):
    """บันทึกการแก้ไขที่ view ตั้งค่าลงคำขอแล้ว: ตรึงเส้นทางใหม่ตามพื้นที่เดินทางและลงประวัติ

    changes = ช่องที่เปลี่ยน (จาก diff_fields) เก็บไว้กับ log ให้เปิดดูเดิม/ใหม่ได้
    """
    if not can_edit(app, user):
        raise FlowError("ไม่มีสิทธิ์แก้ไขคำขอนี้")
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.updater = user
    _log(
        app,
        "edited",
        user,
        comment="" if changes else NO_CHANGES_COMMENT,
        changes=changes,
    )
    app.save()


def current_step_key(app):
    if app.status != "pending" or app.current_step >= len(app.route_snapshot):
        return None
    return app.route_snapshot[app.current_step]


def has_division_head(organization, division, excluding=None):
    """ฝ่ายมีหัวหน้า active อย่างน้อยหนึ่งคน (ไม่นับ excluding)"""
    if division is None:
        return False
    return any(
        member.user is not None and member.user != excluding
        for member in models.OrganizationUserRole.objects(
            organization=organization,
            status="active",
            roles="head",
            division=division,
        )
    )


def _is_division_head(app, user):
    # หัวหน้าฝ่ายที่ยื่นเองอนุมัติขั้นนี้เองได้ (ชั่วคราว รอยืนยันกับกอง)
    if app.division is None:
        return False
    return (
        models.OrganizationUserRole.objects(
            organization=app.organization,
            user=user,
            status="active",
            roles="head",
            division=app.division,
        ).first()
        is not None
    )


def has_role(organization, user, role):
    """user เป็นสมาชิก active ของ org และถือ role นี้"""
    if user is None:
        return False
    return (
        models.OrganizationUserRole.objects(
            organization=organization, user=user, status="active", roles=role
        ).first()
        is not None
    )


def members_with_role(organization, role):
    """ผู้ใช้ที่เป็นสมาชิก active ของ org และถือ role นี้ (ไม่ซ้ำคน)"""
    users = []
    for member in models.OrganizationUserRole.objects(
        organization=organization, status="active", roles=role
    ):
        if member.user is not None and member.user not in users:
            users.append(member.user)
    return users


def can_act(app, user):
    key = current_step_key(app)
    if key is None or user is None:
        return False
    if key == "supervisor":
        return _is_division_head(app, user)
    return has_role(app.organization, user, key)


def can_print_paper(app, user):
    """พิมพ์ใบขอใช้รถได้: ผู้ขอ, ผู้อนุมัติ/หัวหน้าฝ่าย (รวมผู้จัดรถ) หรือ admin ของ org"""
    if user is None:
        return False
    return (
        user == app.creator
        or is_approver(app.organization, user)
        or has_role(app.organization, user, "admin")
    )


def can_confirm_cancel(app, user):
    return app.status == "cancel_requested" and has_role(
        app.organization, user, "dispatcher"
    )


def is_approver(organization, user):
    """ผู้ใช้อนุมัติได้อย่างน้อยหนึ่งขั้นใน org นี้: ถือ role ผู้อนุมัติ หรือเป็นหัวหน้าฝ่ายที่ active"""
    if user is None:
        return False
    return (
        models.OrganizationUserRole.objects(
            organization=organization,
            user=user,
            status="active",
            roles__in=["head", *models.organizations.RESERVATION_APPROVER_ROLE_KEYS],
        ).first()
        is not None
    )


def is_driver_only(organization, user):
    """พนักงานขับรถล้วน (ถือ role driver แต่ไม่ได้อนุมัติ) ไม่ได้ขอใช้รถ: ใช้หน้างานของตัวเองแทนหน้าคำขอ"""
    return has_role(organization, user, "driver") and not is_approver(
        organization, user
    )


def inbox_for(organization, user):
    """คำขอที่รออนุมัติหรือรอรับทราบการยกเลิก และ user ทำแทนขั้นปัจจุบันได้ เรียงตามวันเดินทาง"""
    waiting = models.CarReservation.objects(
        organization=organization, status__in=["pending", "cancel_requested"]
    ).order_by("departure_datetime")
    return [app for app in waiting if can_act(app, user) or can_confirm_cancel(app, user)]


def assignable_cars(organization):
    return models.vehicles.Car.objects(
        organization=organization, status="active"
    ).order_by("license_plate")


def assignable_drivers(organization):
    members = models.OrganizationUserRole.objects(
        organization=organization, status="active", roles="driver"
    )
    return [member.user for member in members if member.user is not None]


# ผู้ดูสถิติภาระงานพนักงานขับรถ: ผู้จัดรถ ผู้บริหาร และ admin ของ org (admin ของระบบผ่านอยู่แล้ว)
STATS_ROLES = (
    "admin",
    "dispatcher",
    "vehicle_unit_head",
    "strategy_head",
    "physical_director",
)


@dataclasses.dataclass
class DriverWorkload:
    """ภาระงานของ พขร. หนึ่งคนช่วง `days` วันล่าสุด (งานที่นับ = เสร็จสิ้นหรือ active)"""

    driver: object
    in_hours_jobs: int = 0
    ot_jobs: int = 0
    hours: float = 0.0
    km: int = 0
    upcoming: int = 0
    busy: bool = False


def driver_workload(
    organization, *, now, window_start, window_end, days=30, since=None
):
    """แถวภาระงานของ พขร. ที่จัดได้ทุกคน เรียงงานล่าสุดน้อยไปมาก แล้วชั่วโมงน้อยไปมาก

    นับงานที่ออกเดินทางตั้งแต่ `since` (ไม่ระบุ = ย้อนหลัง `days` วัน) ถึง `now`
    km = ผลรวมระยะทาง (เลข กม. กลับ - ออก) ของงานที่ปิดแล้ว
    """
    rows = {
        driver.id: DriverWorkload(driver=driver)
        for driver in assignable_drivers(organization)
    }
    since = since or now - datetime.timedelta(days=days)
    jobs = models.CarReservation.objects(
        organization=organization,
        driver__in=[row.driver for row in rows.values()],
        status__in=["completed", "active"],
        departure_datetime__gte=since,
        departure_datetime__lte=now,
    )
    for job in jobs:
        row = rows[job.driver.id]
        if job.is_overtime:
            row.ot_jobs += 1
        else:
            row.in_hours_jobs += 1
        started = job.started_at or job.departure_datetime
        finished = job.completed_at or job.return_datetime or started
        row.hours += (finished - started).total_seconds() / 3600
        row.km += job.distance_km or 0
    ahead = models.CarReservation.objects(
        organization=organization,
        driver__in=[row.driver for row in rows.values()],
        status__in=["pending", "active", "cancel_requested"],
        return_datetime__gt=window_start,
        departure_datetime__lt=window_end,
    )
    for job in ahead:
        rows[job.driver.id].busy = True
    for job in models.CarReservation.objects(
        organization=organization,
        driver__in=[row.driver for row in rows.values()],
        status="active",
        departure_datetime__gt=now,
    ):
        rows[job.driver.id].upcoming += 1
    return sorted(
        rows.values(), key=lambda row: (row.in_hours_jobs + row.ot_jobs, row.hours)
    )


def _overlapping_bookings(app, **resource):
    """คำขออื่นของ org ที่จองรถ/คนขับคนเดียวกัน (ผ่านขั้นจัดรถแล้วและยังไม่จบ) เวลาทับกัน"""
    return models.CarReservation.objects(
        organization=app.organization,
        status__in=["pending", "active", "cancel_requested"],
        id__ne=app.id,
        departure_datetime__lt=app.return_datetime,
        return_datetime__gt=app.departure_datetime,
        **resource,
    )


def approve(
    app,
    user,
    comment="",
    car=None,
    driver=None,
    extra_travelers="",
    is_overtime=False,
):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์อนุมัติขั้นนี้")

    key = current_step_key(app)
    audit_comment = comment
    changes = []
    if key == "dispatcher":
        if car is None or driver is None:
            raise FlowError(CAR_AND_DRIVER_REQUIRED)
        if car not in assignable_cars(app.organization) or driver not in (
            assignable_drivers(app.organization)
        ):
            raise FlowError(CAR_OR_DRIVER_NOT_ASSIGNABLE)
        if _overlapping_bookings(app, car=car).first():
            raise FlowError(f"รถ {car.license_plate} มีงานช่วงเวลานี้แล้ว")
        before = _assignment_snapshot(app)
        app.car = car
        app.driver = driver
        app.is_overtime = bool(is_overtime)
        if app.request_type in EXTRA_TRAVELER_TYPES:
            app.extra_travelers = extra_travelers
        changes = diff_fields(before, _assignment_snapshot(app), ASSIGNMENT_LABELS)
        audit_comment = f"จัดรถ {car.license_plate} พนักงานขับรถ {driver.get_name()}"
        if comment:
            audit_comment += f" ({comment})"
    app.step_approvals.append(
        models.car_reservations.StepApproval(
            step_key=key,
            label=step_label(key),
            decision="approved",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=comment,
        )
    )
    _log(
        app, "approved", user, step_key=key, comment=audit_comment, changes=changes
    )
    app.current_step += 1
    if app.current_step >= len(app.route_snapshot):
        app.status = "active"
    app.save()


def deny(app, user, comment):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์ดำเนินการขั้นนี้")
    if not comment or not comment.strip():
        raise FlowError("ต้องระบุเหตุผลที่ไม่อนุมัติ")

    key = current_step_key(app)
    app.step_approvals.append(
        models.car_reservations.StepApproval(
            step_key=key,
            label=step_label(key),
            decision="denied",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=comment,
        )
    )
    _log(app, "denied", user, step_key=key, comment=comment)
    app.status = "denied"
    app.save()


def can_cancel(app, user):
    return user == app.creator and app.status in ("pending", "active")


def cancel(app, user, reason=""):
    if not can_cancel(app, user):
        raise FlowError("ไม่มีสิทธิ์ยกเลิกคำขอนี้")
    if app.car is None:
        app.status = "cancelled"
        _log(app, "cancelled", user, comment=reason)
    else:
        app.status = "cancel_requested"
        _log(app, "cancel_requested", user, comment=reason)
    app.save()


def confirm_cancel(app, user):
    if not can_confirm_cancel(app, user):
        raise FlowError("ไม่มีสิทธิ์รับทราบการยกเลิก")
    app.status = "cancelled"
    _log(app, "cancel_confirmed", user, step_key="dispatcher")
    app.save()


def can_set_overtime(app, user):
    """ผู้จัดรถสลับสถานะ OT ได้ตราบที่คำขอยัง active"""
    return app.status == "active" and has_role(app.organization, user, "dispatcher")


def set_overtime(app, user, is_overtime):
    if not can_set_overtime(app, user):
        raise FlowError("ไม่มีสิทธิ์แก้สถานะงานนอกเวลา")
    before = _assignment_snapshot(app)
    app.is_overtime = bool(is_overtime)
    _log(
        app,
        "overtime_changed",
        user,
        step_key="dispatcher",
        comment="ตั้งเป็นงานนอกเวลา (OT)" if app.is_overtime else "ตั้งเป็นงานในเวลา",
        changes=diff_fields(
            before,
            _assignment_snapshot(app),
            {"is_overtime": ASSIGNMENT_LABELS["is_overtime"]},
        ),
    )
    app.save()


def can_close(app, user):
    """พขร. ของงานนี้เท่านั้นที่ปิดงานได้ และต้องเป็นงานที่ active"""
    return (
        app.status == "active"
        and app.driver is not None
        and app.driver == user
        and has_role(app.organization, user, "driver")
    )


def can_view_mileage_photos(app, user):
    """รูปเลขไมล์: ผู้ขอ พขร. ของงาน ผู้จัดรถ/ผู้อนุมัติ และ admin ขององค์กร"""
    if user is None:
        return False
    return (
        app.creator == user
        or app.driver == user
        or has_role(app.organization, user, "admin")
        or is_approver(app.organization, user)
    )


def can_start(app, user):
    """พขร. ของงานนี้กดเริ่มงานได้ (เงื่อนไขเดียวกับการปิดงาน)"""
    return can_close(app, user)


def start_trip(app, user):
    """บันทึกเวลาเริ่มงานครั้งแรกเท่านั้น: กดซ้ำไม่เปลี่ยนเวลาและไม่ลงประวัติซ้ำ"""
    if not can_start(app, user):
        raise FlowError("ไม่มีสิทธิ์เริ่มงานนี้")
    if app.started_at is not None:
        return
    app.started_at = datetime.datetime.now()
    _log(app, "started", user)
    app.save()


def earlier_active_task(app):
    """งาน active ของรถคันเดียวกันที่ออกเดินทางก่อนงานนี้ (ต้องปิดก่อน) ไม่มีคือ None"""
    if app.car is None:
        return None
    return (
        models.CarReservation.objects(
            organization=app.organization,
            car=app.car,
            status="active",
            departure_datetime__lt=app.departure_datetime,
        )
        .order_by("departure_datetime")
        .first()
    )


def close_trip(
    app,
    user,
    mileage_out,
    mileage_in,
    expense_case,
    fuel_liters=None,
    cost_baht=None,
    client_ip=None,
    photo_out=None,
    photo_in=None,
):
    """ปิดงาน: บันทึกรายงานท้ายใบ (กม. ออก/กลับ น้ำมัน กรณีค่าใช้จ่าย เป็นเงิน) และอัปเดตเลขไมล์รถ"""
    if not can_close(app, user):
        raise FlowError("ไม่มีสิทธิ์ปิดงานนี้")
    if mileage_in < mileage_out:
        raise MileageError(MILEAGE_IN_BELOW_OUT)
    earlier = earlier_active_task(app)
    if earlier is not None:
        raise FlowError(
            "ต้องปิดงานที่ออกเดินทางก่อนของรถคันเดียวกันก่อน: "
            f"{earlier.location} ({earlier.departure_datetime.strftime('%d/%m/%Y %H:%M')} น.)"
        )

    before = _trip_report_snapshot(app)
    app.last_mileage_before = mileage_out
    app.last_mileage = mileage_in
    app.fuel_liters = fuel_liters
    app.expense_case = expense_case
    app.cost_baht = cost_baht
    app.completed_at = datetime.datetime.now()
    for photo_field, upload in (
        (app.mileage_photo_out, photo_out),
        (app.mileage_photo_in, photo_in),
    ):
        photo_field.replace(
            upload, filename=upload.filename, content_type=upload.content_type
        )
    app.mileage_photos_at = app.completed_at
    networks = app.organization.car_reservation_campus_networks
    app.closed_ip = client_ip
    app.closed_off_campus = (
        not utils.campus_network.ip_in_networks(client_ip, networks)
        if networks
        else None
    )
    app.status = "completed"
    _log(
        app,
        "completed",
        user,
        changes=diff_fields(before, _trip_report_snapshot(app), TRIP_REPORT_LABELS),
    )
    app.save()
    if app.car is not None:
        app.car.last_mileage = mileage_in
        app.car.save()


def _is_admin(organization, user):
    return "admin" in user.roles or has_role(organization, user, "admin")


def can_confirm_close(app, user, now=None):
    """ผู้ขอยืนยันเวลาปิดงานได้ครั้งเดียว ภายใน 3 วันหลังปิดงาน

    ผู้ขอคือผู้สร้างคำขอ แต่ถ้าผู้สร้างเป็นผู้จัดรถ (คำขอเร่งด่วน/งานแทรก) ไม่มีผู้ขอตัวจริงในระบบ
    จึงให้เฉพาะ admin (ของระบบหรือของ org) ตอบแทน
    """
    if (
        user is None
        or app.status != "completed"
        or app.close_confirmation_status(now) != "pending"
    ):
        return False
    if has_role(app.organization, app.creator, "dispatcher"):
        return _is_admin(app.organization, user)
    return user == app.creator


def confirm_close(app, user, correct, reported_end=None, note="", now=None):
    """ผู้ขอตอบว่าเวลาเริ่ม/ปิดงานที่ พขร. บันทึกถูกต้อง หรือไม่ถูกต้อง (ต้องแจ้งเวลาสิ้นสุดจริง)"""
    if not can_confirm_close(app, user, now):
        raise FlowError("ไม่มีสิทธิ์ยืนยันเวลาปิดงานนี้")
    if not correct and reported_end is None:
        raise FlowError(CLOSE_REPORTED_END_REQUIRED)
    app.close_confirmed_by = user
    app.close_confirmed_at = now or datetime.datetime.now()
    if correct:
        app.close_confirmation = "confirmed"
        _log(app, "close_confirmed", user)
    else:
        note = (note or "").strip()
        app.close_confirmation = "disputed"
        app.close_reported_end = reported_end
        app.close_dispute_note = note
        comment = f"เวลาสิ้นสุดจริง {reported_end.strftime('%d/%m/%Y %H:%M')} น."
        _log(app, "close_disputed", user, comment=f"{comment} ({note})" if note else comment)
    app.save()
