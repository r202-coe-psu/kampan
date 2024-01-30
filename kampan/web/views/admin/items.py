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


module = Blueprint("items", __name__, url_prefix="/items")


@module.route("/", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def index():
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
        "/admin/items/index.html",
        paginated_items=paginated_items,
        items=items,
        form=form,
    )


@module.route("/add", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def add():
    form = forms.items.ItemForm()
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/admin/items/add_or_edit.html",
            form=form,
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

    item.save()

    return redirect(url_for("admin.items.index"))


@module.route("/<item_id>/edit", methods=["GET", "POST"])
@login_required
@acl.roles_required("admin")
def edit(item_id):
    item = models.Item.objects().get(id=item_id)
    form = forms.items.ItemForm(obj=item)

    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/admin/items/add_or_edit.html",
            form=form,
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

    item.save()

    return redirect(url_for("admin.items.index"))


@module.route("/<item_id>/delete")
@login_required
@acl.roles_required("admin")
def delete(item_id):
    item = models.Item.objects().get(id=item_id)
    item.status = "disactive"
    item.save()

    return redirect(url_for("admin.items.index"))


@module.route("/<item_id>/picture/<filename>")
@acl.roles_required("admin")
def image(item_id, filename):
    item = models.Item.objects.get(id=item_id)

    if not item or not item.image or item.image.filename != filename:
        return abort(403)

    response = send_file(
        item.image,
        download_name=item.image.filename,
        mimetype=item.image.content_type,
    )
    return response
