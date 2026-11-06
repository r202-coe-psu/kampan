"""ขั้นอนุมัติใบขอใช้รถของระบบจองรถออนไลน์

เส้นทางกำหนดในโค้ดตามประเภทใบขอ ตอนยื่นจะตรึงเส้นทางลงคำขอ (route_snapshot)
เปลี่ยน RESERVATION_ROUTES ภายหลังแล้วคำขอเก่ายังเดินตามเส้นทางเดิม
"""

import datetime

from kampan import models, utils

RESERVATION_STEP_LABELS = {
    "supervisor": "ผู้บังคับบัญชา",
    **dict(models.RESERVATION_POSITIONS),
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


def _log(app, action, actor, step_key="", comment=""):
    app.audit_logs.append(
        models.car_reservations.ReservationAuditLog(
            action=action,
            actor=actor,
            step_key=step_key,
            step_label=step_label(step_key) if step_key else "",
            comment=comment,
        )
    )


def submit(app, actor):
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.current_step = 0
    app.status = "pending"
    _log(app, "submitted", actor)
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
    if app.division is None or user == app.creator:
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


def can_act(app, user):
    key = current_step_key(app)
    if key is None or user is None:
        return False
    if key == "supervisor":
        return _is_division_head(app, user)
    return models.CarReservationPosition.can_act(app.organization, key, user)


def can_confirm_cancel(app, user):
    return app.status == "cancel_requested" and models.CarReservationPosition.can_act(
        app.organization, "dispatcher", user
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


def approve(app, user, comment="", car=None, driver=None, extra_travelers=""):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์อนุมัติขั้นนี้")

    key = current_step_key(app)
    audit_comment = comment
    if key == "dispatcher":
        if car is None or driver is None:
            raise FlowError(CAR_AND_DRIVER_REQUIRED)
        if car not in assignable_cars(app.organization) or driver not in (
            assignable_drivers(app.organization)
        ):
            raise FlowError(CAR_OR_DRIVER_NOT_ASSIGNABLE)
        if _overlapping_bookings(app, car=car).first():
            raise FlowError(f"รถ {car.license_plate} มีงานช่วงเวลานี้แล้ว")
        if _overlapping_bookings(app, driver=driver).first():
            raise FlowError(f"พนักงานขับรถ {driver.get_name()} มีงานช่วงเวลานี้แล้ว")
        app.car = car
        app.driver = driver
        if app.request_type in EXTRA_TRAVELER_TYPES:
            app.extra_travelers = extra_travelers
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
    _log(app, "approved", user, step_key=key, comment=audit_comment)
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
