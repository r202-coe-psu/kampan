"""แบบประเมินความพึงพอใจของระบบจองรถ: ผู้ขอประเมินหลังปิดงาน (spec ข้อ 5.6)"""

from flask import Blueprint, abort, g, render_template
from flask_login import current_user

from kampan import models, utils
from kampan.web import acl, forms

module = Blueprint("feedback", __name__, url_prefix="/feedback")

ANY_ORGANIZATION_ROLE = [role for role, _ in models.organizations.ORGANIZATION_ROLES]


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


@module.route("/<reservation_id>")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def form(reservation_id):
    reservation = get_reservation_or_404(reservation_id)
    return render_template(
        "/car_reservation/feedback/form.html",
        organization=g.organization,
        reservation=reservation,
        form=forms.car_reservation_feedback.FeedbackForm(),
        question_groups=utils.car_reservation_feedback.QUESTION_GROUPS,
        score_choices=forms.car_reservation_feedback.SCORE_CHOICES,
    )
