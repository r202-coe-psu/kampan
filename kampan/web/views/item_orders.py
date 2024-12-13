from calendar import calendar
from pyexpat import model
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required, current_user
from flask_mongoengine import Pagination
import mongoengine as me

from kampan.web import forms, acl
from kampan import models

module = Blueprint("item_orders", __name__, url_prefix="/item_orders")


@module.route("/", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if current_user.has_organization_roles("admin", "supervisor supplier"):
        orders = models.OrderItem.objects(
            status__ne="disactive", organization=organization
        ).order_by("-created_date")
    else:
        orders = models.OrderItem.objects(
            status__ne="disactive", organization=organization, created_by=current_user
        ).order_by("-created_date")
    form = forms.inventories.SearchStartEndDateForm()
    form.item.label = "สถานะ"
    form.item.choices += [
        ("pending", "รอดำเนินการ"),
        ("approved", "อนุมัติ"),
        ("denied", "ปฏิเสธ"),
    ]
    if form.start_date.data == None and form.end_date.data != None:
        orders = orders.filter(
            created_date__lt=form.end_date.data,
        )

    elif form.start_date.data and form.end_date.data == None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
        )

    elif form.start_date.data != None and form.end_date.data != None:
        orders = orders.filter(
            created_date__gte=form.start_date.data,
            created_date__lt=form.end_date.data,
        )
    if form.item.data:
        orders = orders.filter(status__icontains=form.item.data)
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data or form.end_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=24)

    return render_template(
        "/item_orders/index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/order", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def order():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    form = forms.item_orders.OrderItemForm()
    division = (
        models.OrganizationUserRole.objects(
            user=current_user,
            organization=organization,
            status__ne="disactive",
        ).first()
    ).division
    if organization.get_organization_users():
        form.head_endorser.choices = [
            (str(org_user.user.id), org_user.user.get_name())
            for org_user in organization.get_organization_users(division)
            if ("endorser" in org_user.roles or "head" in org_user.roles)
        ]

        form.admin_approver.choices = [
            (str(org_user.user.id), org_user.user.get_name())
            for org_user in organization.get_organization_users(division)
            if ("admin" in org_user.roles)
        ]
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/item_orders/order.html", form=form, organization=organization
        )

    order = models.OrderItem()

    form.populate_obj(order)
    order.head_endorser = models.User.objects(id=form.head_endorser.data).first()
    order.admin_approver = models.User.objects(id=form.admin_approver.data).first()
    order.created_by = current_user._get_current_object()
    if current_user._get_current_object().get_current_division():
        order.division = current_user._get_current_object().get_current_division()

    order.organization = organization
    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))


@module.route("/<order_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def edit(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects().get(id=order_id)
    form = forms.item_orders.OrderItemForm(obj=order)
    division = (
        models.OrganizationUserRole.objects(
            user=current_user,
            organization=organization,
            status__ne="disactive",
        ).first()
    ).division
    form.head_endorser.choices = [
        (str(org_user.user.id), org_user.user.get_name())
        for org_user in organization.get_organization_users(division)
        if ("endorser" in org_user.roles or "head" in org_user.roles)
    ]
    form.admin_approver.choices = [
        (str(org_user.user.id), org_user.user.get_name())
        for org_user in organization.get_organization_users(division)
        if ("admin" in org_user.roles)
    ]
    if not form.validate_on_submit():
        print(form.errors)
        return render_template(
            "/item_orders/order.html", form=form, organization=organization
        )

    form.populate_obj(order)
    order.head_endorser = models.User.objects(id=form.head_endorser.data).first()
    order.admin_approver = models.User.objects(id=form.admin_approver.data).first()
    order.created_by = current_user._get_current_object()
    print(current_user._get_current_object().get_current_division())
    if current_user._get_current_object().get_current_division():
        order.division = current_user._get_current_object().get_current_division()
    order.organization = organization

    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))


@module.route("/<order_id>/delete")
@acl.organization_roles_required(
    "admin", "endorser", "staff", "head", "supervisor supplier"
)
def delete(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects().get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order)
    for checkout in checkouts:
        checkout.status = "disactive"
        checkout.save()
    order.status = "disactive"

    order.save()

    return redirect(url_for("item_orders.index", organization_id=organization_id))
