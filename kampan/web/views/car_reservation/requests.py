import datetime
import io
import re

from bson import ObjectId
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user
from markupsafe import Markup, escape

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint("requests", __name__, url_prefix="/requests")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]
flow = utils.car_reservation_flow
car_timeline = utils.car_timeline
finance = utils.car_reservation_finance


def car_choice_label(car):
    """ทะเบียน (ประเภท, N ที่นั่ง) ไม่มีจำนวนที่นั่งก็ไม่แสดงส่วนนั้น"""
    details = [car.vehicle_type or "-"]
    if car.seat_count:
        details.append(f"{car.seat_count} ที่นั่ง")
    return f"{car.license_plate} ({', '.join(details)})"


def flash_flow_error(error):
    """flash ข้อความของ FlowError: รถชนกับคำขออื่นให้ลิงก์ไปหน้ารายละเอียดของคำขอนั้น

    Markup ไม่ถูก Jinja escape ซ้ำ จึงต้อง escape ค่าที่ผู้ใช้กรอก (ชื่อผู้ขอ ทะเบียน) เอง
    """
    if not isinstance(error, flow.CarConflictError):
        flash(str(error), "danger")
        return
    link = url_for(
        "car_reservation.requests.detail",
        request_id=error.conflict.id,
        organization_id=g.organization.id,
    )
    flash(
        Markup(
            "รถ {plate} มีงานช่วงเวลานี้แล้ว "
            '(ผู้ขอ {name} เวลา {window}) <a href="{link}" class="link font-bold">ดูคำขอที่ชน</a>'
        ).format(
            plate=error.car.license_plate,
            name=error.requester_name,
            window=error.window,
            link=link,
        ),
        "danger",
    )


def get_request_or_404(request_id):
    try:
        reservation = models.CarReservation.objects(
            id=request_id, organization=g.organization
        ).first()
    except Exception:
        reservation = None
    if reservation is None:
        abort(404)
    return reservation


@module.route("/")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    user = current_user._get_current_object()
    if flow.is_driver_only(g.organization, user):
        # พขร. ล้วนไม่ได้ขอใช้รถ: พาไปหน้างานของตัวเอง
        return redirect(
            url_for("car_reservation.tasks.index", organization_id=g.organization.id)
        )
    filters = request_filters(request.args)
    reservations = models.CarReservation.objects(
        organization=g.organization, creator=user, **filters.query
    ).order_by("-created_date")
    return render_template(
        "/car_reservation/requests/index.html",
        organization=g.organization,
        reservations=reservations,
        filters=filters,
        request_types=models.car_reservations.RESERVATION_TYPES,
        statuses=models.car_reservations.RESERVATION_STATUS,
    )


class RequestFilters:
    """ตัวกรองหน้า "คำขอของฉัน" จาก query string: ข้อความ ประเภท สถานะ ช่วงวันออกเดินทาง"""

    def __init__(self, q, request_type, status, date_from, date_to):
        self.q = q
        self.request_type = request_type
        self.status = status
        self.date_from = date_from
        self.date_to = date_to

    @property
    def active(self):
        return any([self.q, self.request_type, self.status, self.date_from, self.date_to])

    @property
    def query(self):
        query = {}
        if self.q:
            query["__raw__"] = {
                "$or": [
                    {"request_reason": {"$regex": re.escape(self.q), "$options": "i"}},
                    {"location": {"$regex": re.escape(self.q), "$options": "i"}},
                ]
            }
        if self.request_type:
            query["request_type"] = self.request_type
        if self.status:
            query["status"] = self.status
        if self.date_from:
            query["departure_datetime__gte"] = datetime.datetime.combine(
                self.date_from, datetime.time.min
            )
        if self.date_to:
            query["departure_datetime__lte"] = datetime.datetime.combine(
                self.date_to, datetime.time.max
            )
        return query


def parse_date(value):
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def request_filters(args):
    types = {key for key, _ in models.car_reservations.RESERVATION_TYPES}
    statuses = {key for key, _ in models.car_reservations.RESERVATION_STATUS}
    request_type = args.get("request_type", "")
    status = args.get("status", "")
    return RequestFilters(
        q=args.get("q", "").strip()[:128],
        request_type=request_type if request_type in types else "",
        status=status if status in statuses else "",
        date_from=parse_date(args.get("date_from")),
        date_to=parse_date(args.get("date_to")),
    )


def quick_decision_form(route, dom_id, reservation):
    """ฟอร์มใน modal อนุมัติ/ไม่อนุมัติของกล่องรออนุมัติ: next ตั้งเป็น URL กล่องนี้ และ id ไม่ซ้ำต่อ modal"""
    next_url = url_for("car_reservation.requests.inbox", organization_id=g.organization.id)
    if route == "deny":
        form = forms.car_reservation.DenyDecisionForm(next=next_url)
    else:
        form = forms.car_reservation.QuickApprovalForm(
            next=next_url, step=reservation.current_step
        )
    return forms.car_reservation.with_id_suffix(form, dom_id)


@module.route("/inbox")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def inbox():
    waiting = flow.inbox_for(g.organization, current_user._get_current_object())
    return render_template(
        "/car_reservation/requests/inbox.html",
        organization=g.organization,
        reservations=waiting,
        step_key=flow.current_step_key,
        quick_form=quick_decision_form,
        inbox_url=url_for(
            "car_reservation.requests.inbox", organization_id=g.organization.id
        ),
        step_label=lambda app: flow.step_label(
            flow.current_step_key(app) or "dispatcher"
        ),
    )


DEPARTURE_IN_THE_PAST = "วันออกเดินทางต้องไม่ย้อนหลัง"


def validate_submission(form, organization, request_type, urgent_by_dispatcher=False):
    """ตรวจฟอร์มคำขอตามกฎร่วม (ล่วงหน้าเกินกำหนด วันกลับ รถวันหยุด ขอกะทันหัน) ทั้งตอนยื่นและตอนแก้ไข

    urgent_by_dispatcher: ผู้จัดรถสร้างเอง ข้ามกฎรถวันหยุดและขอกะทันหัน (ที่เหลือยังตรวจ)

    คืน (ผ่านหรือไม่, จำนวนวันทำการขั้นต่ำที่ต้องยืนยันเร่งด่วน (None ถ้าไม่ต้อง), เป็นคำขอเร่งด่วนหรือไม่)
    """
    submitted = form.validate_on_submit()
    if (
        submitted
        and not urgent_by_dispatcher
        and form.departure_date.data < datetime.date.today()
    ):
        form.departure_date.errors.append(DEPARTURE_IN_THE_PAST)
        submitted = False
    if submitted and flow.is_too_far_ahead(form.departure_date.data):
        form.departure_date.errors.append(flow.TOO_FAR_AHEAD)
        submitted = False
    if submitted and datetime.datetime.combine(
        form.return_date.data, form.return_time.data
    ) < datetime.datetime.combine(form.departure_date.data, form.departure_time.data):
        form.return_date.errors.append("วันกลับต้องไม่ก่อนวันออกเดินทาง")
        submitted = False
    if (
        submitted
        and not urgent_by_dispatcher
        and request_type == "domestic"
        and not flow.vehicle_allowed_for_trip(
            organization,
            form.vehicle_kind.data,
            form.departure_date.data,
            form.return_date.data,
        )
    ):
        form.vehicle_kind.errors.append(flow.HOLIDAY_ONLY_VEHICLE_ERROR)
        submitted = False
    short_notice_days = None
    is_urgent = False
    if (
        submitted
        and not urgent_by_dispatcher
        and flow.is_short_notice(organization, request_type, form.departure_date.data)
    ):
        if form.confirm_urgent.data:
            is_urgent = True
        else:
            short_notice_days = flow.min_business_days(request_type)
            submitted = False
    return submitted, short_notice_days, is_urgent


def short_notice_context(organization, request_type):
    """ให้หน้าฟอร์มเตือนวันเดินทางกระชั้นชิดได้ก่อนส่ง (ไฟล์แนบจึงไม่หายไปกับการส่งรอบแรก)"""
    return {
        "min_business_days": flow.min_business_days(request_type),
        "regular_from": flow.earliest_regular_departure(organization, request_type),
    }


@module.route("/new", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def create():
    organization = g.organization
    request_type = request.args.get("type")
    if request_type is None:
        return render_template(
            "/car_reservation/requests/choose_type.html", organization=organization
        )
    if request_type not in dict(models.car_reservations.RESERVATION_TYPES):
        abort(404)

    form = forms.car_reservation.reservation_form_for(request_type)

    user = current_user._get_current_object()
    member = models.OrganizationUserRole.objects(
        user=user, organization=organization, status="active"
    ).first()
    division = member.division if member else None
    if request.method == "GET":
        form.contact_name.data = user.get_name()
        form.contact_email.data = user.email

    submitted, short_notice_days, is_urgent = validate_submission(
        form, organization, request_type
    )
    if submitted and not flow.has_division_head(organization, division):
        flash("ฝ่ายของคุณยังไม่มีหัวหน้าฝ่าย กรุณาติดต่อผู้ดูแลระบบ", "danger")
    elif submitted:
        reservation = models.CarReservation(
            organization=organization,
            division=division,
            creator=user,
            updater=user,
            request_type=request_type,
            is_urgent=is_urgent,
            details=form.build_details(),
            **form.reservation_fields(),
            departure_datetime=datetime.datetime.combine(
                form.departure_date.data, form.departure_time.data
            ),
            return_datetime=datetime.datetime.combine(
                form.return_date.data, form.return_time.data
            ),
        )
        form.attach_files(reservation)
        flow.submit(reservation, user)
        utils.car_reservation_email.notify(reservation, "submitted")
        flash("ยื่นคำขอใช้รถเรียบร้อยแล้ว", "success")
        return redirect(
            url_for(
                "car_reservation.requests.detail",
                request_id=reservation.id,
                organization_id=organization.id,
            )
        )

    return render_template(
        "/car_reservation/requests/form.html",
        organization=organization,
        form=form,
        short_notice_days=short_notice_days,
        **short_notice_context(organization, request_type),
        request_type=request_type,
        request_type_label=dict(models.car_reservations.RESERVATION_TYPES)[
            request_type
        ],
    )


def object_id_or_none(value):
    return ObjectId(value) if ObjectId.is_valid(value) else None


def car_choices_for(organization):
    return [
        (str(car.id), car_choice_label(car))
        for car in flow.assignable_cars(organization)
    ]


def driver_choices_for(organization):
    return [
        (str(driver.id), driver.get_name())
        for driver in flow.assignable_drivers(organization)
    ]


def workload_label(row):
    """ชื่อ พขร. พร้อมภาระงาน (จำนวนงานย้อนหลัง) และป้ายมีงานชน ไว้เป็นตัวเลือกของช่อง พขร."""
    label = f"{row.driver.get_name()} · {row.in_hours_jobs + row.ot_jobs} งาน"
    if row.busy:
        label += " · มีงานชน"
    return label


def load_assignments(organization, chosen):
    """แปลงชุดที่ฟอร์มส่งมา (id เป็นสตริง) เป็น [{car, driver, is_overtime}] ที่ engine รับ

    รถต้องอยู่ใน org นี้ id ที่หาไม่เจอเป็น None ซึ่ง engine จะปฏิเสธเป็น "กรุณาเลือกรถและพนักงานขับรถ"
    """
    return [
        {
            "car": models.vehicles.Car.objects(
                id=item["car_id"], organization=organization
            ).first()
            if ObjectId.is_valid(item["car_id"])
            else None,
            "driver": models.User.objects(id=item["driver_id"]).first()
            if ObjectId.is_valid(item["driver_id"])
            else None,
            "is_overtime": item["is_overtime"],
        }
        for item in chosen
    ]


def notify_drivers(reservation):
    """แจ้ง พขร. ทุกคนของคำขอในระบบว่าได้รับมอบหมายงาน (driver_assigned ไม่มีอีเมล)"""
    utils.car_reservation_email.notify_in_app(reservation, "driver_assigned")


def requested_kind_of(reservation):
    """ประเภทรถที่ผู้ขอขอในใบขอ (ใบขอที่ไม่มีช่องนี้ เช่น งานแทรก คืน "")"""
    return getattr(reservation.details, "vehicle_kind", "") or ""


def warn_if_vehicle_type_differs(reservation):
    """flash เตือน (ไม่บล็อก) เมื่อรถที่จัดมีประเภทต่างจากที่ผู้ขอขอ รถที่ไม่ระบุประเภทไม่นับว่าต่าง"""
    kind = requested_kind_of(reservation)
    if not kind:
        return
    different = [
        f"{car.license_plate} ({car.vehicle_type})"
        for car in reservation.cars
        if car.vehicle_type and car.vehicle_type != kind
    ]
    if different:
        flash(
            f"รถที่จัดไม่ตรงกับประเภทที่ผู้ขอขอ (ขอ {kind}): {', '.join(different)}",
            "warning",
        )


def picker_window(form):
    """(เวลาออก, เวลากลับ) จากช่องวัน/เวลาของฟอร์ม ช่องไหนยังว่างหรือผิดรูปแบบคืน None ทั้งคู่"""
    parts = (
        form.departure_date.data,
        form.departure_time.data,
        form.return_date.data,
        form.return_time.data,
    )
    if any(part is None for part in parts):
        return None, None
    return (
        datetime.datetime.combine(parts[0], parts[1]),
        datetime.datetime.combine(parts[2], parts[3]),
    )


def picker_selection(values):
    """(selected, active_slot) ของตัวเลือกรถจาก id รถของแต่ละช่อง: ช่องที่กำลังเลือกคือช่องว่างช่องแรก"""
    selected = [value if ObjectId.is_valid(value or "") else "" for value in values]
    active = next((n for n, value in enumerate(selected, start=1) if not value), 1)
    return selected, active


URGENT_ASSIGNMENT_MISMATCH = (
    "กรุณาเลือกรถและพนักงานขับรถให้ครบ {count} คัน (ทุกคันต้องเลือกทั้งรถและพนักงานขับรถ)"
)


@module.route("/urgent", methods=["GET", "POST"])
@acl.organization_roles_required("dispatcher")
def create_urgent():
    """ผู้จัดรถสร้างคำขอใช้รถในประเทศเร่งด่วนแทนผู้ใช้รถจริง พร้อมจัดรถ/พขร. ในฟอร์มเดียว"""
    organization = g.organization
    user = current_user._get_current_object()
    if not flow.can_create_urgent(organization, user):
        abort(403)  # system admin ผ่านตัว decorator แต่ไม่ได้ถือ role ผู้จัดรถ

    request_type = flow.URGENT_REQUEST_TYPE
    if request.args.get("type", request_type) != request_type:
        abort(404)  # คำขอเร่งด่วนมีเฉพาะใบขอในประเทศ
    form = forms.car_reservation.UrgentDomesticReservationForm()
    forms.car_reservation.set_assignment_slots(
        form,
        forms.car_reservation.MAX_URGENT_ASSIGNMENTS,
        car_choices_for(organization),
        driver_choices_for(organization),
    )

    submitted, _, _ = validate_submission(
        form, organization, request_type, urgent_by_dispatcher=True
    )
    chosen, half_filled = forms.car_reservation.chosen_assignments(form)
    if submitted and (half_filled or len(chosen) != form.vehicle_count.data):
        # ผู้จัดรถเป็นผู้ขอเอง จึงต้องจัดครบตามจำนวนรถที่กรอกในฟอร์มเดียวกัน (ไม่มีทางลดจำนวน)
        form.vehicle_count.errors.append(URGENT_ASSIGNMENT_MISMATCH.format(count=form.vehicle_count.data))
        submitted = False
    if submitted:
        reservation = models.CarReservation(
            organization=organization,
            creator=user,
            updater=user,
            request_type=request_type,
            details=form.build_details(),
            **form.reservation_fields(),
            departure_datetime=datetime.datetime.combine(
                form.departure_date.data, form.departure_time.data
            ),
            return_datetime=datetime.datetime.combine(
                form.return_date.data, form.return_time.data
            ),
        )
        try:
            flow.submit_urgent(
                reservation,
                user,
                assignments=load_assignments(organization, chosen),
            )
        except flow.FlowError as error:
            flash_flow_error(error)
        else:
            utils.car_reservation_email.notify(reservation, "approved")
            notify_drivers(reservation)
            flash("สร้างคำขอเร่งด่วนเรียบร้อยแล้ว รอผู้อำนวยการกองกายภาพอนุมัติ", "success")
            warn_if_vehicle_type_differs(reservation)
            return redirect(
                url_for(
                    "car_reservation.requests.detail",
                    request_id=reservation.id,
                    organization_id=organization.id,
                )
            )

    # ตัวเลือกรถแบบตาราง: ครั้งแรกยังไม่มีเวลาจึงเป็นคำใบ้ ส่งกลับมาแก้หลังฟอร์มไม่ผ่านก็แสดงตารางตามเวลาที่กรอก
    selected, active_slot = picker_selection(entry.form.car.data for entry in form.assignments)
    timeline, picker_error = car_timeline.picker_or_hint(
        organization,
        *picker_window(form),
        kind=form.vehicle_kind.data or "",
        selected=selected,
        active_slot=active_slot,
    )
    return render_template(
        "/car_reservation/requests/form.html",
        organization=organization,
        form=form,
        short_notice_days=None,
        request_type=request_type,
        request_type_label="ขอใช้รถเร่งด่วน (ผู้จัดรถสร้างแทนผู้ใช้รถ)",
        urgent_by_dispatcher=True,
        car_picker={"timeline": timeline, "picker_error": picker_error},
    )


@module.route("/insert", methods=["GET", "POST"])
@acl.organization_roles_required("dispatcher")
def create_insert():
    """ผู้จัดรถเพิ่มงานแทรกให้ พขร. ที่มีงานอยู่แล้วในวันนั้น (active ทันที ไม่ต้องอนุมัติ)"""
    organization = g.organization
    user = current_user._get_current_object()
    if not flow.can_create_insert(organization, user):
        abort(403)  # system admin ผ่านตัว decorator แต่ไม่ได้ถือ role ผู้จัดรถ

    form = forms.car_reservation.InsertJobForm()
    form.car.choices = car_choices_for(organization)
    form.driver.choices = driver_choices_for(organization)

    if form.validate_on_submit():
        reservation = models.CarReservation(
            organization=organization,
            creator=user,
            updater=user,
            location=form.location.data,
            request_reason=form.request_reason.data,
            insert_scope=form.insert_scope.data,
            contact_name=form.contact_name.data.strip(),
            contact_email=form.contact_email.data.strip(),
            departure_datetime=datetime.datetime.combine(
                form.departure_date.data, form.departure_time.data
            ),
            return_datetime=datetime.datetime.combine(
                form.return_date.data, form.return_time.data
            ),
        )
        try:
            flow.submit_insert(
                reservation,
                user,
                car=models.vehicles.Car.objects(
                    id=object_id_or_none(form.car.data), organization=organization
                ).first(),
                driver=models.User.objects(
                    id=object_id_or_none(form.driver.data)
                ).first(),
                is_overtime=form.is_overtime.data,
            )
        except flow.FlowError as error:
            flash_flow_error(error)
        else:
            # งานแทรก active ทันที: แจ้ง พขร. เหมือนคำขอที่อนุมัติครบ (อีเมลถึงผู้ขอและ พขร. + แจ้งเตือนในระบบ)
            utils.car_reservation_email.notify(reservation, "active")
            notify_drivers(reservation)
            flash("เพิ่มงานแทรกเรียบร้อยแล้ว", "success")
            return redirect(
                url_for(
                    "car_reservation.requests.detail",
                    request_id=reservation.id,
                    organization_id=organization.id,
                )
            )

    selected, active_slot = picker_selection([form.car.data])
    timeline, picker_error = car_timeline.picker_or_hint(
        organization,
        *picker_window(form),
        driver_id=object_id_or_none(form.driver.data),
        selected=selected,
        active_slot=active_slot,
    )
    return render_template(
        "/car_reservation/requests/insert.html",
        organization=organization,
        form=form,
        car_picker={"timeline": timeline, "picker_error": picker_error},
    )


def stepper(reservation):
    """รายการขั้นของเส้นทางพร้อมสถานะ done/current/waiting/denied"""
    decisions = {
        approval.step_key: approval for approval in reservation.step_approvals
    }
    steps = []
    for index, key in enumerate(reservation.route_snapshot):
        approval = decisions.get(key)
        if approval and approval.decision == "denied":
            state = "denied"
        elif approval:
            state = "done"
        elif index == reservation.current_step and reservation.status == "pending":
            state = "current"
        else:
            state = "waiting"
        steps.append({"key": key, "label": flow.step_label(key), "state": state})
    return steps


def assignment_cards(reservation, user):
    """ข้อมูลที่การ์ดของแต่ละชุด (รถ + พขร.) ในหน้ารายละเอียดต้องใช้ ตามลำดับชุด"""
    return [
        {
            "assignment": assignment,
            "index": index,
            "can_set_overtime": flow.can_set_overtime(reservation, user, assignment),
            "overtime_form": forms.car_reservation.OvertimeForm(
                is_overtime=assignment.is_overtime
            ),
            "close_status": assignment.close_confirmation_status(),
            "can_confirm_close": flow.can_confirm_close(reservation, user, assignment),
            "close_form": forms.car_reservation.CloseConfirmationForm(),
        }
        for index, assignment in enumerate(reservation.assignments, start=1)
    ]


@module.route("/<request_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def detail(request_id):
    reservation = get_request_or_404(request_id)
    user = current_user._get_current_object()
    current_key = flow.current_step_key(reservation)
    required_count = models.car_reservations.required_vehicle_count(reservation)
    car_picker = None
    if current_key == "dispatcher":
        form = forms.car_reservation.DispatchDecisionForm()
        workload = flow.driver_workload(
            g.organization,
            now=datetime.datetime.now(),
            window_start=reservation.departure_datetime,
            window_end=reservation.return_datetime or reservation.departure_datetime,
        )
        forms.car_reservation.set_assignment_slots(
            form,
            required_count,
            car_choices_for(g.organization),
            [(str(row.driver.id), workload_label(row)) for row in workload],
        )
        if flow.can_act(reservation, user):
            # ตัวเลือกรถแบบตาราง: ช่วงของคำขอคงที่ ไม่นับคำขอนี้เองว่าชน
            picker_timeline, picker_error = car_timeline.picker_or_hint(
                g.organization,
                reservation.departure_datetime,
                reservation.return_datetime,
                kind=requested_kind_of(reservation),
                exclude_id=reservation.id,
            )
            car_picker = {"timeline": picker_timeline, "picker_error": picker_error}
    else:
        form = forms.car_reservation.ApprovalDecisionForm()
        workload = []
    form.step.data = reservation.current_step
    return render_template(
        "/car_reservation/requests/detail.html",
        organization=g.organization,
        reservation=reservation,
        steps=stepper(reservation),
        current_step_label=flow.step_label(current_key) if current_key else "",
        can_act=flow.can_act(reservation, user),
        can_view_mileage_photos=flow.can_view_mileage_photos(reservation, user),
        asks_extra_travelers=flow.asks_extra_travelers(reservation),
        can_print_paper=flow.can_print_paper(reservation, user),
        can_edit=flow.can_edit(reservation, user),
        can_cancel=flow.can_cancel(reservation, user),
        can_confirm_cancel=flow.can_confirm_cancel(reservation, user),
        cancel_form=forms.car_reservation.CancelRequestForm(),
        assignment_cards=assignment_cards(reservation, user),
        required_vehicle_count=required_count,
        requested_vehicle_kind=requested_kind_of(reservation),
        off_campus=any(a.closed_off_campus for a in reservation.assignments),
        form=form,
        workload=workload,
        **({"car_picker": car_picker} if car_picker else {}),
        deny_form=forms.car_reservation.DenyDecisionForm(),
        close_confirmation_days=models.car_reservations.CLOSE_CONFIRMATION_DAYS,
        finance_documents=finance.documents_for_reservation(reservation)
        if finance.can_issue(g.organization, user)
        else [],
        finance_saved=finance.saved_docs(reservation),
    )


@module.route("/<request_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def edit(request_id):
    """ผู้ขอแก้ไขคำขอตัวเองได้จนกว่าผู้บังคับบัญชาจะตัดสิน (ประเภทใบขอเปลี่ยนไม่ได้)"""
    organization = g.organization
    reservation = get_request_or_404(request_id)
    user = current_user._get_current_object()
    if not flow.can_edit(reservation, user):
        abort(403)

    request_type = reservation.request_type
    form = forms.car_reservation.reservation_form_for(request_type)
    form.allow_existing_attachments()
    if request.method == "GET":
        form.prefill(reservation)

    submitted, short_notice_days, is_urgent = validate_submission(
        form, organization, request_type
    )
    if submitted:
        before = form.describe(reservation)
        for name, value in {
            **form.reservation_fields(),
            "details": form.build_details(),
            "is_urgent": is_urgent,
            "departure_datetime": datetime.datetime.combine(
                form.departure_date.data, form.departure_time.data
            ),
            "return_datetime": datetime.datetime.combine(
                form.return_date.data, form.return_time.data
            ),
        }.items():
            setattr(reservation, name, value)
        form.attach_files(reservation)
        flow.edit(
            reservation,
            user,
            changes=flow.diff_fields(
                before, form.describe(reservation), form.change_labels()
            ),
        )
        flash("แก้ไขคำขอใช้รถเรียบร้อยแล้ว", "success")
        return redirect(
            url_for(
                "car_reservation.requests.detail",
                request_id=reservation.id,
                organization_id=organization.id,
            )
        )

    return render_template(
        "/car_reservation/requests/form.html",
        organization=organization,
        form=form,
        short_notice_days=short_notice_days,
        **short_notice_context(organization, request_type),
        request_type=request_type,
        request_type_label=dict(models.car_reservations.RESERVATION_TYPES)[
            request_type
        ],
        reservation=reservation,
    )


@module.route("/<request_id>/project_file")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def project_file(request_id):
    """ดาวน์โหลดเอกสารโครงการของใบขอไปต่างประเทศ (ผู้ดูคำขอนี้ได้ ดาวน์โหลดได้)"""
    reservation = get_request_or_404(request_id)
    if not reservation.project_file:
        abort(404)
    return utils.uploaded_files.send_uploaded_file(
        reservation.project_file,
        download_name=reservation.project_file.filename or "project_file",
    )


def get_assignment_or_404(reservation, assignment_id):
    assignment = reservation.get_assignment(assignment_id)
    if assignment is None:
        abort(404)
    return assignment


@module.route("/<request_id>/mileage_photo/<assignment_id>/<side>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def mileage_photo(request_id, assignment_id, side):
    """รูปเลขไมล์ที่ พขร. ของชุดนี้ถ่ายตอนปิดงาน (side = in ขากลับ; out ก่อนออก มีเฉพาะงานเก่า)"""
    reservation = get_request_or_404(request_id)
    assignment = get_assignment_or_404(reservation, assignment_id)
    if not flow.can_view_mileage_photos(
        reservation, current_user._get_current_object()
    ):
        abort(403)
    photo = {
        "out": assignment.mileage_photo_out,
        "in": assignment.mileage_photo_in,
    }.get(side)
    if not photo:
        abort(404)
    return utils.uploaded_files.send_uploaded_file(
        photo, download_name=photo.filename or f"mileage_{side}"
    )


@module.route("/<request_id>/paper", defaults={"assignment_id": None})
@module.route("/<request_id>/paper/<assignment_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def paper(request_id, assignment_id):
    """ใบขอใช้รถ (PDF) ตามแบบฟอร์มทางการของประเภทใบขอ หนึ่งใบต่อชุด (ไม่ระบุชุด = ชุดแรก)"""
    reservation = get_request_or_404(request_id)
    if not flow.can_print_paper(reservation, current_user._get_current_object()):
        abort(403)
    if assignment_id is None:
        assignment = reservation.first_assignment
    else:
        assignment = get_assignment_or_404(reservation, assignment_id)
    pdf = utils.car_reservation_paper.render_pdf(reservation, assignment)
    filename = f"car_request_{reservation.id}"
    if len(reservation.assignments) > 1 and assignment is not None:
        # หนึ่งใบต่อชุด: ชื่อไฟล์บอกลำดับชุด (คำขอคันเดียวใช้ชื่อเดิม)
        filename += f"_{reservation.assignments.index(assignment) + 1}"
    return send_file(
        io.BytesIO(pdf),
        mimetype="application/pdf",
        download_name=f"{filename}.pdf",
    )


def inbox_url_if_requested(form):
    """URL กล่องรออนุมัติของ org นี้ ถ้าฟอร์มส่ง next มาตรงกับมันเป๊ะ (whitelist เดียว ไม่รับ URL อื่น)"""
    inbox_url = url_for("car_reservation.requests.inbox", organization_id=g.organization.id)
    return inbox_url if form.next.data == inbox_url else None


def already_handled(reservation):
    flash(flow.ALREADY_HANDLED, "warning")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/approve", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def approve(request_id):
    reservation = get_request_or_404(request_id)
    dispatching = flow.current_step_key(reservation) == "dispatcher"
    form = (
        forms.car_reservation.DispatchDecisionForm()
        if dispatching
        else forms.car_reservation.ApprovalDecisionForm()
    )
    if not form.validate_on_submit():
        abort(400)
    if form.step.data and form.step.data != str(reservation.current_step):
        return already_handled(reservation)

    user = current_user._get_current_object()
    extra = {}
    required_before = models.car_reservations.required_vehicle_count(reservation)
    if dispatching:
        chosen, half_filled = forms.car_reservation.chosen_assignments(form)
        if half_filled:
            # ชุดที่เลือกรถหรือ พขร. อย่างเดียว: ผู้ที่ไม่ใช่ผู้จัดรถไม่ควรรู้ว่าฟอร์มนี้ตรวจอะไร
            if not flow.can_act(reservation, user):
                abort(403)
            flash(flow.CAR_AND_DRIVER_REQUIRED, "danger")
            return redirect(
                url_for(
                    "car_reservation.requests.detail",
                    request_id=reservation.id,
                    organization_id=g.organization.id,
                )
            )
        extra = {
            "assignments": load_assignments(g.organization, chosen),
            "reduce_reason": (form.reduce_reason.data or "").strip(),
            "extra_travelers": (form.extra_travelers.data or "").strip(),
        }
    try:
        flow.approve(reservation, user, comment=form.comment.data or "", **extra)
    except flow.ConcurrentChangeError:
        return already_handled(reservation)
    except flow.FlowError as error:
        if not dispatching or not flow.can_act(reservation, user):
            abort(403)
        flash_flow_error(error)
        return redirect(
            url_for(
                "car_reservation.requests.detail",
                request_id=reservation.id,
                organization_id=g.organization.id,
            )
        )

    utils.car_reservation_email.notify(
        reservation, "active" if reservation.status == "active" else "approved"
    )
    if dispatching:
        notify_drivers(reservation)
        if models.car_reservations.required_vehicle_count(reservation) < required_before:
            # จัดรถน้อยกว่าที่ขอ (flow ลงประวัติ vehicle_count_reduced แล้ว): แจ้งผู้ขอพร้อมเหตุผล
            utils.car_reservation_email.notify(reservation, "vehicle_count_reduced")
    flash("บันทึกการอนุมัติเรียบร้อยแล้ว", "success")
    if dispatching:
        warn_if_vehicle_type_differs(reservation)
    return redirect(
        inbox_url_if_requested(form)
        or url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/deny", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def deny(request_id):
    reservation = get_request_or_404(request_id)
    form = forms.car_reservation.DenyDecisionForm()
    redirect_to_detail = redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )
    if not flow.can_act(reservation, current_user._get_current_object()):
        abort(403)
    if not form.validate_on_submit():
        flash("กรุณาระบุเหตุผลที่ไม่อนุมัติ", "danger")
        return redirect_to_detail

    try:
        flow.deny(
            reservation,
            current_user._get_current_object(),
            comment=form.comment.data,
        )
    except flow.ConcurrentChangeError:
        return already_handled(reservation)
    utils.car_reservation_email.notify(reservation, "denied")
    flash("บันทึกการไม่อนุมัติเรียบร้อยแล้ว", "success")
    inbox_url = inbox_url_if_requested(form)
    return redirect(inbox_url) if inbox_url else redirect_to_detail


@module.route("/<request_id>/overtime/<assignment_id>", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def overtime(request_id, assignment_id):
    reservation = get_request_or_404(request_id)
    assignment = get_assignment_or_404(reservation, assignment_id)
    form = forms.car_reservation.OvertimeForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        flow.set_overtime(
            reservation,
            current_user._get_current_object(),
            assignment,
            form.is_overtime.data,
        )
    except flow.ConcurrentChangeError:
        return already_handled(reservation)
    except flow.FlowError:
        abort(403)
    flash("บันทึกสถานะงานนอกเวลาเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/cancel", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def cancel(request_id):
    reservation = get_request_or_404(request_id)
    form = forms.car_reservation.CancelRequestForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        flow.cancel(
            reservation,
            current_user._get_current_object(),
            reason=form.reason.data or "",
        )
    except flow.ConcurrentChangeError:
        return already_handled(reservation)
    except flow.FlowError:
        abort(403)
    utils.car_reservation_email.notify(reservation, reservation.status)
    flash("ยกเลิกคำขอเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/cancel/confirm", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def confirm_cancel(request_id):
    reservation = get_request_or_404(request_id)
    if not forms.car_reservation.CancelRequestForm().validate_on_submit():
        abort(400)
    try:
        flow.confirm_cancel(reservation, current_user._get_current_object())
    except flow.ConcurrentChangeError:
        return already_handled(reservation)
    except flow.FlowError:
        abort(403)
    utils.car_reservation_email.notify(reservation, "cancelled")
    flash("รับทราบการยกเลิกเรียบร้อยแล้ว", "success")
    return redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )


@module.route("/<request_id>/close_confirmation/<assignment_id>", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def close_confirmation(request_id, assignment_id):
    """ผู้ขอยืนยันเวลาเริ่ม/ปิดงานที่ พขร. ของชุดนี้บันทึก (ตอบได้ครั้งเดียวต่อชุด)"""
    reservation = get_request_or_404(request_id)
    assignment = get_assignment_or_404(reservation, assignment_id)
    user = current_user._get_current_object()
    if not flow.can_confirm_close(reservation, user, assignment):
        abort(403)
    form = forms.car_reservation.CloseConfirmationForm()
    if not form.validate_on_submit():
        abort(400)

    correct = form.decision.data == "correct"
    reported_end = (
        datetime.datetime.combine(form.actual_end_date.data, form.actual_end_time.data)
        if form.actual_end_date.data and form.actual_end_time.data
        else None
    )
    redirect_to_detail = redirect(
        url_for(
            "car_reservation.requests.detail",
            request_id=reservation.id,
            organization_id=g.organization.id,
        )
    )
    try:
        flow.confirm_close(
            reservation,
            user,
            assignment,
            correct=correct,
            reported_end=reported_end,
            note=form.note.data or "",
        )
    except flow.FlowError as error:
        flash(str(error), "danger")
        return redirect_to_detail
    if not correct:
        utils.car_reservation_email.notify(reservation, "close_disputed")
    flash("บันทึกการยืนยันเวลาปิดงานเรียบร้อยแล้ว", "success")
    return redirect_to_detail


def finance_filename(reservation, doc):
    return f"car-finance-{doc}-{reservation.id}.pdf"


@module.route("/<request_id>/finance/<doc>", methods=["GET", "POST"])
@acl.organization_roles_required(*finance.FINANCE_ROLES)
def finance_document(request_id, doc):
    reservation = get_request_or_404(request_id)
    if doc not in finance.documents_for(reservation.request_type):
        abort(404)
    if reservation.status != "completed":
        abort(403)
    saved = finance.saved_document(reservation, doc)
    form = forms.car_reservation_finance.FinanceForm(obj=saved)
    if form.validate_on_submit():
        saved = finance.save_document(
            reservation, doc, form, current_user._get_current_object()
        )
        if request.form.get("action") != "save":
            pdf = finance.render(doc, reservation, finance.FinanceData.from_form(form))
            return send_file(
                io.BytesIO(pdf),
                mimetype="application/pdf",
                as_attachment=True,
                download_name=finance_filename(reservation, doc),
            )
        flash(f"บันทึก{finance.DOCUMENT_LABELS[doc]}แล้ว", "success")
        return redirect(
            url_for(
                "car_reservation.requests.finance_document",
                request_id=reservation.id,
                doc=doc,
                organization_id=g.organization.id,
            )
        )
    return render_template(
        "/car_reservation/requests/finance_form.html",
        organization=g.organization,
        reservation=reservation,
        doc=doc,
        doc_label=finance.DOCUMENT_LABELS[doc],
        form=form,
        saved=saved,
    )
