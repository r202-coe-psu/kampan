from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    send_file,
    abort,
    jsonify,
    current_app,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
from wtforms import fields, validators, widgets
import datetime

from kampan.web import forms, acl, redis_rq
from kampan import models, utils


module = Blueprint(
    "motorcycle_applications", __name__, url_prefix="/motorcycle_applications"
)


@module.route("", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if current_user.has_organization_roles("admin", "supervisor supplier"):

        motorcycle_applications = (
            models.vehicle_applications.MotorcycleApplication.objects(
                organization=organization
            ).order_by("-created_date")
        )
    else:
        motorcycle_applications = (
            models.vehicle_applications.MotorcycleApplication.objects(
                organization=organization, creator=current_user
            ).order_by("-created_date")
        )
    paginated_motorcycle_applications = Pagination(
        motorcycle_applications, page=1, per_page=50
    )
    return render_template(
        "/vehicle_lending/motorcycle_applications/index.html",
        organization=organization,
        paginated_motorcycle_applications=paginated_motorcycle_applications,
    )


@module.route("/calendar", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def calendar():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycle_applications = models.vehicle_applications.MotorcycleApplication.objects(
        organization=organization
    )
    paginated_motorcycle_applications = Pagination(
        motorcycle_applications, page=1, per_page=50
    )
    return render_template(
        "/vehicle_lending/motorcycle_applications/calendar.html",
        organization=organization,
        paginated_motorcycle_applications=paginated_motorcycle_applications,
    )


@module.route(
    "/create", methods=["GET", "POST"], defaults={"motorcycle_application_id": None}
)
@module.route("/<motorcycle_application_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def create_or_edit(motorcycle_application_id):
    motorcycle_application = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicle_applications.MotorcycleApplicationForm()

    form.motorcycle.choices = [
        (str(motorcycle.id), motorcycle.license_plate)
        for motorcycle in models.vehicles.Motorcycle.objects(organization=organization)
    ]
    if not form.validate_on_submit():
        if motorcycle_application_id:
            motorcycle_application = (
                models.vehicle_applications.MotorcycleApplication.objects(
                    id=motorcycle_application_id
                ).first()
            )
            form = forms.vehicle_applications.MotorcycleApplicationForm(
                obj=motorcycle_application
            )

            form.departure_date.data = motorcycle_application.departure_datetime.date()
            form.departure_time.data = motorcycle_application.departure_datetime.time()
        else:

            date = request.args.get("date", type=str, default=None)
            if date:
                date = datetime.datetime.strptime(date, "%Y-%m-%d")
                form.departure_date.data = date.date()
                form.departure_time.data = date.time()
            else:
                date = datetime.datetime.now()
                form.departure_date.data = date.date()
                form.departure_time.data = date.time()
        form.motorcycle.choices = [
            (str(motorcycle.id), motorcycle.license_plate)
            for motorcycle in models.vehicles.Motorcycle.objects(
                organization=organization
            )
        ]

        print(form.errors)
        return render_template(
            "/vehicle_lending/motorcycle_applications/create_or_edit.html",
            organization=organization,
            form=form,
        )
    motorcycle_application = models.vehicle_applications.MotorcycleApplication()
    if motorcycle_application_id:
        motorcycle_application = (
            models.vehicle_applications.MotorcycleApplication.objects(
                id=motorcycle_application_id
            ).first()
        )

    form.populate_obj(motorcycle_application)
    motorcycle_application.motorcycle = models.vehicles.Motorcycle.objects(
        id=form.motorcycle.data
    ).first()
    if not motorcycle_application.motorcycle:
        return render_template(
            "/vehicle_lending/motorcycle_applications/create_or_edit.html",
            organization=organization,
            form=form,
        )
    motorcycle_application.departure_datetime = datetime.datetime.combine(
        form.departure_date.data, form.departure_time.data
    )

    motorcycle_application.organization = current_user.get_current_organization()
    motorcycle_application.division = current_user.get_current_division()
    if not motorcycle_application_id:
        motorcycle_application.creator = current_user
    motorcycle_application.updater = current_user
    motorcycle_application.updated_date = datetime.datetime.now()
    motorcycle_application.save()
    return redirect(
        url_for(
            "vehicle_lending.motorcycle_applications.index",
            organization_id=organization_id,
        )
    )


@module.route("/<motorcycle_application_id>/return_motorcycle", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def return_motorcycle(motorcycle_application_id):
    motorcycle_application = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.vehicle_applications.ReturnMotorcycleApplicationForm()

    if motorcycle_application_id:
        motorcycle_application = (
            models.vehicle_applications.MotorcycleApplication.objects(
                id=motorcycle_application_id
            ).first()
        )

    if not form.validate_on_submit():
        print(form.errors)
        if motorcycle_application_id:
            form.last_mileage.data = motorcycle_application.motorcycle.last_mileage
            form.return_date.data = datetime.datetime.now().date()
            form.return_time.data = datetime.datetime.now().time()

        return render_template(
            "/vehicle_lending/motorcycle_applications/return_motorcycle.html",
            organization=organization,
            form=form,
        )

    motorcycle_application = models.vehicle_applications.MotorcycleApplication.objects(
        id=motorcycle_application_id
    ).first()

    form.populate_obj(motorcycle_application)

    motorcycle_application.return_datetime = datetime.datetime.combine(
        form.return_date.data, form.return_time.data
    )

    motorcycle_application.updater = current_user
    motorcycle_application.updated_date = datetime.datetime.now()
    motorcycle_application.motorcycle.last_mileage = form.last_mileage.data
    motorcycle_application.motorcycle.save()
    motorcycle_application.status = "returned"
    motorcycle_application.save()
    return redirect(
        url_for(
            "vehicle_lending.motorcycle_applications.index",
            organization_id=organization_id,
        )
    )


@module.route("/<motorcycle_application_id>/delete")
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier", "supervisor supplier"
)
def delete(motorcycle_application_id):
    organization_id = request.args.get("organization_id")

    motorcycle_application = (
        models.vehicle_applications.MotorcycleApplication.objects().get(
            id=motorcycle_application_id
        )
    )
    motorcycle_application.status = "disactive"
    motorcycle_application.save()

    return redirect(
        url_for("vehicle_lending.motorcycle_applications.index", **request.args)
    )


@module.route("/get_motorcycle_applications")
@login_required
def get_motorcycle_applications():
    organization_id = request.args.get("organization_id")

    motorcycle_applications = models.vehicle_applications.MotorcycleApplication.objects(
        status__in=[
            "pending",
            "returned",
            "active",
        ]
    ).order_by("-status")

    color_of_event = {
        "active": "blue",
        "pending": "orange",
        "returned": "green",
    }
    datas = []
    for motorcycle_application in motorcycle_applications:
        start = motorcycle_application.departure_datetime.strftime("%Y-%m-%d")
        end = (
            motorcycle_application.departure_datetime + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        time = motorcycle_application.departure_datetime.strftime("%H:%M")
        data = {
            "id": str(motorcycle_application.id),
            "title": f"{time} น. : {motorcycle_application.motorcycle.license_plate} : {motorcycle_application.location}",
            "description": f"ป้ายทะเบียน : {motorcycle_application.motorcycle.license_plate}\nเหตุผล : {motorcycle_application.request_reason}\nสถานที่ที่ต้องการจะไป : {motorcycle_application.location}",
            "start": start,
            "end": end,
            "color": color_of_event[motorcycle_application.status],
        }
        datas.append(data)

    return jsonify({"motorcycle_applications": datas})


@module.route("/<motorcycle_application_id>/send_email", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def send_email(motorcycle_application_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    motorcycle_application = models.vehicle_applications.MotorcycleApplication.objects(
        id=motorcycle_application_id
    ).first()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.motorcycle_send_emails.force_send_email_to_admin,
        args=(
            motorcycle_application,
            current_user._get_current_object(),
            current_app.config,
        ),
        job_id=f"force_sent_email_head_endorser_motorcycle_application_{motorcycle_application.id}",
        timeout=600,
        job_timeout=600,
    )
    return {"status": "success", "job_id": job.id}
