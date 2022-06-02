from flask import Blueprint, render_template, redirect, url_for, send_file
from flask_login import login_required, current_user
from kampan.web import forms
from kampan import models
import mongoengine as me

import datetime

module = Blueprint("items", __name__, url_prefix="/items")


@module.route("/")
@login_required
def index():
    items = models.Item.objects()
    return render_template(
        "/items/index.html",
        items=items,
    )


@module.route("/add", methods=["GET", "POST"])
@login_required
def add():
    form = forms.items.ItemForm()
    if not form.validate_on_submit():
        print(form.errors)
        form.size.width.label.text = "ยาว (ซม.)"
        form.size.height.label.text = "สูง (ซม.)"
        form.size.deep.label.text = "กว้าง (ซม.)"
        return render_template(
            "/items/add.html",
            form=form,
        )

    item = models.Item(
        user=current_user._get_current_object(),
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

    return redirect(url_for("items.index"))


@module.route("/<item_id>/edit", methods=["GET", "POST"])
@login_required
def edit(item_id):
    item = models.Item.objects().get(id=item_id)
    form = forms.items.ItemForm(obj=item)

    if not form.validate_on_submit():
        print(form.errors)
        form.size.width.label.text = "ยาว (ซม.)"
        form.size.height.label.text = "สูง (ซม.)"
        form.size.deep.label.text = "กว้าง (ซม.)"
        return render_template(
            "/items/item_edit.html",
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

    return redirect(url_for("items.index"))


@module.route("/<item_id>/delete")
@login_required
def delete(item_id):
    item = models.Item.objects().get(id=item_id)
    item.delete()

    return redirect(url_for("items.index"))


@module.route("/<item_id>/picture/<filename>")
def image(item_id, filename):
    item = models.Item.objects.get(id=item_id)

    if not item or not item.image or item.image.filename != filename:
        return abort(403)

    response = send_file(
        item.image,
        attachment_filename=item.image.filename,
        mimetype=item.image.content_type,
    )
    return response
