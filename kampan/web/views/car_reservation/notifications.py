"""เมนูการแจ้งเตือนของระบบจองรถ: จำนวนที่ยังไม่อ่านบน sidebar และหน้ารายการแบ่งแท็บ"""

import datetime
import itertools

from flask import Blueprint, abort, g, redirect, render_template, request, url_for
from flask_login import current_user

from kampan import utils
from kampan.web import acl
from kampan.web.views.car_reservation.calendar import ANY_ORGANIZATION_ROLE

module = Blueprint("notifications", __name__, url_prefix="/notifications")

PAGE_SIZE = 20
TABS = ("all", "unread")


def my_inbox():
    return utils.notifications.inbox(current_user._get_current_object(), g.organization)


def day_label(day, today):
    if day == today:
        return "วันนี้"
    if day == today - datetime.timedelta(days=1):
        return "เมื่อวาน"
    return day.strftime("%d/%m/") + str(day.year + 543)


def group_by_day(notifications):
    """[(ป้ายวัน, [แจ้งเตือน...]), ...] เรียงตาม inbox อยู่แล้ว (ใหม่ก่อน)"""
    today = datetime.date.today()
    return [
        (day_label(day, today), list(items))
        for day, items in itertools.groupby(
            notifications, key=lambda n: n.created_date.date()
        )
    ]


@module.route("")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    tab = request.args.get("tab", "all")
    if tab not in TABS:
        tab = "all"
    page = max(request.args.get("page", 1, type=int), 1)

    items = my_inbox()
    unread_count = items.clone().filter(read_at=None).count()
    if tab == "unread":
        items = items.filter(read_at=None)
    total = items.count()
    return render_template(
        "/car_reservation/notifications/index.html",
        organization=g.organization,
        groups=group_by_day(items.skip((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)),
        tab=tab,
        unread_count=unread_count,
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


@module.route("/read-all", methods=["POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def read_all():
    utils.notifications.mark_all_read(current_user._get_current_object(), g.organization)
    return redirect(
        url_for(
            "car_reservation.notifications.index",
            organization_id=g.organization.id,
            tab=request.args.get("tab", "all"),
        )
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
