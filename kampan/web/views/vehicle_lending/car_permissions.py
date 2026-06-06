import datetime

import mongoengine as me
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from flask_mongoengine import Pagination

from kampan import models, utils
from kampan.web import acl, forms

from ... import redis_rq

module = Blueprint("car_permissions", __name__, url_prefix="/car_permissions")


@module.route("/header_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.vehicle_applications.CarPermissionFilterForm(request.args)
    org_users = models.OrganizationUserRole.objects(
        organization=organization, status="active"
    )
    user_choices = []
    for org_user in org_users:
        if org_user.user:
            user_choices.append(
                (
                    str(org_user.user.id),
                    org_user.user.get_resources_fullname_th()
                    or org_user.user.get_name(),
                )
            )
    form.creator.choices = user_choices

    creator_id = form.creator.data
    location = form.location.data or ""
    departure_date = form.departure_date.data
    return_date = form.return_date.data
    created_date = form.created_date.data

    query = me.Q(organization=organization, status="pending on header")
    if creator_id:
        query &= me.Q(creator=creator_id)

    if current_user.get_current_division():
        query &= me.Q(division=current_user.get_current_division())

    if location:
        query &= me.Q(location__icontains=location)

    if departure_date:
        query &= me.Q(
            departure_datetime__gte=datetime.datetime.combine(
                departure_date, datetime.time.min
            ),
            departure_datetime__lte=datetime.datetime.combine(
                departure_date, datetime.time.max
            ),
        )

    if return_date:
        query &= me.Q(
            return_datetime__gte=datetime.datetime.combine(
                return_date, datetime.time.min
            ),
            return_datetime__lte=datetime.datetime.combine(
                return_date, datetime.time.max
            ),
        )

    if created_date:
        query &= me.Q(
            created_date__gte=datetime.datetime.combine(
                created_date, datetime.time.min
            ),
            created_date__lte=datetime.datetime.combine(
                created_date, datetime.time.max
            ),
        )

    car_applications = models.vehicle_applications.CarApplication.objects(
        query
    ).order_by("-created_date")
    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_applications, page=page, per_page=50)

    return render_template(
        "/vehicle_lending/car_permissions/header_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
        form=form,
    )


@module.route("/header_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "pending on admin"
    car_application.header_approval = (
        models.vehicle_applications.CarApplicationApproval(
            approved_by=current_user._get_current_object(),
            approved_at=datetime.datetime.now(),
        )
    )
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
            "vehicle_lending.car_permissions.header_page",
            organization_id=organization.id,
        )
    )


@module.route("/header_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def header_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by header"
    car_application.denied_reason = denied_reason
    car_application.header_approval = (
        models.vehicle_applications.CarApplicationApproval(
            approved_by=current_user._get_current_object(),
            approved_at=datetime.datetime.now(),
        )
    )
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.header_page",
            organization_id=organization.id,
        )
    )


@module.route("/director_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.vehicle_applications.CarPermissionFilterForm(request.args)
    org_users = models.OrganizationUserRole.objects(
        organization=organization, status="active"
    )
    user_choices = []
    for org_user in org_users:
        if org_user.user:
            user_choices.append(
                (
                    str(org_user.user.id),
                    org_user.user.get_resources_fullname_th()
                    or org_user.user.get_name(),
                )
            )
    form.creator.choices = user_choices

    creator_id = form.creator.data
    location = form.location.data or ""
    departure_date = form.departure_date.data
    return_date = form.return_date.data
    created_date = form.created_date.data

    query = me.Q(organization=organization, status="pending on director")
    if creator_id:
        query &= me.Q(creator=creator_id)

    if location:
        query &= me.Q(location__icontains=location)

    if departure_date:
        query &= me.Q(
            departure_datetime__gte=datetime.datetime.combine(
                departure_date, datetime.time.min
            ),
            departure_datetime__lte=datetime.datetime.combine(
                departure_date, datetime.time.max
            ),
        )

    if return_date:
        query &= me.Q(
            return_datetime__gte=datetime.datetime.combine(
                return_date, datetime.time.min
            ),
            return_datetime__lte=datetime.datetime.combine(
                return_date, datetime.time.max
            ),
        )

    if created_date:
        query &= me.Q(
            created_date__gte=datetime.datetime.combine(
                created_date, datetime.time.min
            ),
            created_date__lte=datetime.datetime.combine(
                created_date, datetime.time.max
            ),
        )

    car_applications = models.vehicle_applications.CarApplication.objects(
        query
    ).order_by("-created_date")
    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_applications, page=page, per_page=50)

    return render_template(
        "/vehicle_lending/car_permissions/director_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
        form=form,
    )


@module.route("/director_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "pending on admin"
    car_application.director_approval = (
        models.vehicle_applications.CarApplicationApproval(
            approved_by=current_user._get_current_object(),
            approved_at=datetime.datetime.now(),
        )
    )
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
            "vehicle_lending.car_permissions.director_page",
            organization_id=organization.id,
        )
    )


@module.route("/director_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def director_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by director"
    car_application.denied_reason = denied_reason
    car_application.director_approval = (
        models.vehicle_applications.CarApplicationApproval(
            approved_by=current_user._get_current_object(),
            approved_at=datetime.datetime.now(),
        )
    )
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.director_page",
            organization_id=organization.id,
        )
    )


@module.route("/admin_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_page():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form = forms.vehicle_applications.CarPermissionFilterForm(request.args)
    org_users = models.OrganizationUserRole.objects(
        organization=organization, status="active"
    )
    user_choices = []
    for org_user in org_users:
        if org_user.user:
            user_choices.append(
                (
                    str(org_user.user.id),
                    org_user.user.get_resources_fullname_th()
                    or org_user.user.get_name(),
                )
            )
    form.creator.choices = user_choices

    creator_id = form.creator.data
    location = form.location.data or ""

    departure_date = form.departure_date.data
    return_date = form.return_date.data
    created_date = form.created_date.data

    query = me.Q(
        organization=organization,
        status__in=["pending on admin", "denied by admin", "active"],
    )
    if creator_id:
        query &= me.Q(creator=creator_id)

    if location:
        query &= me.Q(location__icontains=location)

    if departure_date:
        query &= me.Q(
            departure_datetime__gte=datetime.datetime.combine(
                departure_date, datetime.time.min
            ),
            departure_datetime__lte=datetime.datetime.combine(
                departure_date, datetime.time.max
            ),
        )

    if return_date:
        query &= me.Q(
            return_datetime__gte=datetime.datetime.combine(
                return_date, datetime.time.min
            ),
            return_datetime__lte=datetime.datetime.combine(
                return_date, datetime.time.max
            ),
        )

    if created_date:
        query &= me.Q(
            created_date__gte=datetime.datetime.combine(
                created_date, datetime.time.min
            ),
            created_date__lte=datetime.datetime.combine(
                created_date, datetime.time.max
            ),
        )

    car_applications = models.vehicle_applications.CarApplication.objects(
        query
    ).order_by("-created_date")
    page = request.args.get("page", 1, type=int)
    paginated_car_applications = Pagination(car_applications, page=page, per_page=50)

    cars = models.vehicles.Car.objects(organization=organization)
    drivers = organization.get_all_drivers()

    return render_template(
        "/vehicle_lending/car_permissions/admin_page.html",
        organization=organization,
        paginated_car_applications=paginated_car_applications,
        cars=cars,
        drivers=drivers,
        form=form,
    )


@module.route("/admin_approve", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_approve():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")

    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()

    car_id = request.form.get("car")
    driver_id = request.form.get("driver")

    if car_id:
        car_application.car = models.vehicles.Car.objects(id=car_id).first()
    if driver_id:
        car_application.driver = models.User.objects(id=driver_id).first()

    car_application.status = "active"
    car_application.admin_approval = models.vehicle_applications.CarApplicationApproval(
        approved_by=current_user._get_current_object(),
        approved_at=datetime.datetime.now(),
    )
    car_application.save()

    job = redis_rq.redis_queue.queue.enqueue(
        utils.send_email_to_drivers.force_send_email_to_driver,
        args=(
            car_application,
            current_user._get_current_object(),
            current_app.config,
        ),
        job_id=f"send_email_to_driver_{car_application.id}",
        timeout=600,
        job_timeout=600,
    )

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.admin_page",
            organization_id=organization.id,
        )
    )


@module.route("/admin_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser", "head", "supervisor supplier")
def admin_denied():
    organization_id = request.form.get("organization_id")
    car_application_id = request.form.get("car_application_id")
    denied_reason = request.form.get("denied_reason", default="")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    car_application = models.vehicle_applications.CarApplication.objects(
        id=car_application_id
    ).first()
    car_application.status = "denied by admin"
    car_application.denied_reason = denied_reason
    car_application.admin_approval = models.vehicle_applications.CarApplicationApproval(
        approved_by=current_user._get_current_object(),
        approved_at=datetime.datetime.now(),
    )
    car_application.save()

    return redirect(
        url_for(
            "vehicle_lending.car_permissions.admin_page",
            organization_id=organization.id,
        )
    )
