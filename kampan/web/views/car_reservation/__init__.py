import datetime

from flask import Blueprint, g, request
from flask_login import current_user

from kampan import models, utils

module = Blueprint("car_reservation", __name__, url_prefix="/car_reservation")


@module.context_processor
def inject_inbox():
    """ข้อมูลเมนูรายการรออนุมัติของ sidebar: เห็นเมนูไหม (ผู้อนุมัติของ org) และจำนวนที่รออยู่"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"inbox_count": 0, "is_approver": False}
    user = current_user._get_current_object()
    flow = utils.car_reservation_flow
    return {
        "inbox_count": len(flow.inbox_for(organization, user)),
        "is_approver": flow.is_approver(organization, user),
    }


@module.context_processor
def inject_is_driver():
    """เห็นเมนูรายการงานไหม: เฉพาะพนักงานขับรถ (role driver) ของ org ที่ดูอยู่"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"is_driver": False}
    return {
        "is_driver": utils.car_reservation_flow.has_role(
            organization, current_user._get_current_object(), "driver"
        )
    }


@module.context_processor
def inject_can_view_stats():
    """เห็นเมนูภาระงานพนักงานขับรถไหม: ผู้จัดรถ ผู้บริหาร และ admin"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"can_view_stats": False}
    user = current_user._get_current_object()
    return {
        "can_view_stats": "admin" in user.roles
        or any(
            utils.car_reservation_flow.has_role(organization, user, role)
            for role in utils.car_reservation_flow.STATS_ROLES
        )
    }


@module.context_processor
def inject_feedback_state():
    """สถานะแบบประเมินของใบขอ (ใช้กับ partial feedback/_link.html ในหน้ารายละเอียดและคำขอของฉัน)"""
    if not current_user.is_authenticated:
        return {}
    user = current_user._get_current_object()
    return {
        "feedback_state": lambda reservation: utils.car_reservation_feedback.state_for(
            reservation, user
        )
    }


# ไอคอนและคำแนะนำสั้น ๆ ของใบขอแต่ละประเภท ใช้ในหน้าและ modal เลือกประเภท (ชื่อใบขอมาจาก RESERVATION_TYPES)
REQUEST_TYPE_CARDS = {
    "domestic": ("ph-map-trifold", "ยื่นล่วงหน้า 3–30 วันทำการ"),
    "airport": ("ph-airplane-tilt", "สำหรับผู้บริหารและบุคลากรในสำนักงานอธิการบดี"),
    "welfare": ("ph-heart", "สำหรับตนเองและญาติสายตรง"),
    "abroad": ("ph-globe-hemisphere-east", "ยื่นล่วงหน้าอย่างน้อย 10 วันทำการ"),
}


@module.context_processor
def inject_request_types():
    """ตัวเลือกประเภทใบขอของ modal ยื่นคำขอ และวันที่ (?date=YYYY-MM-DD) ที่ส่งต่อไปหน้าฟอร์ม"""
    cards = [
        {
            "key": key,
            "title": title,
            "icon": REQUEST_TYPE_CARDS[key][0],
            "hint": REQUEST_TYPE_CARDS[key][1],
        }
        for key, title in models.car_reservations.RESERVATION_TYPES
    ]
    try:
        date = datetime.date.fromisoformat(request.args.get("date", "")).isoformat()
    except ValueError:
        date = None
    return {"request_type_cards": cards, "new_request_date": date}
