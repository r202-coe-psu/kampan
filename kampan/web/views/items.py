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
@acl.organization_roles_required("admin", "supervisor supplier")
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
        (
            str(item.id),
            f"{item.name} " + (f"({item.barcode_id}) " if item.barcode_id else ""),
        )
        for item in items
    ]

    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    if not form.validate_on_submit():

        item_name = request.args.get("item_name")
        if item_name:
            form.item_name.data = item_name
            items = items.filter(name__icontains=form.item_name.data)

        item_select_id = request.args.get("item_select_id")
        if item_select_id:
            form.item.data = item_select_id
            items = items.filter(id=form.item.data)

        categories = request.args.get("categories")

        if categories:
            form.categories.data = categories
            items = items.filter(categories=form.categories.data)

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
    item_name = form.item_name.data
    item_select_id = form.item.data
    categories = form.categories.data
    organization_id = organization.id
    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
            item_name=item_name,
            categories=categories,
            item_select_id=item_select_id,
        )
    )


@module.route("/upload_file_items", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_file():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.get("errors")

    if not form.validate_on_submit():
        return render_template(
            "/items/upload_file.html",
            organization=organization,
            errors=errors,
            form=form,
        )

    if form.upload_file.data:
        errors = utils.items.validate_items_upload_engagement(
            form.upload_file.data, organization
        )
        if not errors:
            completed = utils.items.process_items_upload_file(
                form.upload_file.data, organization, current_user
            )
        else:
            return render_template(
                "/items/upload_file.html",
                organization=organization,
                errors=errors,
                form=form,
            )
    else:
        return redirect(
            url_for(
                "items.upload_file", organization_id=organization_id, errors=["ไม่พบไฟล์"]
            )
        )
    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/upload_edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_edit():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.get("errors")

    if not form.validate_on_submit():
        return render_template(
            "/items/upload_edit_file.html",
            organization=organization,
            errors=errors,
            form=form,
        )

    if form.upload_file.data:
        errors = utils.items.validate_edit_items_engagement(
            form.upload_file.data, organization=organization
        )
        if not errors:
            completed = utils.items.process_edit_items_file(
                form.upload_file.data, organization, current_user
            )

        else:
            return render_template(
                "/items/upload_edit_file.html",
                organization=organization,
                errors=errors,
                form=form,
            )
    else:
        return redirect(
            url_for(
                "items.upload_edit", organization_id=organization_id, errors="ไม่พบไฟล์"
            )
        )
    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/upload_delete", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_delete():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.items.UploadFileForm()
    errors = request.args.get("errors")

    if not form.validate_on_submit():
        return render_template(
            "/items/upload_delete_file.html",
            organization=organization,
            errors=errors,
            form=form,
        )

    if form.upload_file.data:
        errors = utils.items.validate_delete_items_engagement(
            form.upload_file.data, organization
        )
        if not errors:
            completed = utils.items.process_delete_items_file(
                form.upload_file.data, organization, current_user
            )
        else:
            return render_template(
                "/items/upload_delete_file.html",
                organization=organization,
                errors=errors,
                form=form,
            )
    else:
        return redirect(
            url_for(
                "items.upload_delete", organization_id=organization_id, errors="ไม่พบไฟล์"
            )
        )
    return redirect(
        url_for(
            "items.index",
            organization_id=organization_id,
        )
    )


@module.route("/upload_compare_file", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def upload_compare_file():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.items.CompareItemForm()
    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    form.status.choices = [
        ("", "ทั้งหมด"),
        ("pending", "รอการยืนยัน"),
        ("active", "บันทึกแล้ว"),
    ]

    errors = request.args.get("errors")

    if not form.validate_on_submit():
        if not form.categories.data:
            form.categories.data = [
                str(category.id)
                for category in models.Category.objects(
                    organization=organization, status="active"
                )
            ]

        return render_template(
            "/items/upload_compare_file.html",
            organization=organization,
            form=form,
            errors=errors,
        )

    if form.upload_file.data:
        errors = utils.items.validate_compare_items_engagement(
            form.upload_file.data, organization
        )
        if errors:
            return render_template(
                "/items/upload_compare_file.html",
                organization=organization,
                form=form,
                errors=errors,
            )
        response = utils.items.compare_file(
            form.upload_file.data, form.categories.data, form.status.data, organization
        )
        return response

    return redirect(
        url_for(
            "items.upload_delete", organization_id=organization_id, errors=["ไม่พบไฟล์"]
        )
    )


@module.route("/download_template_items_file")
@acl.organization_roles_required("admin", "supervisor supplier")
def download_template_items_file():
    organization_id = request.args.get("organization_id")
    response = utils.items.get_template_items_file()
    return response


@module.route("/download_template_delete_items_file")
@acl.organization_roles_required("admin", "supervisor supplier")
def download_template_delete_items_file():
    organization_id = request.args.get("organization_id")
    response = utils.items.get_template_delete_items_file()
    return response


@module.route("/add", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
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
        return render_template(
            "/items/add_or_edit.html",
            form=form,
            organization=organization,
        )

    item = models.Item(
        created_by=current_user._get_current_object(),
    )
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
    item.name = str(form.name.data).strip()
    item.categories = models.Category.objects(id=form.categories.data).first()
    item.created_by = current_user._get_current_object()
    item.last_updated_by = current_user._get_current_object()
    item.organization = organization
    item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/<item_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
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
        if item.categories:
            form.categories.data = str(item.categories.id)
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
    form.populate_obj(item)
    if form.item_format.data == "one to one":
        item.item_format == "one to one"
        item.piece_per_set = 1
        item.piece_unit = form.set_unit.data
    else:
        item.item_format == "one to many"
        item.piece_per_set = form.piece_per_set.data
        item.piece_unit = form.piece_unit.data
    item.status = "active"
    item.name = str(form.name.data).strip()
    item.categories = models.Category.objects(id=form.categories.data).first()
    item.last_updated_by = current_user._get_current_object()
    item.organization = organization
    item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/<item_id>/edit_active_item", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier")
def edit_active_item(item_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    item = models.Item.objects().get(id=item_id)

    form = forms.items.ItemActiveEditForm(obj=item)
    form.categories.choices = [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]

    if not form.validate_on_submit():
        if item.categories:
            form.categories.data = str(item.categories.id)

        return render_template(
            "/items/edit_active_item.html",
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

    form.populate_obj(item)

    item.name = str(form.name.data).strip()
    item.categories = models.Category.objects(id=form.categories.data).first()
    item.last_updated_by = current_user._get_current_object()
    item.organization = organization
    item.status = "active"

    item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/<item_id>/delete")
@acl.organization_roles_required("admin", "supervisor supplier")
def delete(item_id):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects().get(id=item_id)
    item.status = "disactive"
    item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/<item_id>/confirm")
@acl.organization_roles_required("admin", "supervisor supplier")
def confirm(item_id):
    organization_id = request.args.get("organization_id")

    item = models.Item.objects().get(id=item_id)
    item.status = "active"
    item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/confirm_all")
@acl.organization_roles_required("admin", "supervisor supplier")
def confirm_all():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    items = models.Item.objects(status="pending", organization=organization)
    for item in items:
        item.status = "active"
        item.save()

    return redirect(url_for("items.index", **request.args))


@module.route("/<item_id>/detail")
@acl.organization_roles_required("admin", "supervisor supplier")
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


@module.route("/export_data", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "supervisor supplier", "head")
def export_data():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.items.FilterExportItemForm()
    form.categories.choices = [("", "หมวดหมู่")] + [
        (str(category.id), category.name)
        for category in models.Category.objects(
            organization=organization, status="active"
        )
    ]
    form.status.choices = [
        ("", "ทั้งหมด"),
        ("pending", "รอการยืนยัน"),
        ("active", "บันทึกแล้ว"),
    ]
    if not form.validate_on_submit():
        if not form.categories.data:
            form.categories.data = [
                str(category.id)
                for category in models.Category.objects(
                    organization=organization, status="active"
                )
            ]
        return render_template(
            "/items/export_data.html",
            organization=organization,
            form=form,
        )

    response = utils.items.export_data(
        form.categories.data, form.status.data, organization
    )
    return response
