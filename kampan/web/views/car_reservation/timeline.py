"""ตารางรถ: ผู้จัดรถเห็นภาพรวมว่ารถแต่ละคันว่างหรือไม่ว่างช่วงไหน (แถว = รถ, คอลัมน์ = วัน, แท่ง = งาน)

ข้อมูลทั้งหมดมาจาก `utils.car_timeline` (data builder ที่ไม่ผูกกับ request) หน้านี้ทำหน้าที่อ่าน query string
ตรวจสิทธิ์ และ render เท่านั้น ส่วนตารางอยู่ใน partial `timeline/_grid.html` ซึ่งใช้ซ้ำกับตัวเลือกรถในฟอร์มจัดรถได้
"""

import datetime

from flask import Blueprint, abort, g, render_template, request, url_for
from flask_login import current_user

from kampan import utils
from kampan.web import acl, forms

module = Blueprint("timeline", __name__, url_prefix="/timeline")

flow = utils.car_reservation_flow
car_timeline = utils.car_timeline

# ป้ายของตัวเลือกจำนวนวัน
DAY_LABELS = {1: "1 วัน", 7: "7 วัน", 14: "14 วัน", 30: "1 เดือน"}
# สถานะที่ถือว่าเป็น "ซ่อนไว้ เปิดดูได้ด้วย filter" ใช้แสดงคำใบ้ข้างช่องสถานะ
HIDDEN_BY_DEFAULT = ("cancelled", "denied")


def is_partial_request():
    """htmx ขอเฉพาะตาราง (ยกเว้นตอน htmx ดึงหน้าเต็มมาคืนประวัติ back/forward ที่มี HX-History-Restore-Request)"""
    return bool(request.headers.get("HX-Request")) and not request.headers.get(
        "HX-History-Restore-Request"
    )


def filter_form(organization, filters):
    """ฟอร์มตัวกรองที่กรอกค่าจาก filter ที่ผ่านการตรวจแล้ว พร้อมตัวเลือก พขร. ของ org"""
    form = forms.car_reservation.TimelineFilterForm(
        formdata=None,
        data={
            "organization_id": str(organization.id),
            "vehicle_type": filters.vehicle_types,
            "q": filters.q,
            "driver": filters.driver_id,
            "status": filters.statuses,
            "free_from": filters.free_from,
            "free_to": filters.free_to,
        },
    )
    form.driver.choices = [("", "พนักงานขับรถทุกคน")] + sorted(
        ((str(driver.id), driver.get_name()) for driver in flow.assignable_drivers(organization)),
        key=lambda choice: choice[1],
    )
    return form


@module.route("/")
@acl.organization_roles_required(*flow.TIMELINE_ROLES)
def index():
    organization = g.organization
    # system admin ผ่านตัว decorator แต่ต้องถือ role ผู้จัดรถ/admin ขององค์กรนี้ด้วยจึงดูตารางรถรวมได้
    if not flow.can_view_timeline(organization, current_user._get_current_object()):
        abort(403)

    now = datetime.datetime.now()
    today = now.date()
    start_date, days, filters = car_timeline.parse_query(request.args, today=today)
    form = filter_form(organization, filters)
    # พขร. ที่ไม่ใช่สมาชิกของ org นี้ไม่กรอง (ไม่แสดงเป็นตัวเลือก และไม่ทำให้ตารางว่างเปล่าแบบงง ๆ)
    if filters.driver_id and filters.driver_id not in {value for value, _ in form.driver.choices}:
        filters.driver_id = ""
        form.driver.data = ""

    timeline = car_timeline.build_timeline(organization, start_date, days, filters, now=now)

    def args_for(start=start_date, days=days):
        return car_timeline.query_args(start, days, filters, today=today)

    shift = datetime.timedelta(days=timeline.day_count)
    links = {
        "prev": args_for(start=start_date - shift),
        "next": args_for(start=start_date + shift),
        "today": args_for(start=today),
        "days": [
            (value, DAY_LABELS[value], args_for(days=value))
            for value in car_timeline.DAY_CHOICES
        ],
        # ล้างตัวกรองทั้งหมด แต่คงช่วงวันที่ดูอยู่
        "reset": car_timeline.query_args(
            start_date, days, car_timeline.TimelineFilters(), today=today
        ),
        # ซ่อนไว้ในฟอร์มตัวกรอง (ว่าง = วันนี้) เพื่อให้กรองแล้วอยู่ช่วงวันเดิม
        "start": start_date.isoformat() if start_date != today else "",
    }
    filtered = bool(
        filters.vehicle_types
        or filters.q
        or filters.driver_id
        or filters.free_window
        or sorted(filters.statuses) != sorted(car_timeline.DEFAULT_STATUSES)
    )
    context = {
        "organization": organization,
        "timeline": timeline,
        "form": form,
        "links": links,
        "hidden_by_default": HIDDEN_BY_DEFAULT,
        "filtered": filtered,
        "reset_href": url_for(
            "car_reservation.timeline.index",
            organization_id=organization.id,
            **links["reset"],
        ),
    }
    if is_partial_request():
        # ปุ่มนำทาง/ช่วงวันที่อยู่นอกตาราง: ส่งไปแทนที่ด้วย hx-swap-oob พร้อมกัน
        return render_template(
            "/car_reservation/timeline/_grid.html", nav_oob=True, **context
        )
    return render_template("/car_reservation/timeline/index.html", **context)
