from flask import Blueprint, g
from flask_login import current_user

from kampan import utils

module = Blueprint("car_reservation", __name__, url_prefix="/car_reservation")


@module.context_processor
def inject_inbox_count():
    """จำนวนคำขอที่รอผู้ใช้อนุมัติ ใช้แสดงป้ายตัวเลขที่ sidebar"""
    organization = getattr(g, "organization", None)
    if organization is None or not current_user.is_authenticated:
        return {"inbox_count": 0}
    waiting = utils.car_reservation_flow.inbox_for(
        organization, current_user._get_current_object()
    )
    return {"inbox_count": len(waiting)}
