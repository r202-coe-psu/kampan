"""ขั้นอนุมัติใบขอใช้รถของระบบจองรถออนไลน์

เส้นทางกำหนดในโค้ดตามประเภทใบขอ ตอนยื่นจะตรึงเส้นทางลงคำขอ (route_snapshot)
เปลี่ยน RESERVATION_ROUTES ภายหลังแล้วคำขอเก่ายังเดินตามเส้นทางเดิม
"""

import datetime

from kampan import models, utils

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


def can_edit(app, user):
    """ผู้ขอแก้ไขคำขอตัวเองได้จนกว่าผู้บังคับบัญชา (ขั้นแรก) จะตัดสิน"""
    return (
        user is not None
        and user == app.creator
        and app.status == "pending"
        and app.current_step == 0
        and not app.step_approvals
    )


def edit(app, user):
    """บันทึกการแก้ไขที่ view ตั้งค่าลงคำขอแล้ว: ตรึงเส้นทางใหม่ตามพื้นที่เดินทางและลงประวัติ"""
    if not can_edit(app, user):
        raise FlowError("ไม่มีสิทธิ์แก้ไขคำขอนี้")
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.updater = user
    _log(app, "edited", user)
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


def can_close(app, user):
    """พขร. ของงานนี้เท่านั้นที่ปิดงานได้ และต้องเป็นงานที่ active"""
    return (
        app.status == "active"
        and app.driver is not None
        and app.driver == user
        and has_role(app.organization, user, "driver")
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
    app, user, mileage_out, mileage_in, expense_case, fuel_liters=None, cost_baht=None
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

    app.last_mileage_before = mileage_out
    app.last_mileage = mileage_in
    app.fuel_liters = fuel_liters
    app.expense_case = expense_case
    app.cost_baht = cost_baht
    app.completed_at = datetime.datetime.now()
    app.status = "completed"
    _log(app, "completed", user)
    app.save()
    if app.car is not None:
        app.car.last_mileage = mileage_in
        app.car.save()
