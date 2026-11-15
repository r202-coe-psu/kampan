"""ตั้งค่าของระบบจองรถสำหรับแอดมินองค์กร"""

from flask import Blueprint, flash, g, redirect, render_template, url_for

from kampan import models
from kampan.web import acl, forms

module = Blueprint("settings", __name__, url_prefix="/settings")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization = g.organization
    form = forms.car_reservation.SettingsForm(obj=organization)
    if form.validate_on_submit():
        organization.car_reservation_contact_phone = (
            form.car_reservation_contact_phone.data or ""
        ).strip()
        organization.save()
        flash("บันทึกการตั้งค่าเรียบร้อยแล้ว", "success")
        return redirect(
            url_for("car_reservation.settings.index", organization_id=organization.id)
        )
    return render_template(
        "/car_reservation/settings/index.html", organization=organization, form=form
    )
