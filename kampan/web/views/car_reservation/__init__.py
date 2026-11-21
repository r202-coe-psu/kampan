import datetime

from flask import Blueprint, g, request
from flask_login import current_user

from kampan import models, utils

from . import feedback as feedback_view

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
        "inbox_count": flow.inbox_count(organization, user),
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
def inject_can_request():
    """เห็นเมนูคำขอของฉัน/ยื่นคำขอไหม: ทุกคนยกเว้นพนักงานขับรถล้วน (ซึ่งถูกพาไปหน้ารายการงานแทน)"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"can_request": False}
    return {
        "can_request": not utils.car_reservation_flow.is_driver_only(
            organization, current_user._get_current_object()
        )
    }


@module.context_processor
def inject_can_view_stats():
    """เห็นเมนูแดชบอร์ดพนักงานขับรถไหม: ผู้จัดรถ ผู้บริหาร และ admin"""
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
def inject_can_create_urgent():
    """เห็นเมนูขอใช้รถเร่งด่วนไหม: เฉพาะผู้จัดรถ (role dispatcher) ของ org ที่ดูอยู่"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"can_create_urgent": False}
    return {
        "can_create_urgent": utils.car_reservation_flow.can_create_urgent(
            organization, current_user._get_current_object()
        )
    }


@module.context_processor
def inject_can_create_insert():
    """เห็นเมนูเพิ่มงานแทรกไหม: เฉพาะผู้จัดรถ (role dispatcher) ของ org ที่ดูอยู่"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"can_create_insert": False}
    return {
        "can_create_insert": utils.car_reservation_flow.can_create_insert(
            organization, current_user._get_current_object()
        )
    }


@module.context_processor
def inject_feedback_link():
    """ลิงก์ประเมินของใบขอ (ใช้กับ partial feedback/_link.html ในหน้ารายละเอียดและคำขอของฉัน)"""
    if not current_user.is_authenticated:
        return {}
    user = current_user._get_current_object()
    return {
        "feedback_link": lambda reservation: feedback_view.get_requester_feedback_url(
            reservation, user
        ),
        # หนึ่งลิงก์ต่อรถหนึ่งคัน (คำขอหลายคันประเมินแยกทีละคัน)
        "feedback_links": lambda reservation: feedback_view.get_requester_feedback_links(
            reservation, user
        ),
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
