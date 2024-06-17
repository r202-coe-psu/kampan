from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
import mongoengine as me
from flask_mongoengine import Pagination

import datetime

module = Blueprint("notifications", __name__, url_prefix="/notifications")
subviews = []


@module.route("/")
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    notifications = []

    items = models.Item.objects(
        status="active", notification_status=True, organization=organization
    )
    for item in items:
        if item.minimum > item.get_amount_items():
            notifications.append(item)
    page = request.args.get("page", default=1, type=int)
    paginated_notifications = Pagination(notifications, page=page, per_page=30)
    return render_template(
        "/notifications/index.html",
        paginated_notifications=paginated_notifications,
        notifications=notifications,
        organization=organization,
    )


@module.route("/<item_id>/set_status")
@acl.organization_roles_required("admin", "endorser", "staff")
def set_status(item_id):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects(id=item_id).first()
    if item.notification_status:
        item.notification_status = False
    else:
        item.notification_status = True

    item.save()

    return redirect(
        url_for("items.detail", organization_id=organization_id, item_id=item_id)
    )
