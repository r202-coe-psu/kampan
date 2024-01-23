from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
import mongoengine as me

from kampan.web import forms, acl
from kampan import models

module = Blueprint("item_positions", __name__, url_prefix="/item-positions")


@module.route("/")
@login_required
@acl.roles_required("admin")
def index():
    item_positions = models.ItemPosition.objects(status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_item_positions = Pagination(item_positions, page=page, per_page=30)
    return render_template(
        "/admin/item_positions/index.html",
        paginated_item_positions=paginated_item_positions,
        item_positions=item_positions,
    )


@module.route("/add", methods=["GET", "POST"], defaults=dict(item_position_id=None))
@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def add_or_edit(item_position_id):
    form = forms.item_positions.ItemPositionForm()

    item_position = None
    if item_position_id:
        item_position = models.ItemPosition.objects().get(id=item_position_id)
        form = forms.item_positions.ItemPositionForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/admin/item_positions/add-edit.html",
            form=form,
        )

    if not item_position:
        item_position = models.ItemPosition()

    form.populate_obj(item_position)
    item_position.user = current_user._get_current_object()

    item_position.save()

    return redirect(url_for("admin.item_positions.index"))


@module.route("/<item_position_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def edit(item_position_id):
    item_position = models.Warehouse.objects().get(id=item_position_id)
    form = forms.item_positions.WarehouseForm(obj=item_position)

    if not form.validate_on_submit():
        return render_template(
            "/admin/item_positions/add-edit.html",
            form=form,
        )

    form.populate_obj(item_position)
    item_position.save()

    return redirect(url_for("admin.item_positions.index"))


@module.route("/<item_position_id>/delete")
@login_required
@acl.roles_required("admin")
def delete(item_position_id):
    item_position = models.ItemPosition.objects().get(id=item_position_id)
    item_position.status = "disactive"
    item_position.save()

    return redirect(url_for("admin.item_positions.index"))
