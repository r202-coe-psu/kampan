from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    send_file,
    abort,
    request,
)
from flask_login import login_required, current_user
from kampan.web import forms, acl
from kampan import models
from flask_mongoengine import Pagination
import mongoengine as me

import datetime

module = Blueprint("items", __name__, url_prefix="/items")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.SearchItemForm()
    items = models.Item.objects(status="active")

    form.item.choices = [
        (item.id, f"{item.barcode_id} ({item.name})") for item in items
    ]

    form.categories.choices = [
        (item.categories, f"{''.join(item.categories)}") for item in items
    ]
    if not form.validate_on_submit():
        print(form.errors)
    if form.item.data != None:
        items = items.filter(id=form.item.data)
    if form.categories.data != None:
        items = items.filter(categories=form.categories.data)
    print(form.data)

    page = request.args.get("page", default=1, type=int)
    paginated_items = Pagination(items, page=page, per_page=24)
    return render_template(
        "/items/index.html",
        paginated_items=paginated_items,
        items=items,
        form=form,
        organization=organization,
    )


@module.route("/add", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def add():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.ItemForm()
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/items/add_or_edit.html",
            form=form,
            organization=organization,
        )

    item = models.Item(
        created_by=current_user._get_current_object(),
    )
    print("->", form.categories.data)
    form.populate_obj(item)

    if form.img.data:
        if item.image:
            item.image.replace(
                form.img.data,
                filename=form.img.data.filename,
                content_type=form.img.data.content_type,
            )
        else:
            item.image.put(
                form.img.data,
                filename=form.img.data.filename,
                content_type=form.img.data.content_type,
            )
    if form.item_format.data == "one to one":
        item.one_to_many = False
        item.piece_per_set = 1
        item.piece_unit = form.set_unit.data
    item.created_by = current_user._get_current_object()
    item.last_updated_by = current_user._get_current_object()
    item.organization = organization
    item.save()

    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def edit(item_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item = models.Item.objects().get(id=item_id)
    form = forms.items.ItemForm(obj=item)
    if not item.one_to_many:
        form.item_format.choices = form.item_format.choices[::-1]
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/items/add_or_edit.html",
            form=form,
            organization=organization,
            item=item,
        )

    if form.img.data:
        if item.image:
            item.image.replace(
                form.img.data,
                filename=form.img.data.filename,
                content_type=form.img.data.content_type,
            )
        else:
            item.image.put(
                form.img.data,
                filename=form.img.data.filename,
                content_type=form.img.data.content_type,
            )
    print("=======>", form.item_format.data)
    form.populate_obj(item)
    if form.item_format.data == "one to one":
        item.one_to_many = False
        item.piece_per_set = 1
        item.piece_unit = form.set_unit.data
    else:
        item.one_to_many = True
        item.piece_per_set = form.piece_per_set.data
        item.piece_unit = form.piece_unit.data
    item.last_updated_by = current_user._get_current_object()
    item.organization = organization
    item.save()

    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_id>/delete")
@acl.organization_roles_required("admin", "endorser", "staff")
def delete(item_id):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects().get(id=item_id)
    item.status = "disactive"
    item.save()

    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_id>/picture/<filename>")
@acl.organization_roles_required("admin", "endorser", "staff")
def image(item_id, filename):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects.get(id=item_id)

    if not item or not item.image or item.image.filename != filename:
        return abort(403)

    response = send_file(
        item.image,
        download_name=item.image.filename,
        mimetype=item.image.content_type,
    )
    return response
