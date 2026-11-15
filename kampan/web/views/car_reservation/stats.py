"""สถิติของระบบจองรถ: dashboard ภาระงานพนักงานขับรถสำหรับผู้จัดรถและผู้บริหาร"""

import datetime

from flask import Blueprint, g, render_template, request

from kampan import utils
from kampan.web import acl

module = Blueprint("stats", __name__, url_prefix="/stats")

flow = utils.car_reservation_flow
feedback = utils.car_reservation_feedback

@module.route("/drivers")
@acl.organization_roles_required(*flow.STATS_ROLES)
def drivers():
    period = request.args.get("period")
    days = {key: days for key, _, days in feedback.PERIODS}
    if period not in days:
        period = feedback.DEFAULT_PERIOD
    now = datetime.datetime.now()
    rows = flow.driver_workload(
        g.organization,
        now=now,
        window_start=now,
        window_end=now,
        days=days[period],
    )
    driver_id = request.args.get("driver", "")
    shown = [row for row in rows if not driver_id or str(row.driver.id) == driver_id]
    return render_template(
        "/car_reservation/stats/drivers.html",
        organization=g.organization,
        periods=feedback.PERIODS,
        period=period,
        driver_id=driver_id,
        driver_choices=[(str(row.driver.id), row.driver.get_name()) for row in rows],
        rows=shown,
    )
