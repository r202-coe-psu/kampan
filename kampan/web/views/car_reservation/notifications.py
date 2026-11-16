"""กระดิ่งแจ้งเตือนของระบบจองรถ: จำนวนที่ยังไม่อ่าน รายการล่าสุด และหน้าดูทั้งหมด"""

from flask import Blueprint, abort, g, redirect, url_for
from flask_login import current_user

from kampan import utils
from kampan.web import acl
from kampan.web.views.car_reservation.calendar import ANY_ORGANIZATION_ROLE

module = Blueprint("notifications", __name__, url_prefix="/notifications")


@module.route("/<notification_id>/open")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def open(notification_id):
    notification = utils.notifications.find(
        current_user._get_current_object(), g.organization, notification_id
    )
    if notification is None:
        abort(404)
    utils.notifications.mark_read(notification)
    return redirect(
        notification.url
        or url_for("car_reservation.notifications.index", organization_id=g.organization.id)
    )
