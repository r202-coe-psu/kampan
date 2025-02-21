from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models

module = Blueprint("motorcycles", __name__, url_prefix="/motorcycles")


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycles = models.vehicles.Motorcycle.objects(organization=organization)
    return render_template(
        "/vehicle_lending/motorcycles/index.html",
        organization=organization,
        motorcycles=motorcycles,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"motorcycle_id": None})
@module.route("/<motorcycle_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create_or_edit(motorcycle_id):
    motorcycle = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicles.MotorcycleForm()
    if motorcycle_id:
        motorcycle = models.vehicles.Motorcycle.objects(id=motorcycle_id).first()
        form = forms.vehicles.MotorcycleForm(obj=motorcycle)

    if not form.validate_on_submit():
        print(form.errors)

        return render_template(
            "/vehicle_lending/motorcycles/create_or_edit.html",
            organization=organization,
            form=form,
        )

    motorcycle = models.vehicles.Motorcycle()
    if motorcycle_id:
        motorcycle = models.vehicles.Motorcycle.objects(id=motorcycle_id).first()
    if form.upload_image.data:
        print(form.upload_image.data)
        if motorcycle.image:
            motorcycle.image.replace(
                form.upload_image.data,
                filename=form.upload_image.data.filename,
                content_type=form.upload_image.data.content_type,
            )
        else:
            motorcycle.image.put(
                form.upload_image.data,
                filename=form.upload_image.data.filename,
                content_type=form.upload_image.data.content_type,
            )
    form.populate_obj(motorcycle)
    motorcycle.organization = current_user.get_current_organization()
    if not motorcycle_id:
        motorcycle.creator = current_user
    motorcycle.updater = current_user
    motorcycle.updated_date = datetime.datetime.now()

    motorcycle.save()
    return redirect(
        url_for("vehicle_lending.motorcycles.index", organization_id=organization_id)
    )


@module.route("/<motorcycle_id>/picture/<filename>")
@acl.organization_roles_required(
    "admin", "supervisor supplier", "head", "supervisor supplier"
)
def image(motorcycle_id, filename):
    organization_id = request.args.get("organization_id")

    motorcycle = models.vehicles.Motorcycle.objects.get(id=motorcycle_id)

    if not motorcycle or not motorcycle.image or motorcycle.image.filename != filename:
        return abort(403)

    response = send_file(
        motorcycle.image,
        download_name=motorcycle.image.filename,
        mimetype=motorcycle.image.content_type,
    )
    return response


@module.route("/<motorcycle_id>/delete")
@acl.organization_roles_required("admin", "supervisor supplier")
def delete(motorcycle_id):
    organization_id = request.args.get("organization_id")

    motorcycle = models.vehicles.Motorcycle.objects().get(id=motorcycle_id)
    motorcycle.status = "disactive"
    motorcycle.save()

    return redirect(url_for("vehicle_lending.motorcycles.index", **request.args))
