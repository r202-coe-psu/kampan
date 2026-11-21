"""โปรไฟล์ของฉันในระบบจองรถ: ข้อมูลบัญชี บทบาทในหน่วยงาน ลายเซ็น และสรุปคำขอของตัวเอง"""

from flask import Blueprint, g, render_template
from flask_login import current_user

from kampan import models
from kampan.web import acl
from kampan.web.views.car_reservation.calendar import ANY_ORGANIZATION_ROLE

module = Blueprint("profile", __name__, url_prefix="/profile")


@module.route("")
@acl.organization_roles_required(*ANY_ORGANIZATION_ROLE)
def index():
    organization = g.organization
    user = current_user._get_current_object()
    mine = models.CarReservation.objects(organization=organization, creator=user)
    counts = {
        status: mine.filter(status=status).count()
        for status, _ in models.car_reservations.RESERVATION_STATUS
    }
    return render_template(
        "/car_reservation/profile/index.html",
        organization=organization,
        role_items=user.get_organization_role_items(organization),
        division=user.get_current_division(organization),
        total=mine.count(),
        counts=counts,
        status_labels=dict(models.car_reservations.RESERVATION_STATUS),
    )
