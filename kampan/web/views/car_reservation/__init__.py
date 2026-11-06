from flask import Blueprint, g
from flask_login import current_user

from kampan import utils

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
