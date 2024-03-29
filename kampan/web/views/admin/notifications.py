from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination

from kampan.web import forms, acl
from kampan import models

module = Blueprint("notifications", __name__, url_prefix="/notifications")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    notifications = []

    items = models.Item.objects(status="active")
    for item in items:
        if item.minimum > item.get_items_quantity():
            notifications.append(item)
    page = request.args.get("page", default=1, type=int)
    paginated_notifications = Pagination(notifications, page=page, per_page=30)
    return render_template(
        "/admin/notifications/index.html",
        paginated_notifications=paginated_notifications,
        notifications=notifications,
    )


@module.route("/<item_id>/set_status")
@login_required
@acl.roles_required("admin")
def set_status(item_id):
    item = models.Item.objects(id=item_id).first()
    item.notification_status = False
    item.save()

    return redirect(url_for("admin.notifications.index"))
