"""ขั้นอนุมัติใบขอใช้รถของระบบจองรถออนไลน์

เส้นทางกำหนดในโค้ดตามประเภทใบขอ ตอนยื่นจะตรึงเส้นทางลงคำขอ (route_snapshot)
เปลี่ยน RESERVATION_ROUTES ภายหลังแล้วคำขอเก่ายังเดินตามเส้นทางเดิม
"""

import dataclasses
import datetime

import mongoengine as me

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
DUPLICATE_CAR = "เลือกรถคันเดียวกันซ้ำในคำขอเดียวไม่ได้"
DUPLICATE_DRIVER = "เลือกพนักงานขับรถคนเดียวกันซ้ำในคำขอเดียวไม่ได้"
REDUCE_REASON_REQUIRED = "จัดรถน้อยกว่าที่ผู้ขอขอ ต้องระบุเหตุผลที่ลดจำนวนรถ"
REDUCE_FIELD_LABEL = "จำนวนรถ (คัน)"


CAR_OR_DRIVER_NOT_ASSIGNABLE = "รถหรือพนักงานขับรถที่เลือกไม่พร้อมใช้งาน"


def too_many_vehicles_error(limit):
    return f"จัดรถได้ไม่เกิน {limit} คัน ตามจำนวนรถที่ผู้ขอขอ"


def asks_extra_travelers(app):
    """ผู้จัดรถระบุผู้ร่วมเดินทางเพิ่มได้ตอนจัดรถ (ช่อง (3) ของใบ): เฉพาะในประเทศต่างจังหวัดและต่างประเทศ"""
    return app.request_type == "abroad" or (
        app.request_type == "domestic" and app.province_scope == "out_of_province"
    )

HOLIDAY_ONLY_VEHICLES = ("เก๋ง", "มินิบัส")
HOLIDAY_ONLY_VEHICLE_ERROR = (
    "รถเก๋ง/มินิบัสให้บริการเฉพาะวันเสาร์-อาทิตย์และวันหยุดนักขัตฤกษ์"
)


class FlowError(Exception):
    pass


class MileageError(FlowError):
    pass


class ConcurrentChangeError(FlowError):
    """มีคนอื่นเปลี่ยนคำขอนี้ไปก่อนระหว่างที่เรากำลังบันทึก"""


class CarConflictError(FlowError):
    """รถคันนี้มีคำขอ (CarReservation) อื่นในช่วงเวลาที่ทับกัน: เก็บคำขอที่ชนไว้ให้ view ทำลิงก์ไปหน้ารายละเอียด"""

    def __init__(self, car, conflict):
        self.car = car
        self.conflict = conflict
        super().__init__(
            f"รถ {car.license_plate} มีงานช่วงเวลานี้แล้ว "
            f"(ผู้ขอ {self.requester_name} เวลา {self.window})"
        )

    @property
    def requester_name(self):
        creator = self.conflict.creator
        return creator.get_name() if creator else self.conflict.contact_name or "-"

    @property
    def window(self):
        departure = self.conflict.departure_datetime
        return_ = self.conflict.return_datetime
        return (
            f"{departure.strftime('%d/%m/%Y %H:%M')} - "
            f"{return_.strftime('%d/%m/%Y %H:%M')} น."
        )


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


def earliest_regular_departure(organization, request_type, today=None):
    """วันออกเดินทางวันแรกที่ไม่นับว่ากระชั้นชิด (ก่อนหน้านี้ต้องยืนยันเป็นคำขอเร่งด่วน)"""
    return utils.business_days.nth_business_day_after(
        organization, today or datetime.date.today(), min_business_days(request_type)
    )


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
    "extra_travelers": "ขออนุมัติให้ผู้ร่วมเดินทางไปปฏิบัติงานต่างจังหวัด",
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


def _plate(assignment):
    car = assignment.car
    return car.license_plate if car else NO_VALUE_TEXT


def _is_multi(app):
    return len(app.assignments) > 1


def _assignment_note(app, assignment):
    """ข้อความระบุรถของชุดนี้ใน log: ใบขอรถคันเดียวไม่ต้องระบุ (ชัดอยู่แล้ว)"""
    return f"รถ {_plate(assignment)}" if _is_multi(app) else ""


def _assignment_snapshot(app, slots=None):
    """ค่าที่ขั้นผู้จัดรถกำหนด (รถ พขร. OT รายชุด และผู้ร่วมเดินทาง) เป็นข้อความแสดงผล

    ชุดที่ n เก็บที่ car_n / driver_n / is_overtime_n (นับจาก 1) slots = จำนวนช่องอย่างน้อยที่ต้องมี
    ช่องที่ยังไม่มีชุดเป็น "-" เพื่อเทียบก่อน/หลังจัดรถได้
    """
    slots = max(slots or 0, len(app.assignments), 1)
    values = {}
    for number in range(1, slots + 1):
        assignment = app.assignments[number - 1] if number <= len(app.assignments) else None
        values[f"car_{number}"] = _plate(assignment) if assignment else NO_VALUE_TEXT
        values[f"driver_{number}"] = (
            assignment.driver.get_name()
            if assignment and assignment.driver
            else NO_VALUE_TEXT
        )
        # ช่องที่ยังไม่มีชุดนับเป็นงานในเวลา (ค่าตั้งต้น) ไม่งั้นการจัดรถครั้งแรกจะลง log ว่า OT เปลี่ยนจาก "-"
        values[f"is_overtime_{number}"] = _yes_no(
            assignment.is_overtime if assignment else False
        )
    values["extra_travelers"] = _text_or_dash(app.extra_travelers)
    return values


def _assignment_labels(slots):
    """ป้ายของ _assignment_snapshot: มีหลายชุดจะต่อท้ายว่า "คันที่ n" ให้รู้ว่าแก้ของชุดไหน"""
    labels = {}
    for number in range(1, max(slots, 1) + 1):
        suffix = f" คันที่ {number}" if slots > 1 else ""
        for name in ("car", "driver", "is_overtime"):
            labels[f"{name}_{number}"] = ASSIGNMENT_LABELS[name] + suffix
    labels["extra_travelers"] = ASSIGNMENT_LABELS["extra_travelers"]
    return labels


def _trip_report_snapshot(assignment):
    """รายงานท้ายใบที่ พขร. กรอกตอนปิดงานของชุดนี้ เป็นข้อความแสดงผล"""
    return {
        "mileage_out": _text_or_dash(assignment.last_mileage_before),
        "mileage_in": _text_or_dash(assignment.last_mileage),
        "fuel_liters": _amount_or_dash(assignment.fuel_liters),
        "expense_case": _text_or_dash(
            dict(models.car_reservations.EXPENSE_CASES).get(
                assignment.expense_case, assignment.expense_case
            )
        ),
        "cost_baht": _amount_or_dash(assignment.cost_baht),
    }


def _trip_report_labels(app, assignment):
    """ป้ายของ _trip_report_snapshot: มีหลายชุดจะต่อท้ายด้วยทะเบียนรถของชุดนั้น"""
    if not _is_multi(app):
        return dict(TRIP_REPORT_LABELS)
    return {
        name: f"{label} ({_plate(assignment)})"
        for name, label in TRIP_REPORT_LABELS.items()
    }


def _new_log(action, actor, step_key="", comment="", changes=()):
    return models.car_reservations.ReservationAuditLog(
        action=action,
        actor=actor,
        step_key=step_key,
        step_label=step_label(step_key) if step_key else "",
        comment=comment,
        changes=list(changes),
    )


def _log(app, action, actor, step_key="", comment="", changes=()):
    app.audit_logs.append(_new_log(action, actor, step_key, comment, changes))


def signature_snapshot(user):
    """bytes ของลายเซ็นปัจจุบันของ user (ไม่มีลายเซ็นคืน None)"""
    if user is None or not user.signature:
        return None
    gridout = user.signature.get()
    gridout.seek(0)
    return gridout.read()


def submit(app, actor):
    app.requester_signature = signature_snapshot(app.creator)
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.current_step = 0
    app.status = "pending"
    _log(app, "submitted", actor)
    app.save()


def can_create_urgent(organization, user):
    """เฉพาะผู้ที่ถือ role ผู้จัดรถของ org สร้างคำขอเร่งด่วนได้ (system admin ก็ต้องถือ role นี้)"""
    return has_role(organization, user, "dispatcher")


def submit_urgent(
    app,
    dispatcher,
    car=None,
    driver=None,
    is_overtime=False,
    *,
    assignments=None,
    reduce_reason="",
):
    """ผู้จัดรถสร้างคำขอเร่งด่วน: ตรึงเส้นทางสั้นแล้วอนุมัติขั้นผู้จัดรถพร้อมรถ/พขร. ในทีเดียว

    จัดหลายคันส่ง `assignments` (รายการ {car, driver, is_overtime}) หรือจัดคันเดียวด้วย car/driver
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
    approve(
        app,
        dispatcher,
        car=car,
        driver=driver,
        is_overtime=is_overtime,
        assignments=assignments,
        reduce_reason=reduce_reason,
    )


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
    # งานแทรกใช้รถคันเดียวกับงานหลักของ พขร. คนเดิมได้ งานของคนอื่น/รถยืม DIIS ยังบล็อก
    taken = _car_is_taken(app, car, except_driver=driver)
    if taken:
        raise _car_conflict_error(car, taken)
    app.is_insert = True
    app.request_type = INSERT_REQUEST_TYPE
    app.province_scope = INSERT_PROVINCE_SCOPE
    app.assignments = [
        models.car_reservations.CarAssignment(
            car=car, driver=driver, is_overtime=bool(is_overtime)
        )
    ]
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
            assignments__driver=driver,
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
    ids = _inbox_ids(organization, user)
    if not ids:
        return []
    return list(models.CarReservation.objects(id__in=ids).order_by("departure_datetime"))


def inbox_count(organization, user):
    """จำนวนใน inbox_for โดยไม่โหลดเอกสารเต็ม (sidebar นับทุกหน้า)"""
    return len(_inbox_ids(organization, user))


def _ref_id(value):
    return getattr(value, "id", value)


def _inbox_ids(organization, user):
    """กฎเดียวกับ can_act / can_confirm_cancel แต่โหลด role ของ user ครั้งเดียว แทนการ query ต่อคำขอ"""
    if user is None:
        return []
    roles, head_divisions = set(), set()
    for member in (
        models.OrganizationUserRole.objects(
            organization=organization, user=user, status="active"
        )
        .no_dereference()
        .only("roles", "division")
    ):
        roles.update(member.roles)
        if "head" in member.roles and member.division is not None:
            head_divisions.add(_ref_id(member.division))
    if not roles:
        return []
    waiting = (
        models.CarReservation.objects(
            organization=organization, status__in=["pending", "cancel_requested"]
        )
        .no_dereference()
        .only("status", "current_step", "route_snapshot", "division")
    )
    ids = []
    for app in waiting:
        if app.status == "cancel_requested":
            allowed = "dispatcher" in roles
        else:
            key = current_step_key(app)
            if key == "supervisor":
                allowed = app.division is not None and _ref_id(app.division) in head_divisions
            else:
                allowed = key is not None and key in roles
        if allowed:
            ids.append(app.id)
    return ids


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
    upcoming_hours: float = 0.0
    busy: bool = False


class DriverJob:
    """งานหนึ่งชุด (assignment) ของ พขร. หนึ่งคนในคำขอหนึ่งใบ

    คำขอที่มีหลายชุดกลายเป็นหลายงาน ตามชุดของแต่ละ พขร. ช่องของชุด (รถ พขร. OT ระยะทาง เวลาเริ่ม/ปิด)
    มาจาก assignment ส่วนช่องอื่น (วันออก-กลับ สถานที่ ผู้ขอ ฯลฯ) อ่านผ่านไปที่คำขอ
    จึงใช้แทนคำขอใน template ที่เคยวนงานของ พขร. ได้
    """

    def __init__(self, reservation, assignment):
        self.reservation = reservation
        self.assignment = assignment

    @property
    def id(self):
        return self.reservation.id

    @property
    def car(self):
        return self.assignment.car

    @property
    def feedback_key(self):
        """(id คำขอ, id รถ): แบบประเมินผูกกับคู่นี้ ไม่ใช่คำขออย่างเดียว"""
        return (self.reservation.id, self.assignment.car.id if self.assignment.car else None)

    @property
    def driver(self):
        return self.assignment.driver

    @property
    def is_overtime(self):
        return self.assignment.is_overtime

    @property
    def distance_km(self):
        return self.assignment.distance_km

    @property
    def started_at(self):
        return self.assignment.started_at

    @property
    def completed_at(self):
        return self.assignment.completed_at

    def __getattr__(self, name):
        # เรียกเฉพาะเมื่อหา attribute ปกติไม่เจอ: อ่านต่อจากคำขอ (กัน recursion ตอนยังไม่มี reservation)
        if name == "reservation" or name.startswith("__"):
            raise AttributeError(name)
        return getattr(self.reservation, name)


def worked_hours(job, reservation=None):
    """ชั่วโมงทำงานของงานที่เกิดแล้ว: เวลาเริ่ม/ปิดงานจริง ถ้าไม่มีใช้เวลาออก/กลับตามใบขอ

    job = DriverJob หรือ assignment (ส่งคำขอที่ assignment นั้นอยู่เป็น reservation)
    """
    reservation = reservation or job
    started = job.started_at or reservation.departure_datetime
    finished = job.completed_at or reservation.return_datetime or started
    return (finished - started).total_seconds() / 3600


def booked_hours(job, reservation=None):
    """ชั่วโมงที่จองไว้ของงานที่ยังไม่เกิด ตามเวลาออก-กลับในใบขอ"""
    reservation = reservation or job
    return (
        reservation.return_datetime - reservation.departure_datetime
    ).total_seconds() / 3600


def _jobs_of(reservations, drivers):
    """DriverJob ของทุกชุดที่ พขร. อยู่ในรายการ drivers (เรียงตามคำขอที่ส่งมา)"""
    ids = {driver.id for driver in drivers}
    return [
        DriverJob(reservation, assignment)
        for reservation in reservations
        for assignment in reservation.assignments
        if assignment.driver is not None and assignment.driver.id in ids
    ]


def driver_jobs(organization, driver, *, now, since):
    """(งานที่ออกเดินทางแล้วช่วง since..now ใหม่ก่อน, งาน active ที่ยังไม่ออก เรียงตามวันออก)

    ใช้เงื่อนไขเดียวกับ driver_workload ตัวเลขในหน้ารายคนจึงตรงกับตารางรวม
    คำขอที่มีหลายชุดนับเฉพาะชุดของ driver (เป็น DriverJob หนึ่งงานต่อชุด)
    """
    done = models.CarReservation.objects(
        organization=organization,
        assignments__driver=driver,
        status__in=["completed", "active"],
        departure_datetime__gte=since,
        departure_datetime__lte=now,
    ).order_by("-departure_datetime")
    upcoming = models.CarReservation.objects(
        organization=organization,
        assignments__driver=driver,
        status="active",
        departure_datetime__gt=now,
    ).order_by("departure_datetime")
    return _jobs_of(done, [driver]), _jobs_of(upcoming, [driver])


def driver_workload(
    organization, *, now, window_start, window_end, days=30, since=None
):
    """แถวภาระงานของ พขร. ที่จัดได้ทุกคน เรียงงานล่าสุดน้อยไปมาก แล้วชั่วโมงน้อยไปมาก

    นับงานรายชุด (assignment) ที่ออกเดินทางตั้งแต่ `since` (ไม่ระบุ = ย้อนหลัง `days` วัน) ถึง `now`
    คำขอที่มีสองชุดนับให้ พขร. แต่ละคนแยกกัน ด้วย OT และเวลาของชุดนั้น
    km = ผลรวมระยะทาง (เลข กม. กลับ - ออก) ของงานที่ปิดแล้ว
    upcoming / upcoming_hours = งาน active ที่ยังไม่ออกเดินทาง และชั่วโมงที่จองไว้ตามใบขอ
    """
    rows = {
        driver.id: DriverWorkload(driver=driver)
        for driver in assignable_drivers(organization)
    }
    drivers = [row.driver for row in rows.values()]
    since = since or now - datetime.timedelta(days=days)
    jobs = models.CarReservation.objects(
        organization=organization,
        assignments__driver__in=drivers,
        status__in=["completed", "active"],
        departure_datetime__gte=since,
        departure_datetime__lte=now,
    )
    for job in _jobs_of(jobs, drivers):
        row = rows[job.driver.id]
        if job.is_overtime:
            row.ot_jobs += 1
        else:
            row.in_hours_jobs += 1
        row.hours += worked_hours(job)
        row.km += job.distance_km or 0
    ahead = models.CarReservation.objects(
        organization=organization,
        assignments__driver__in=drivers,
        status__in=["pending", "active", "cancel_requested"],
        return_datetime__gt=window_start,
        departure_datetime__lt=window_end,
    )
    for job in _jobs_of(ahead, drivers):
        rows[job.driver.id].busy = True
    for job in _jobs_of(
        models.CarReservation.objects(
            organization=organization,
            assignments__driver__in=drivers,
            status="active",
            departure_datetime__gt=now,
        ),
        drivers,
    ):
        row = rows[job.driver.id]
        row.upcoming += 1
        row.upcoming_hours += booked_hours(job)
    return sorted(
        rows.values(), key=lambda row: (row.in_hours_jobs + row.ot_jobs, row.hours)
    )


ALREADY_HANDLED = "คำขอนี้เพิ่งถูกดำเนินการโดยผู้อื่น กรุณาเปิดหน้าใหม่แล้วตรวจสอบอีกครั้ง"

# ยืมรถ (DIIS) ใช้รถคันเดียวกัน: คำขอที่ยังไม่จบและมีรถแล้วนับว่าจองรถคันนั้น
DIIS_BOOKED_STATUSES = ["pending on header", "pending on director", "pending on admin", "active"]


def _save_if(app, **expected):
    """บันทึกเฉพาะเมื่อ state ใน DB ยังเป็นค่าตอนตรวจสิทธิ์ สองคนกดพร้อมกัน คนที่สองได้ FlowError แทนการเขียนทับ"""
    try:
        app.save(save_condition=expected)
    except me.errors.SaveConditionError:
        raise ConcurrentChangeError(ALREADY_HANDLED)


def _car_booked_by_diis(app, car):
    return models.vehicle_applications.CarApplication.objects(
        organization=app.organization,
        car=car,
        status__in=DIIS_BOOKED_STATUSES,
        departure_datetime__lt=app.return_datetime,
        return_datetime__gt=app.departure_datetime,
    ).first()


def _car_is_taken(app, car, except_driver=None):
    """คำขอที่จองรถคันนี้ทับเวลา (CarReservation) หรือใบยืมรถ DIIS ที่ทับเวลา ไม่มีเป็น None

    except_driver = ไม่นับคำขอที่ใช้รถคันนี้กับ พขร. คนนี้ (งานหลักของ พขร. ที่งานแทรกใช้รถร่วม)
    """
    return _overlapping_bookings(
        app, car=car, except_driver=except_driver
    ).first() or _car_booked_by_diis(app, car)


def _car_conflict_error(car, taken):
    """taken จาก _car_is_taken: คำขอในระบบนี้ได้ CarConflictError (ลิงก์ได้) ใบยืม DIIS ไม่มีหน้ารายละเอียดในโมดูลนี้ จึงเป็นข้อความธรรมดา"""
    if isinstance(taken, models.CarReservation):
        return CarConflictError(car, taken)
    return FlowError(
        f"รถ {car.license_plate} มีงานช่วงเวลานี้แล้ว (ถูกยืมผ่านระบบยืมรถเดิม)"
    )


def _overlapping_bookings(app, car=None, driver=None, except_driver=None):
    """คำขออื่นของ org ที่จองรถ/คนขับคนเดียวกัน (ผ่านขั้นจัดรถแล้วและยังไม่จบ) เวลาทับกัน

    car/driver เป็นเงื่อนไขของชุดเดียวกัน (ชุดที่ใช้รถคันนั้นกับ พขร. คนนั้น)
    except_driver = ข้ามชุดที่ พขร. คนนี้ขับ (ใช้กับ car เพื่อไม่นับงานหลักของ พขร. ที่งานแทรกใช้รถร่วม)
    """
    match = {}
    if car is not None:
        match["car"] = car
    if driver is not None:
        match["driver"] = driver
    if except_driver is not None:
        match["driver__ne"] = except_driver
    return models.CarReservation.objects(
        organization=app.organization,
        status__in=["pending", "active", "cancel_requested"],
        id__ne=app.id,
        departure_datetime__lt=app.return_datetime,
        return_datetime__gt=app.departure_datetime,
        assignments__match=match,
    )


def _assignment_inputs(assignments, car, driver, is_overtime):
    """[(รถ, พขร., OT)] จากรายการชุด (dict หรือ object ที่มี car/driver/is_overtime) หรือ car/driver เดี่ยวแบบเดิม"""
    if assignments is None:
        if car is None and driver is None:
            return []
        return [(car, driver, bool(is_overtime))]
    return [
        (
            _field_of(item, "car"),
            _field_of(item, "driver"),
            bool(_field_of(item, "is_overtime", False)),
        )
        for item in assignments
    ]


def _field_of(item, name, default=None):
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _validate_dispatch(app, inputs, reduce_reason):
    """ตรวจชุดรถ+พขร. ที่ผู้จัดรถเลือก (ครบตามจำนวน หรือน้อยกว่าพร้อมเหตุผล ไม่ซ้ำ พร้อมใช้ และไม่ชนเวลา)

    คืนจำนวนรถที่ผู้ขอขอ ยก FlowError/CarConflictError ถ้าไม่ผ่าน
    """
    if not inputs or any(car is None or driver is None for car, driver, _ in inputs):
        raise FlowError(CAR_AND_DRIVER_REQUIRED)
    required = models.car_reservations.required_vehicle_count(app)
    if len(inputs) > required:
        raise FlowError(too_many_vehicles_error(required))
    if len(inputs) < required and not (reduce_reason or "").strip():
        raise FlowError(REDUCE_REASON_REQUIRED)
    cars = [car for car, _, _ in inputs]
    drivers = [driver for _, driver, _ in inputs]
    if len({car.id for car in cars}) < len(cars):
        raise FlowError(DUPLICATE_CAR)
    if len({driver.id for driver in drivers}) < len(drivers):
        raise FlowError(DUPLICATE_DRIVER)
    assignable_car_ids = {car.id for car in assignable_cars(app.organization)}
    assignable_driver_ids = {d.id for d in assignable_drivers(app.organization)}
    if any(car.id not in assignable_car_ids for car in cars) or any(
        driver.id not in assignable_driver_ids for driver in drivers
    ):
        raise FlowError(CAR_OR_DRIVER_NOT_ASSIGNABLE)
    for car in cars:
        taken = _car_is_taken(app, car)
        if taken:
            raise _car_conflict_error(car, taken)
    return required


def approve(
    app,
    user,
    comment="",
    car=None,
    driver=None,
    extra_travelers="",
    is_overtime=False,
    *,
    assignments=None,
    reduce_reason="",
):
    """อนุมัติขั้นปัจจุบัน

    ขั้นผู้จัดรถต้องจัดรถให้ครบ: `assignments` = รายการ {car, driver, is_overtime} (หรือ car/driver เดี่ยว
    แบบเดิมเป็นชุดเดียว) ครบตามจำนวนรถที่ผู้ขอขอ หรือน้อยกว่าพร้อม `reduce_reason` (ลด details.vehicle_count
    และลง log vehicle_count_reduced) ถ้ารถคันใดชนเวลาหลัง save ทั้งการจัดรถถูกถอยกลับ
    """
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์อนุมัติขั้นนี้")

    key = current_step_key(app)
    step = app.current_step
    previous = _DispatchState(app)
    audit_comment = comment
    changes = []
    if key == "dispatcher":
        inputs = _assignment_inputs(assignments, car, driver, is_overtime)
        required = _validate_dispatch(app, inputs, reduce_reason)
        slots = max(len(inputs), len(app.assignments))
        before = _assignment_snapshot(app, slots)
        app.assignments = [
            models.car_reservations.CarAssignment(
                car=car_, driver=driver_, is_overtime=is_overtime_
            )
            for car_, driver_, is_overtime_ in inputs
        ]
        if asks_extra_travelers(app):
            app.extra_travelers = extra_travelers
        changes = diff_fields(
            before, _assignment_snapshot(app, slots), _assignment_labels(slots)
        )
        if len(inputs) < required:
            app.details.vehicle_count = len(inputs)
            _log(
                app,
                "vehicle_count_reduced",
                user,
                step_key=key,
                comment=reduce_reason.strip(),
                changes=[
                    models.car_reservations.FieldChange(
                        field="vehicle_count",
                        label=REDUCE_FIELD_LABEL,
                        old=str(required),
                        new=str(len(inputs)),
                    )
                ],
            )
        audit_comment = "จัดรถ " + ", ".join(
            f"{car_.license_plate} พนักงานขับรถ {driver_.get_name()}"
            for car_, driver_, _ in inputs
        )
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
            signature=signature_snapshot(user),
        )
    )
    _log(
        app, "approved", user, step_key=key, comment=audit_comment, changes=changes
    )
    app.current_step += 1
    if app.current_step >= len(app.route_snapshot):
        app.status = "active"
    _save_if(app, status="pending", current_step=step)
    if key == "dispatcher":
        # ผู้จัดรถอีกคนจัดรถคันเดียวกันช่วงเวลาเดียวกันในจังหวะเดียวกัน: ถอยการจัดรถทั้งหมดของเรา ไม่ให้รถถูกจองซ้อน
        for assigned_car in app.cars:
            taken = _car_is_taken(app, assigned_car)
            if taken:
                _undo_dispatch(app, step, previous)
                raise _car_conflict_error(assigned_car, taken)


class _DispatchState:
    """สถานะของคำขอก่อนขั้นอนุมัติหนึ่งขั้น ไว้ถอยกลับถ้ารถชนหลัง save"""

    def __init__(self, app):
        self.assignments = list(app.assignments)
        self.extra_travelers = app.extra_travelers
        self.vehicle_count = getattr(app.details, "vehicle_count", None)
        self.log_count = len(app.audit_logs)


def _undo_dispatch(app, step, previous):
    """ถอยทั้งขั้นผู้จัดรถ: ชุดรถ จำนวนรถ ขั้น/สถานะ รายการอนุมัติ และ log ที่ขั้นนี้เพิ่ม (รวม log ลดจำนวนรถ)

    ทำใน update เดียวและมีเงื่อนไขว่าคำขอยังอยู่ที่ขั้นถัดไป
    """
    values = {
        "current_step": step,
        "status": "pending",
        "assignments": [a.to_mongo() for a in previous.assignments],
        "extra_travelers": previous.extra_travelers,
    }
    if previous.vehicle_count is not None:
        values["details.vehicle_count"] = previous.vehicle_count
    models.CarReservation._get_collection().update_one(
        {"_id": app.id, "current_step": step + 1},
        {
            "$set": values,
            "$pop": {"step_approvals": 1},
            # $slice ตัดกลับเหลือจำนวน log ก่อนอนุมัติ (ขั้นนี้อาจเพิ่มสองรายการ)
            "$push": {"audit_logs": {"$each": [], "$slice": previous.log_count}},
        },
    )
    app.reload()


def deny(app, user, comment):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์ดำเนินการขั้นนี้")
    if not comment or not comment.strip():
        raise FlowError("ต้องระบุเหตุผลที่ไม่อนุมัติ")

    key = current_step_key(app)
    step = app.current_step
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
    _save_if(app, status="pending", current_step=step)


def can_cancel(app, user):
    return user == app.creator and app.status in ("pending", "active")


def cancel(app, user, reason=""):
    if not can_cancel(app, user):
        raise FlowError("ไม่มีสิทธิ์ยกเลิกคำขอนี้")
    status = app.status
    if not app.assignments:
        app.status = "cancelled"
        _log(app, "cancelled", user, comment=reason)
    else:
        app.status = "cancel_requested"
        _log(app, "cancel_requested", user, comment=reason)
    _save_if(app, status=status, current_step=app.current_step)


def confirm_cancel(app, user):
    if not can_confirm_cancel(app, user):
        raise FlowError("ไม่มีสิทธิ์รับทราบการยกเลิก")
    app.status = "cancelled"
    _log(app, "cancel_confirmed", user, step_key="dispatcher")
    _save_if(app, status="cancel_requested")


def _owns(app, assignment):
    """assignment เป็นชุดของคำขอนี้จริง (กันส่งชุดของคำขออื่นเข้ามา)"""
    return (
        assignment is not None
        and app.get_assignment(assignment.assignment_id) is not None
    )


def can_set_overtime(app, user, assignment):
    """ผู้จัดรถแก้สถานะ OT ของชุดนี้ได้หลังจัดรถแล้ว ระหว่างรอผู้อนุมัติขั้นถัดไป เมื่ออนุมัติครบแล้วล็อก (ทุกชุด)"""
    return (
        app.status == "pending"
        and _owns(app, assignment)
        and has_role(app.organization, user, "dispatcher")
    )


def _update_assignment(app, assignment, *, status, guard=None, values=(), log=None):
    """แก้เฉพาะช่องของชุดนี้ในคำขอแบบ atomic (ไม่ save ทั้งเอกสาร) คืน True ถ้าเงื่อนไขผ่านและแก้แล้ว

    ถ้า พขร. สองคนปิดงานของชุดตัวเองพร้อมกัน การ save ทั้งเอกสารจะให้คนหลังเขียนทับชุดของคนแรก
    จึงอัปเดตเฉพาะ element นี้ ($set assignments.$.<ช่อง>) เมื่อ element ที่มี assignment_id นี้ยังเข้าเงื่อนไข guard
    และคำขออยู่ใน status ที่คาดไว้ แล้ว $push log ในคำสั่งเดียวกัน
    ใช้ collection ตรง ๆ เพราะ update() ของ MongoEngine ไม่แปลง FileField ในตำแหน่ง $ (รูปเลขไมล์)
    values = {ชื่อช่อง: ค่า Python} แปลงเป็นค่าของ Mongo ผ่าน field ของ CarAssignment
    """
    fields = models.car_reservations.CarAssignment._fields
    update = {
        "$set": {
            f"assignments.$.{name}": None if value is None else fields[name].to_mongo(value)
            for name, value in dict(values).items()
        }
    }
    if log is not None:
        update["$push"] = {"audit_logs": log.to_mongo()}
    result = models.CarReservation._get_collection().update_one(
        {
            "_id": app.id,
            "status": {"$in": [status] if isinstance(status, str) else list(status)},
            "assignments": {
                "$elemMatch": {"assignment_id": assignment.assignment_id, **(guard or {})}
            },
        },
        update,
    )
    return result.matched_count == 1


def set_overtime(app, user, assignment, is_overtime):
    if not can_set_overtime(app, user, assignment):
        raise FlowError("ไม่มีสิทธิ์แก้สถานะงานนอกเวลา")
    is_overtime = bool(is_overtime)
    note = _assignment_note(app, assignment)
    comment = "ตั้งเป็นงานนอกเวลา (OT)" if is_overtime else "ตั้งเป็นงานในเวลา"
    label = ASSIGNMENT_LABELS["is_overtime"]
    log = _new_log(
        "overtime_changed",
        user,
        step_key="dispatcher",
        comment=f"{comment} ({note})" if note else comment,
        changes=diff_fields(
            {"is_overtime": _yes_no(assignment.is_overtime)},
            {"is_overtime": _yes_no(is_overtime)},
            {"is_overtime": f"{label} ({_plate(assignment)})" if note else label},
        ),
    )
    if not _update_assignment(
        app,
        assignment,
        status="pending",
        values={"is_overtime": is_overtime},
        log=log,
    ):
        raise ConcurrentChangeError(ALREADY_HANDLED)
    app.reload()


def can_close(app, user, assignment):
    """พขร. ของชุดนี้เท่านั้นที่ปิดงานได้ และต้องเป็นคำขอที่ active และชุดนี้ยังไม่ปิด"""
    return (
        app.status == "active"
        and _owns(app, assignment)
        and not assignment.is_closed
        and assignment.driver is not None
        and assignment.driver == user
        and has_role(app.organization, user, "driver")
    )


def can_view_mileage_photos(app, user):
    """รูปเลขไมล์: ผู้ขอ พขร. ของชุดใดก็ได้ในคำขอ ผู้จัดรถ/ผู้อนุมัติ และ admin ขององค์กร"""
    if user is None:
        return False
    return (
        app.creator == user
        or any(assignment.driver == user for assignment in app.assignments)
        or has_role(app.organization, user, "admin")
        or is_approver(app.organization, user)
    )


def can_start(app, user, assignment):
    """พขร. ของชุดนี้กดเริ่มงานได้ (เงื่อนไขเดียวกับการปิดงาน)"""
    return can_close(app, user, assignment)


def start_trip(app, user, assignment):
    """บันทึกเวลาเริ่มงานของชุดนี้ครั้งแรกเท่านั้น: กดซ้ำไม่เปลี่ยนเวลาและไม่ลงประวัติซ้ำ"""
    if not can_start(app, user, assignment):
        raise FlowError("ไม่มีสิทธิ์เริ่มงานนี้")
    if assignment.started_at is not None:
        return
    note = _assignment_note(app, assignment)
    if _update_assignment(
        app,
        assignment,
        status="active",
        guard={"started_at": None, "completed_at": None},
        values={"started_at": datetime.datetime.now()},
        log=_new_log("started", user, comment=note),
    ):
        app.reload()
        return
    # ไม่ผ่านเงื่อนไข: กดซ้ำจากอีกแท็บ (เริ่มไปแล้ว ไม่ต้องทำอะไร) หรือคำขอ/ชุดเปลี่ยนสถานะไปแล้ว
    app.reload()
    fresh = app.get_assignment(assignment.assignment_id)
    if fresh is not None and fresh.started_at is not None:
        return
    raise ConcurrentChangeError(ALREADY_HANDLED)


def close_trip(
    app,
    user,
    assignment,
    mileage_out,
    mileage_in,
    expense_case,
    fuel_liters=None,
    cost_baht=None,
    client_ip=None,
    photo_in=None,
):
    """ปิดงานของชุดนี้: บันทึกรายงานท้ายใบ (กม. ออก/กลับ น้ำมัน กรณีค่าใช้จ่าย เป็นเงิน) และอัปเดตเลขไมล์รถ

    ปิดงานได้ไม่ต้องเรียงตามวันเดินทาง (คนขับอีกคนลืมปิดก็ไม่ติด) เลขไมล์รถจึงเก็บค่าสูงสุดที่เคยกรอก
    งานเก่าที่มาปิดทีหลังด้วยเลขที่ต่ำกว่าจะไม่ทำให้เลขไมล์รถถอยหลัง

    เขียนเฉพาะชุดนี้แบบ atomic (ปิดซ้ำชุดเดิมได้ ConcurrentChangeError ชุดอื่นของคำขอไม่ถูกแตะ)
    เมื่อทุกชุดปิดครบจึงเปลี่ยนคำขอเป็น completed ครั้งเดียว คืน True ถ้าการเรียกนี้เป็นตัวที่ปิดคำขอ
    หลังเรียก app ถูก reload แล้ว: ถ้าจะอ่านชุดนี้ต่อให้เรียก app.get_assignment(assignment_id) ใหม่
    """
    if not can_close(app, user, assignment):
        raise FlowError("ไม่มีสิทธิ์ปิดงานนี้")
    if mileage_in < mileage_out:
        raise MileageError(MILEAGE_IN_BELOW_OUT)

    car = assignment.car
    report = models.car_reservations.CarAssignment(
        last_mileage_before=mileage_out,
        last_mileage=mileage_in,
        fuel_liters=fuel_liters,
        expense_case=expense_case,
        cost_baht=cost_baht,
    )
    completed_at = datetime.datetime.now()
    networks = app.organization.car_reservation_campus_networks
    closed_off_campus = (
        not utils.campus_network.ip_in_networks(client_ip, networks)
        if networks
        else None
    )
    labels = _trip_report_labels(app, assignment)
    log = _new_log(
        "completed",
        user,
        comment=_assignment_note(app, assignment),
        changes=diff_fields(
            _trip_report_snapshot(assignment), _trip_report_snapshot(report), labels
        ),
    )
    # ถ่ายเฉพาะเลขไมล์ขากลับ (mileage_photo_out เก็บไว้ให้งานเก่าที่เคยถ่ายสองรูป)
    photo = assignment.mileage_photo_in
    photo.replace(
        photo_in, filename=photo_in.filename, content_type=photo_in.content_type
    )
    closed = False
    try:
        closed = _update_assignment(
            app,
            assignment,
            status="active",
            guard={"completed_at": None},
            values={
                "last_mileage_before": mileage_out,
                "last_mileage": mileage_in,
                "fuel_liters": fuel_liters,
                "expense_case": expense_case,
                "cost_baht": cost_baht,
                "completed_at": completed_at,
                "mileage_photo_in": photo,
                "mileage_photos_at": completed_at,
                "closed_ip": client_ip,
                "closed_off_campus": closed_off_campus,
            },
            log=log,
        )
    finally:
        if not closed:
            photo.delete()  # ไม่ได้ปิด (ปิดซ้ำ/สถานะเปลี่ยน) ไม่ทิ้งรูปค้างใน GridFS
    if not closed:
        raise ConcurrentChangeError(ALREADY_HANDLED)
    if car is not None:
        car.update(max__last_mileage=mileage_in)
        car.reload("last_mileage")
    app.reload()
    if not app.all_closed:
        return False
    # ชุดสุดท้ายที่ปิดเป็นคนพลิก: เงื่อนไข status=active ทำให้สองคนปิดพร้อมกันพลิกได้ครั้งเดียว
    flipped = models.CarReservation.objects(id=app.id, status="active").update_one(
        set__status="completed"
    )
    app.reload()
    return flipped == 1


def _is_admin(organization, user):
    return "admin" in user.roles or has_role(organization, user, "admin")


def can_confirm_close(app, user, assignment, now=None):
    """ผู้ขอยืนยันเวลาปิดงานของชุดนี้ได้ครั้งเดียว ภายใน 3 วันหลังที่ พขร. ของชุดนั้นปิดงาน

    ผู้ขอคือผู้สร้างคำขอ แต่ถ้าผู้สร้างเป็นผู้จัดรถ (คำขอเร่งด่วน/งานแทรก) ไม่มีผู้ขอตัวจริงในระบบ
    จึงให้เฉพาะ admin (ของระบบหรือของ org) ตอบแทน
    """
    if (
        user is None
        or app.status not in ("active", "completed")
        or not _owns(app, assignment)
        or assignment.close_confirmation_status(now) != "pending"
    ):
        return False
    if has_role(app.organization, app.creator, "dispatcher"):
        return _is_admin(app.organization, user)
    return user == app.creator


def confirm_close(
    app, user, assignment, correct, reported_end=None, note="", now=None
):
    """ผู้ขอตอบว่าเวลาเริ่ม/ปิดงานที่ พขร. ของชุดนี้บันทึกถูกต้อง หรือไม่ถูกต้อง (ต้องแจ้งเวลาสิ้นสุดจริง)"""
    if not can_confirm_close(app, user, assignment, now):
        raise FlowError("ไม่มีสิทธิ์ยืนยันเวลาปิดงานนี้")
    if not correct and reported_end is None:
        raise FlowError(CLOSE_REPORTED_END_REQUIRED)
    values = {"close_confirmed_by": user, "close_confirmed_at": now or datetime.datetime.now()}
    note_of_car = _assignment_note(app, assignment)
    if correct:
        values["close_confirmation"] = "confirmed"
        log = _new_log("close_confirmed", user, comment=note_of_car)
    else:
        note = (note or "").strip()
        values.update(
            close_confirmation="disputed",
            close_reported_end=reported_end,
            close_dispute_note=note,
        )
        comment = f"เวลาสิ้นสุดจริง {reported_end.strftime('%d/%m/%Y %H:%M')} น."
        if note:
            comment = f"{comment} ({note})"
        if note_of_car:
            comment = f"{note_of_car}: {comment}"
        log = _new_log("close_disputed", user, comment=comment)
    # ตอบได้ครั้งเดียว: ผู้ขอสองแท็บกดพร้อมกัน คนที่สองไม่ผ่านเงื่อนไข close_confirmation ว่าง
    if not _update_assignment(
        app,
        assignment,
        status=["active", "completed"],
        guard={"completed_at": {"$ne": None}, "close_confirmation": None},
        values=values,
        log=log,
    ):
        raise ConcurrentChangeError(ALREADY_HANDLED)
    app.reload()
