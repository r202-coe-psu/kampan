from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from io import BytesIO
from kampan.web import forms, acl
from kampan import models

import datetime

module = Blueprint("requisitions", __name__, url_prefix="/requisitions")


@module.route("", methods=["GET", "POST"])
@login_required
@acl.organization_roles_required("admin")
def index():
    organization = current_user.user_setting.current_organization
    today = datetime.datetime.now()
    tor_year = getattr(current_user.user_setting, "tor_year", None)
    next_7 = today + datetime.timedelta(days=7)

    query = {}
    if tor_year:
        query["tor_year"] = tor_year

    procurements = models.Procurement.objects(
        **query, end_date__gte=today, end_date__lte=next_7
    ).order_by("end_date")
    return render_template(
        "procurement/requisitions/index.html",
        procurements=procurements,
        organization=organization,
    )
