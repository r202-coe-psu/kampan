from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    current_app,
    session,
)
from flask_login import login_required, current_user

import datetime
import mongoengine as me

from kampan import models
from kampan.web import acl, forms
from kampan.utils import email_utils

from urllib import parse
from .. import redis_rq

from jinja2 import Template

module = Blueprint("email_templates", __name__, url_prefix="/email_templates")
subviews = []


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required("staff", "admin")
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects.get(id=organization_id)
    email_templates = models.EmailTemplate.objects(organization=organization)

    form = forms.email_templates.EmailTemplateFileForm()

    return render_template(
        "/email_templates/index.html",
        email_templates=email_templates,
        organization=organization,
        form=form,
    )


@module.route(
    "/create",
    methods=["GET", "POST"],
    defaults={"email_template_id": None},
)
@module.route("/<email_template_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("staff", "admin")
def create_or_edit(email_template_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.email_templates.EmailTemplateForm()
    upload_form = forms.email_templates.EmailTemplateFileForm()
    organization = models.Organization.objects.get(id=organization_id)

    email_template = models.EmailTemplate.objects()
    if email_template_id:
        email_template = models.EmailTemplate.objects.get(id=email_template_id)
        organization = models.Organization.objects.get(id=organization_id)
        form = forms.email_templates.EmailTemplateForm(obj=email_template)

    uploaded_email_template = session.get("uploaded_email_template_form", None)
    if uploaded_email_template:
        form.body.data = uploaded_email_template
        session.pop("uploaded_email_template_form")

    if not form.validate_on_submit():
        return render_template(
            "/email_templates/create_or_edit.html",
            form=form,
            upload_form=upload_form,
            email_template=email_template,
            organization=organization,
        )

    if not email_template_id:
        email_template = models.EmailTemplate(
            organization=organization,
            created_by=current_user._get_current_object(),
            last_updated_by=current_user._get_current_object(),
            created_date=datetime.datetime.now(),
            updated_date=datetime.datetime.now(),
        )

    form.populate_obj(email_template)

    email_template.organization = organization
    email_template.last_updated_by = current_user._get_current_object()
    email_template.updated_date = datetime.datetime.now()
    email_template.save()

    return redirect(
        url_for(
            "email_templates.detail",
            email_template_id=email_template.id,
            organization_id=organization.id,
        )
    )


@module.route(
    "/upload_email_template",
    methods=["GET", "POST"],
    defaults={"email_template_id": None},
)
@module.route(
    "/<email_template_id>/upload_email_template",
    methods=["GET", "POST"],
)
@acl.organization_roles_required("staff", "admin")
def upload_email_template(email_template_id):
    organization = models.Organization.objects.get(
        id=request.args.get("organization_id")
    )
    upload_form = forms.email_templates.EmailTemplateFileForm()

    if not upload_form.validate_on_submit():
        return redirect(
            url_for(
                "email_templates.create_or_edit",
                organization_id=organization.id,
                email_template_id=email_template_id,
            )
        )

    uploaded_data = upload_form.email_template_file.data.stream.read().decode("utf-8")
    session["uploaded_email_template_form"] = uploaded_data
    return redirect(
        url_for(
            "email_templates.create_or_edit",
            organization_id=organization.id,
            email_template_id=email_template_id,
        )
    )


@module.route("/<email_template_id>", methods=["GET", "POST"])
@acl.organization_roles_required("staff", "admin")
def detail(email_template_id):
    organization_id = request.args.get("organization_id", None)
    organization = models.Organization.objects.get(id=organization_id)
    email_template = models.EmailTemplate.objects.get(id=email_template_id)
    form = forms.email_templates.EmailTemplateFileForm()

    return render_template(
        "/email_templates/detail.html",
        email_template=email_template,
        organization=organization,
        form=form,
    )


@module.route(
    "/<organization_id>/views/<email_template_id>/delete", methods=["GET", "POST"]
)
@acl.organization_roles_required("staff", "admin")
def delete_email_template(organization_id, email_template_id):
    email_template = models.EmailTemplate.objects(id=email_template_id)
    organization = models.Organization.objects.get(id=organization_id)
    email_template.delete()

    return redirect(
        url_for("organizations.view_email_templates", organization_id=organization_id)
    )


@module.route(
    "/<organization_id>/email_templates/<email_template_id>/set_default/<is_default>",
    methods=["GET", "POST"],
)
@acl.organization_roles_required("admin", "staff")
def set_default_email_template(organization_id, email_template_id, is_default):
    organization = models.Organization.objects.get(id=organization_id)
    email_template = models.EmailTemplate.objects.get(id=email_template_id)

    action = is_default.lower()
    if action == "true":
        old_default_template = models.EmailTemplate.objects(
            organization=organization, is_default=True, type=email_template.type
        ).first()
        if old_default_template:
            old_default_template.is_default = False
            old_default_template.save()

        email_template.is_default = True
        email_template.save()
    else:
        email_template.is_default = False
        email_template.save()

    return redirect(
        url_for("organizations.view_email_templates", organization_id=organization_id)
    )


@module.route("/order/<order_id>/send_email", methods=["GET", "POST"])
@acl.organization_roles_required("staff", "admin")
def force_send_email(order_id):
    # division = models.Division.objects.get(id=division_id)
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects(id=order_id).first()

    job = redis_rq.redis_queue.queue.enqueue(
        email_utils.force_send_email_to_endorser,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for(
            "item_checkouts.bill_checkout",
            order_id=order_id,
            organization_id=organization.id,
        )
    )

    # return redirect(url_for("approve_orders.index", organization_id=organization.id))
