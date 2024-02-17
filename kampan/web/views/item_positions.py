from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
from flask_mongoengine import Pagination
import mongoengine as me

import datetime

module = Blueprint("item_positions", __name__, url_prefix="/item-positions")


@module.route("/")
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    item_positions = models.ItemPosition.objects(status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_item_positions = Pagination(item_positions, page=page, per_page=30)
    return render_template(
        "/item_positions/index.html",
        paginated_item_positions=paginated_item_positions,
        item_positions=item_positions,
        organization=organization,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(item_position_id=None))
@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def add_or_edit(item_position_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.item_positions.ItemPositionForm()

    item_position = None
    if item_position_id:
        item_position = models.ItemPosition.objects().get(id=item_position_id)
        form = forms.item_positions.ItemPositionForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/item_positions/add-edit.html",
            form=form,
            organization=organization,
        )

    if not item_position:
        item_position = models.ItemPosition()

    form.populate_obj(item_position)
    if not item_position_id:
        item_position.created_by = current_user._get_current_object()
    item_position.last_updated_by = current_user._get_current_object()
    item_position.save()

    return redirect(
        url_for(
            "item_positions.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(item_position_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item_position = models.Warehouse.objects().get(id=item_position_id)
    form = forms.item_positions.WarehouseForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/item_positions/add-edit.html",
            form=form,
            organization=organization,
        )

    form.populate_obj(item_position)
    item_position.save()

    return redirect(
        url_for(
            "item_positions.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_position_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(item_position_id):
    organization_id = request.args.get("organization_id")

    item_position = models.ItemPosition.objects().get(id=item_position_id)
    item_position.status = "disactive"
    item_position.save()

    return redirect(
        url_for(
            "item_positions.index",
            organization_id=organization_id,
        )
    )
