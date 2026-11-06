"""แบบประเมินความพึงพอใจของระบบจองรถ: ผู้ขอประเมินหลังปิดงาน (spec ข้อ 5.6)"""

from flask import Blueprint, abort, flash, g, redirect, render_template, url_for
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint("feedback", __name__, url_prefix="/feedback")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]


@module.route("/")
@acl.organization_roles_required("admin")
def index():
    return render_template(
        "/car_reservation/feedback/index.html",
        organization=g.organization,
        feedbacks=models.CarReservationFeedback.objects(
            organization=g.organization
        ).order_by("-created_date"),
    )


def get_reservation_or_404(reservation_id):
    try:
        reservation = models.CarReservation.objects(
            id=reservation_id, organization=g.organization
        ).first()
    except Exception:
        reservation = None
    if reservation is None:
        abort(404)
    return reservation


@module.route("/<reservation_id>", methods=["GET", "POST"])
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def form(reservation_id):
    reservation = get_reservation_or_404(reservation_id)
    if not utils.car_reservation_feedback.can_submit(
        reservation, current_user._get_current_object()
    ):
        abort(403)
    detail_url = url_for(
        "car_reservation.requests.detail",
        request_id=reservation.id,
        organization_id=g.organization.id,
    )
    if utils.car_reservation_feedback.feedback_of(reservation) is not None:
        flash("ประเมินแล้ว", "warning")
        return redirect(detail_url)
    form = forms.car_reservation_feedback.FeedbackForm()
    if form.validate_on_submit():
        models.CarReservationFeedback(
            organization=g.organization,
            reservation=reservation,
            creator=current_user._get_current_object(),
            car=reservation.car,
            driver=reservation.driver,
            scores=[
                models.car_reservation_feedback.FeedbackScore(
                    key=key, score=form[key].data
                )
                for key in utils.car_reservation_feedback.SCORE_KEYS
            ],
            comment=form.comment.data or "",
        ).save()
        flash("ขอบคุณสำหรับการประเมิน", "success")
        return redirect(detail_url)
    return render_template(
        "/car_reservation/feedback/form.html",
        organization=g.organization,
        reservation=reservation,
        form=form,
        question_groups=utils.car_reservation_feedback.QUESTION_GROUPS,
        score_choices=forms.car_reservation_feedback.SCORE_CHOICES,
    )
