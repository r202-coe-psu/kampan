from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    jsonify,
    current_app,
    abort,
)
from flask_login import login_required, current_user
import mongoengine as me
from flask_mongoengine import Pagination
import datetime

from kampan.web import forms, acl
from kampan import models, utils
from ... import redis_rq

module = Blueprint("car_applications", __name__, url_prefix="/car_applications")


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
        car_applications = models.vehicle_applications.CarApplication.objects(
            organization=organization
        ).order_by("-created_date")
    else:
        car_applications = models.vehicle_applications.CarApplication.objects(
            organization=organization, creator=current_user
        ).order_by("-created_date")
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)
    return render_template(
        "/vehicle_lending/car_applications/index.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
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
    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization
    )
    paginated_car_applications = Pagination(car_applications, page=1, per_page=50)
    return render_template(
        "/vehicle_lending/car_applications/calendar.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
    )


@module.route("/create", methods=["GET", "POST"], defaults={"car_application_id": None})
@module.route("/<car_application_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def create_or_edit(car_application_id):
    car_application = None
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.vehicle_applications.CarApplicationForm()

    form.car.choices = [("", "ไม่ได้ระบุ")] + [
        (str(car.id), car.license_plate)
        for car in models.vehicles.Car.objects(organization=organization)
    ]
    form.driver.choices = [("", "ไม่ได้ระบุ")] + [
        (str(user.id), user.get_resources_fullname_th())
        for user in organization.get_all_drivers()
    ]
    if not form.validate_on_submit():
        if car_application_id:
            car_application = models.vehicle_applications.CarApplication.objects(
                id=car_application_id
            ).first()
            form = forms.vehicle_applications.CarApplicationForm(obj=car_application)

        else:
            date = request.args.get("date", type=str, default=None)
            if date:
                date = datetime.datetime.strptime(date, "%Y-%m-%d")
                form.departure_date.data = date.date()
                form.departure_time.data = date.time()
                form.return_date.data = date.date()
                form.return_time.data = date.time()

                form.flight_time.data = date.time()
                form.flight_return_time.data = date.time()

            else:
                date = datetime.datetime.now()
                form.departure_date.data = date.date()
                form.departure_time.data = date.time()
                form.return_date.data = date.date()
                form.return_time.data = date.time()

                form.flight_time.data = date.time()
                form.flight_return_time.data = date.time()

        if car_application:
            form.departure_date.data = car_application.departure_datetime.date()
            form.departure_time.data = car_application.departure_datetime.time()

            form.return_date.data = car_application.return_datetime.date()
            form.return_time.data = car_application.return_datetime.time()

            form.flight_time.data = car_application.flight_datetime.time()
            form.flight_return_time.data = car_application.flight_return_datetime.time()

            if car_application.driver:
                form.driver.data = str(car_application.driver.id)

        form.car.choices = [("", "ไม่ได้ระบุ")] + [
            (str(car.id), car.license_plate)
            for car in models.vehicles.Car.objects(organization=organization)
        ]
        form.driver.choices = [("", "ไม่ได้ระบุ")] + [
            (str(user.id), user.get_resources_fullname_th())
            for user in organization.get_all_drivers()
        ]

        print(form.errors)
        return render_template(
            "/vehicle_lending/car_applications/create_or_edit.html",
            organization=organization,
            form=form,
        )

    car_application = models.vehicle_applications.CarApplication()
    if car_application_id:
        car_application = models.vehicle_applications.CarApplication.objects(
            id=car_application_id
        ).first()

    form.populate_obj(car_application)
    if form.car.data:
        car_application.car = models.vehicles.Car.objects(id=form.car.data).first()
    else:
        car_application.car = None

    if form.driver.data:
        car_application.driver = models.User.objects(id=form.driver.data).first()
    else:
        car_application.driver = None
    car_application.departure_datetime = datetime.datetime.combine(
        form.departure_date.data, form.departure_time.data
    )
    if form.travel_type.data != "one way":
        car_application.return_datetime = datetime.datetime.combine(
            form.return_date.data, form.return_time.data
        )
    car_application.status = "pending on header"

    if form.using_type.data == "out of town":
        car_application.status = "pending on director"
    if form.using_type.data == "airport transfer":
        car_application.flight_datetime = datetime.datetime.combine(
            form.departure_date.data, form.flight_time.data
        )
        if form.travel_type.data != "one way":
            car_application.flight_return_datetime = datetime.datetime.combine(
                form.return_date.data, form.flight_return_time.data
            )

    car_application.organization = current_user.get_current_organization()
    car_application.division = current_user.get_current_division()
    if not car_application_id:
        car_application.creator = current_user
    division = None
    member = models.OrganizationUserRole.objects(
        user=current_user,
        organization=organization,
        status__ne="disactive",
    ).first()
    if member:
        division = member.division

    car_application.division = division
    car_application.updater = current_user
    car_application.updated_date = datetime.datetime.now()
    car_application.save()

    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.send_email_car_application_to_endorser,
        args=(
            car_application,
            current_user._get_current_object(),
            current_app.config,
            car_application.status,
        ),
        job_id=f"send_email_car_application_to_endorser_{car_application.id}",
        timeout=600,
        job_timeout=600,
    )
    return redirect(
        url_for(
            "vehicle_lending.car_applications.index", organization_id=organization_id
        )
    )


@module.route("/<car_application_id>/delete")
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier", "supervisor supplier"
)
def delete(car_application_id):
    organization_id = request.args.get("organization_id")

    car_application = models.vehicle_applications.CarApplication.objects().get(
        id=car_application_id, organization=organization_id
    )
    car_application.status = "disactive"
    car_application.save()

    return redirect(url_for("vehicle_lending.car_applications.index", **request.args))


@module.route("/get_car_applications")
@login_required
def get_car_applications():
    organization_id = request.args.get("organization_id")

    car_applications = models.vehicle_applications.CarApplication.objects(
        organization=organization_id,
        status__in=[
            "pending on header",
            "pending on director",
            "pending on admin",
            "active",
            "completed",
        ],
    )

    color_of_event = {
        "active": "green",
        "pending on header": "orange",
        "pending on director": "orange",
        "pending on admin": "orange",
        "completed": "gray",
    }
    datas = []
    for car_application in car_applications:
        start = car_application.departure_datetime.strftime("%Y-%m-%d")
        end = (
            car_application.departure_datetime + datetime.timedelta(days=1)
        ).strftime("%Y-%m-%d")
        if car_application.travel_type == "round trip":
            end = (
                car_application.return_datetime + datetime.timedelta(days=1)
            ).strftime("%Y-%m-%d")
        time = car_application.departure_datetime.strftime("%H:%M")
        creator_name = (
            car_application.creator.get_resources_fullname_th()
            if car_application.creator
            else "-"
        )
        data = {
            "id": str(car_application.id),
            "title": f"{time} น. , {creator_name} , {car_application.location}",
            "start": start,
            "end": end,
            "color": color_of_event.get(car_application.status, "gray"),
        }
        datas.append(data)

    return jsonify({"car_applications": datas})


@module.route("/<car_application_id>/modal")
@login_required
def event_modal(car_application_id):
    organization_id = request.args.get("organization_id")
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization_id
    ).first()
    return render_template(
        "/vehicle_lending/car_applications/components/event_modal.html",
        car_application=car_application,
    )


@module.route("/<car_application_id>/paper", methods=["GET"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def paper(car_application_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id, organization=organization
    ).first()

    if not car_application:
        return abort(404)

    if not current_user.has_organization_roles("admin", "supervisor supplier"):
        if car_application.creator != current_user:
            return abort(403)

    return render_template(
        "/vehicle_lending/car_applications/paper.html",
        car_applications=[car_application],
        organization=organization,
        is_bulk=False,
    )


@module.route("/combine_paper", methods=["GET"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def combine_paper():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return abort(404)

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    if not start_date_str or not end_date_str:
        return abort(400, "กรุณาระบุวันที่เริ่มต้นและวันที่สิ้นสุด")

    try:
        start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    except ValueError:
        return abort(400, "รูปแบบวันที่ไม่ถูกต้อง")

    if current_user.has_organization_roles("admin", "supervisor supplier"):
        car_applications = models.vehicle_applications.CarApplication.objects(
            organization=organization,
            departure_datetime__gte=start_date,
            departure_datetime__lte=end_date,
            status__ne="disactive",
        ).order_by("departure_datetime")
    else:
        car_applications = models.vehicle_applications.CarApplication.objects(
            organization=organization,
            creator=current_user,
            departure_datetime__gte=start_date,
            departure_datetime__lte=end_date,
            status__ne="disactive",
        ).order_by("departure_datetime")

    return render_template(
        "/vehicle_lending/car_applications/paper.html",
        car_applications=car_applications,
        organization=organization,
        is_bulk=True,
        start_date_str=start_date_str,
        end_date_str=end_date_str,
    )
