import datetime

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from flask_login import current_user

from kampan import models
from kampan.web import acl, forms

module = Blueprint("settings", __name__, url_prefix="/settings")


def active_members(organization):
    """สมาชิก active ขององค์กร (ไม่ซ้ำคน) พร้อม id ของสมาชิกที่เป็นพนักงานขับรถ"""
    members = {}
    driver_ids = set()
    for member_role in models.OrganizationUserRole.objects(
        organization=organization, status="active"
    ):
        user = member_role.user
        if user is None:
            continue
        members[str(user.id)] = user
        if "driver" in member_role.roles:
            driver_ids.add(str(user.id))
    return members, driver_ids


def current_form_data(organization):
    data = {}
    for position in models.CarFlowPosition.objects(organization=organization):
        data[f"{position.position_key}_user"] = (
            str(position.user.id) if position.user else ""
        )
        data[f"{position.position_key}_delegates"] = [
            str(delegate.id) for delegate in position.delegates
        ]
    return data


def save_positions(organization, form, members):
    for key, _label in models.SNOR_POSITIONS:
        user_id = form[f"{key}_user"].data
        position = models.CarFlowPosition.objects(
            organization=organization, position_key=key
        ).first()

        if not user_id:
            if position:
                position.delete()
            continue

        position = position or models.CarFlowPosition(
            organization=organization, position_key=key
        )
        position.user = members[user_id]
        position.delegates = [
            members[delegate_id] for delegate_id in form[f"{key}_delegates"].data
        ]
        position.updated_by = current_user._get_current_object()
        position.updated_date = datetime.datetime.now()
        position.save()


@module.route("/positions", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def positions():
    organization = g.organization
    members, driver_ids = active_members(organization)
    member_choices = [
        (user_id, user.get_name()) for user_id, user in members.items()
    ]
    form_class = forms.snor_car.build_position_form(
        member_choices, driver_ids
    )
    form = form_class(data=current_form_data(organization))

    if form.validate_on_submit():
        save_positions(organization, form, members)
        flash("บันทึกผู้ดำรงตำแหน่งแล้ว", "success")
        return redirect(
            url_for(
                "snor_car.settings.positions",
                organization_id=organization.id,
            )
        )

    return render_template(
        "/snor_car/settings/positions.html",
        organization=organization,
        form=form,
        positions=models.SNOR_POSITIONS,
    )
