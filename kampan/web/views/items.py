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
from kampan import models, utils
from flask_mongoengine import Pagination
import mongoengine as me
import decimal

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
    items = models.Item.objects(
        status__in=["active", "pending"], organization=organization
    ).order_by("status", "-created_date")
    form.item.choices = [("", "เลือกวัสดุ")] + [
        (str(item.id), f"{item.name} ({item.barcode_id}) ") for item in items
    ]

    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    if not form.validate_on_submit():
        print(form.errors)
    if form.item.data:
        items = items.filter(id=form.item.data)
    if form.categories.data:
        items = items.filter(categories=form.categories.data)
    # print(form.data)

    page = request.args.get("page", default=1, type=int)
    try:
        paginated_items = Pagination(items, page=page, per_page=24)
    except:
        paginated_items = Pagination(items, page=1, per_page=24)
    return render_template(
        "/items/index.html",
        paginated_items=paginated_items,
        items=items,
        form=form,
        organization=organization,
    )


@module.route("/upload_file_items", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def upload_file():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.get("errors")
    upload_errors = {
        "headers": "ลงทะเบียนวัสดุ",
        "errors": errors,
    }
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/items/upload_file.html",
            organization=organization,
            upload_errors=upload_errors,
            form=form,
        )

    if form.upload_file.data:
        errors = utils.items.validate_items_engagement(form.upload_file.data)
        if not errors:
            completed = utils.items.process_items_file(
                form.upload_file.data, organization, current_user
            )
        else:
            return redirect(
                url_for(
                    "items.upload_file", organization_id=organization_id, errors=errors
                )
            )
    else:
        return redirect(
            url_for(
                "items.upload_file", organization_id=organization_id, errors="ไม่พบไฟล์"
            )
        )
    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/downlaod_template_items_file")
@acl.organization_roles_required("admin", "endorser", "staff")
def download_template_items_file():
    organization_id = request.args.get("organization_id")
    response = utils.items.get_template_items_file()
    return response


@module.route("/add", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "staff")
def add():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.ItemForm()
    form.categories.choices = [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
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
    # print("->", form.categories.data)
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
        item.item_format == "one to many"
        item.piece_per_set = 1
        item.piece_unit = form.set_unit.data
    item.categories = models.Category.objects(id=form.categories.data).first()
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
    form.categories.choices = [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    if not item.item_format == "one to many":
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
    # print("=======>", form.item_format.data)
    form.populate_obj(item)
    if form.item_format.data == "one to one":
        item.item_format == "one to one"
        item.piece_per_set = 1
        item.piece_unit = form.set_unit.data
    else:
        item.item_format == "one to many"
        item.piece_per_set = form.piece_per_set.data
        item.piece_unit = form.piece_unit.data
    item.categories = models.Category.objects(id=form.categories.data).first()
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


@module.route("/<item_id>/confirm")
@acl.organization_roles_required("admin", "endorser", "staff")
def confirm(item_id):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects().get(id=item_id)
    item.status = "active"
    item.save()
    item_snapshot = models.items.ItemSnapshot(
        item=item,
        amount=item.get_amount_items(),
        amount_pieces=item.get_amount_pieces(),
        organization=item.organization,
    )
    last_price = item.get_last_price()
    last_price_per_piece = item.get_last_price_per_piece()
    remaining_balance = item.get_remaining_balance()
    if last_price:
        item_snapshot.last_price = decimal.Decimal(last_price)

    if last_price_per_piece:
        item_snapshot.last_price_per_piece = decimal.Decimal(last_price_per_piece)

    if remaining_balance:
        item_snapshot.remaining_balance = decimal.Decimal(remaining_balance)
    item_snapshot.save()

    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/confirm_all")
@acl.organization_roles_required("admin", "endorser", "staff")
def confirm_all():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    items = models.Item.objects(status="pending", organization=organization)
    for item in items:
        item.status = "active"
        item.save()

        item_snapshot = models.items.ItemSnapshot(
            item=item,
            amount=item.get_amount_items(),
            amount_pieces=item.get_amount_pieces(),
            organization=item.organization,
        )

        last_price = item.get_last_price()
        last_price_per_piece = item.get_last_price_per_piece()
        remaining_balance = item.get_remaining_balance()
        if last_price:
            item_snapshot.last_price = decimal.Decimal(last_price)

        if last_price_per_piece:
            item_snapshot.last_price_per_piece = decimal.Decimal(last_price_per_piece)

        if remaining_balance:
            item_snapshot.remaining_balance = decimal.Decimal(remaining_balance)
        item_snapshot.save()

    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/<item_id>/detail")
@acl.organization_roles_required("admin", "endorser", "staff")
def detail(item_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item = models.Item.objects().get(id=item_id)

    return render_template(
        "/items/detail.html",
        organization=organization,
        item=item,
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
