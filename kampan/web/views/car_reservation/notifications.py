"""กระดิ่งแจ้งเตือนของระบบจองรถ: จำนวนที่ยังไม่อ่าน รายการล่าสุด และหน้าดูทั้งหมด"""

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask_login import current_user

from kampan import utils
from kampan.web import acl
from kampan.web.views.car_reservation.calendar import ANY_ORGANIZATION_ROLE

module = Blueprint("notifications", __name__, url_prefix="/notifications")

MENU_SIZE = 8
PAGE_SIZE = 20


def my_inbox():
    return utils.notifications.inbox(current_user._get_current_object(), g.organization)


@module.route("")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    page = max(request.args.get("page", 1, type=int), 1)
    items = my_inbox()
    total = items.count()
    return render_template(
        "/car_reservation/notifications/index.html",
        organization=g.organization,
        notifications=items.skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE),
        page=page,
        has_next=page * PAGE_SIZE < total,
    )


@module.route("/badge")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def badge():
    return render_template(
        "/car_reservation/notifications/_badge.html",
        organization=g.organization,
        unread_count=my_inbox().filter(read_at=None).count(),
    )


@module.route("/menu")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def menu():
    return render_template(
        "/car_reservation/notifications/_menu.html",
        organization=g.organization,
        notifications=my_inbox().limit(MENU_SIZE),
    )


@module.route("/read-all", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def read_all():
    utils.notifications.mark_all_read(current_user._get_current_object(), g.organization)
    return redirect(
        url_for("car_reservation.notifications.index", organization_id=g.organization.id)
    )


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
