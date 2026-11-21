"""สถิติของระบบจองรถ: แดชบอร์ดพนักงานขับรถ (ตารางรวมและรายคน) สำหรับผู้จัดรถและผู้บริหาร"""

import datetime

from flask import Blueprint, abort, g, render_template, request
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint("stats", __name__, url_prefix="/stats")

flow = utils.car_reservation_flow

# ช่วงเวลาของสถิติ: (key, ป้าย, จำนวนวันย้อนหลังจากตอนนี้)
PERIODS = [("week", "1 สัปดาห์", 7), ("month", "1 เดือน", 30), ("year", "1 ปี", 365)]
DEFAULT_PERIOD = "month"


def chosen_period(value):
    days = {key: days for key, _, days in PERIODS}
    period = value if value in days else DEFAULT_PERIOD
    return period, days[period]


def feedback_by_job(organization, jobs):
    """{id งาน: {"count", "average", "template_ids"}} และคะแนนเฉลี่ยรวม จากแบบประเมินของงานเหล่านี้

    average = ค่าเฉลี่ยคำตอบแบบคะแนน (1-5) ทุกข้อ งานที่ไม่มีคำตอบแบบคะแนนได้ None
    """
    per_job = {}
    all_scores = []
    responses = models.CarFeedbackResponse.objects(
        organization=organization, car_reservation__in=[job.id for job in jobs]
    ).only("car_reservation", "feedback_template", "answers").no_dereference()
    for response in responses:
        key = response.car_reservation.id
        entry = per_job.setdefault(key, {"count": 0, "scores": [], "template_ids": []})
        entry["count"] += 1
        template_id = response.feedback_template.id
        if template_id not in entry["template_ids"]:
            entry["template_ids"].append(template_id)
        scores = [a.answer_score for a in response.answers if a.answer_score is not None]
        entry["scores"] += scores
        all_scores += scores
    for entry in per_job.values():
        scores = entry.pop("scores")
        entry["average"] = sum(scores) / len(scores) if scores else None
    overall = sum(all_scores) / len(all_scores) if all_scores else None
    return per_job, overall


@module.route("/drivers/<driver_id>")
@acl.organization_roles_required(*flow.STATS_ROLES)
def driver(driver_id):
    driver = next(
        (d for d in flow.assignable_drivers(g.organization) if str(d.id) == driver_id),
        None,
    )
    if driver is None:
        abort(404)
    period, days = chosen_period(request.args.get("period"))
    now = datetime.datetime.now()
    since = now - datetime.timedelta(days=days)
    row = next(
        r
        for r in flow.driver_workload(
            g.organization, now=now, window_start=now, window_end=now, since=since
        )
        if r.driver.id == driver.id
    )
    done, upcoming = flow.driver_jobs(g.organization, driver, now=now, since=since)
    feedback, average_score = feedback_by_job(g.organization, done)
    return render_template(
        "/car_reservation/stats/driver.html",
        organization=g.organization,
        driver=driver,
        periods=PERIODS,
        period=period,
        row=row,
        done=done,
        upcoming=upcoming,
        feedback=feedback,
        average_score=average_score,
        feedback_count=sum(entry["count"] for entry in feedback.values()),
        # หน้าผลแบบประเมินเปิดได้เฉพาะ admin ขององค์กร
        can_open_feedback=current_user.has_organization_roles("admin", organization=g.organization),
        worked_hours=flow.worked_hours,
        booked_hours=flow.booked_hours,
    )


@module.route("/drivers")
@acl.organization_roles_required(*flow.STATS_ROLES)
def drivers():
    form = forms.car_reservation.DriverStatsFilterForm(formdata=request.args)
    period, period_days = chosen_period(form.period.data)
    now = datetime.datetime.now()
    rows = flow.driver_workload(
        g.organization,
        now=now,
        window_start=now,
        window_end=now,
        days=period_days,
    )
    driver_id = form.driver.data or ""
    shown = [row for row in rows if not driver_id or str(row.driver.id) == driver_id]
    form.driver.choices = [("", "พนักงานขับรถทุกคน")] + [
        (str(row.driver.id), row.driver.get_name()) for row in rows
    ]
    form.organization_id.data = str(g.organization.id)
    form.period.data = period
    return render_template(
        "/car_reservation/stats/drivers.html",
        organization=g.organization,
        periods=PERIODS,
        period=period,
        driver_id=driver_id,
        form=form,
        rows=shown,
    )
