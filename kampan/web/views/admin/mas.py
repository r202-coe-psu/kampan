from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
)
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
from kampan.web import acl, forms
from kampan import models

import mongoengine as me
import datetime

module = Blueprint("mas", __name__, url_prefix="/mas")


@module.route("/")
@login_required
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    mas = models.MAS.objects(status="active").order_by("created_date")
    page = request.args.get("page", default=1, type=int)
    paginated_mas = Pagination(mas, page=page, per_page=20)
    total_amount = sum(m.amount or 0 for m in mas)
    total_remaining = sum(m.remaining_amount or 0 for m in mas)
    total_reservable = sum(m.reservable_amount or 0 for m in mas)
    return render_template(
        "procurement/mas/index.html",
        organization=organization,
        mas=paginated_mas.items,
        paginated_mas=paginated_mas,
        total_amount=total_amount,
        total_remaining=total_remaining,
        total_reservable=total_reservable,
    )


@module.route("/create", methods=["GET", "POST"])
@module.route("/<mas_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(mas_id=None):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first() if mas_id else None
    form = forms.mas.MASForm(obj=mas)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "procurement/mas/create_or_edit.html",
            form=form,
            organization=organization,
            mas=mas,
        )

    if not mas:
        mas = models.MAS()
        mas.created_by = current_user._get_current_object()

    form.populate_obj(mas)
    mas.last_updated_by = current_user._get_current_object()
    mas.remaining_amount = mas.amount
    mas.reservable_amount = mas.remaining_amount or 0
    mas.save()

    return redirect(url_for("admin.mas.index", organization_id=organization.id))


@module.route("/<mas_id>/delete", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def delete(mas_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first()
    if mas:
        mas.status = "closed"
        mas.save()

    return redirect(url_for("admin.mas.index", organization_id=organization.id))


@module.route("/<mas_id>/reservation", methods=["GET"])
@acl.organization_roles_required("admin")
def reservation(mas_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    mas = models.MAS.objects(id=mas_id).first()
    reservations = models.Reservation.objects(mas=mas).order_by("-reserved_date")
    page = request.args.get("page", default=1, type=int)
    paginated_reservations = Pagination(reservations, page=page, per_page=20)

    return render_template(
        "procurement/mas/reservation.html",
        organization=organization,
        mas=mas,
        reservations=paginated_reservations.items,
        paginated_reservations=paginated_reservations,
    )
