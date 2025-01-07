from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    current_app,
)
from flask_login import current_user
from kampan.models import inventories
from kampan.web import forms, acl
from kampan import models, utils
from flask_mongoengine import Pagination
import datetime
from .. import redis_rq

module = Blueprint("approve_orders", __name__, url_prefix="/approve_orders")


@module.route("/item_checkouts", methods=["GET", "POST"])
@acl.organization_roles_required("admin", "endorser")
def item_checkouts():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order_id = request.args.get("order_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=30)
    return render_template(
        "/approve_orders/item_checkouts.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        checkouts=checkouts,
        organization=organization,
    )


# ----------------- Endorser -----------------


@module.route("/endorser", methods=["GET", "POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        approval_status="pending",
        status="pending",
        organization=organization,
        head_endorser=current_user,
    )

    form = forms.inventories.SearchStartEndDateForm()
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
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/endorser/endorser_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/endorser_approve", methods=["GET"])
@acl.organization_roles_required("head", "endorser")
def endorser_approve(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")

    for checkout in checkout_items:
        item = checkout.item
        quantity = (checkout.set_ * item.piece_per_set) + checkout.piece
        if quantity > item.get_amount_pieces():
            checkout.piece = item.get_amount_pieces()
            checkout.quantity = item.get_amount_pieces()
        checkout.save()

    order.status = "pending on supervisor supplier"
    order.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_supervisor_supplier,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_head_endorser_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for("approve_orders.endorser_index", organization_id=organization_id)
    )


@module.route("/<order_id>/endorser_denied", methods=["GET", "POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_denied(order_id):
    organization_id = request.args.get("organization_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    order.approval_status = "denied"
    order.status = "denied"
    order.denied_reason = request.args.get("reason", default="", type=str)
    order.save()

    for checkout in checkout_items:
        checkout.status = "denied"
        checkout.save()

    return redirect(
        url_for("approve_orders.endorser_index", organization_id=organization_id)
    )


@module.route("/<order_id>/endorser_approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("head", "endorser")
def endorser_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/endorser/endorser_approve_detail.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


# ----------------- Supervisor Supplier -----------------


@module.route("/supervisor_supplier", methods=["GET", "POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        approval_status="pending",
        status="pending on supervisor supplier",
        organization=organization,
    )

    form = forms.inventories.SearchStartEndDateForm()
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
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/supervisor_supplier/supervisor_supplier_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/supervisor_supplier_approve", methods=["GET"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approve(order_id):
    organization_id = request.args.get("organization_id")
    order = models.OrderItem.objects.get(id=order_id)
    order.status = "pending on admin"
    order.save()

    return redirect(
        url_for(
            "approve_orders.supervisor_supplier_index", organization_id=organization_id
        )
    )


@module.route("/<order_id>/supervisor_supplier_denied", methods=["GET", "POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_denied(order_id):
    organization_id = request.args.get("organization_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    order.approval_status = "denied"
    order.status = "denied"
    order.denied_reason = request.args.get("reason", default="", type=str)

    order.save()

    for checkout in checkout_items:
        checkout.status = "denied"
        checkout.save()

    return redirect(
        url_for(
            "approve_orders.supervisor_supplier_index",
            organization_id=organization_id,
        )
    )


@module.route(
    "/<order_id>/supervisor_supplier_approved_detail", methods=["GET", "POST"]
)
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/supervisor_supplier/supervisor_supplier_approve_detail.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


@module.route("/<order_id>/supervisor_supplier_approve_page", methods=["GET", "POST"])
@acl.organization_roles_required("supervisor supplier")
def supervisor_supplier_approve_page(order_id):
    form = forms.approve_orders.SupplierApproveForm()
    order = models.OrderItem.objects.get(id=order_id)
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()

    form.admin_approver.choices = [
        (str(org_user.user.id), org_user.user.get_name())
        for org_user in organization.get_organization_users()
        if ("admin" in org_user.roles)
    ]
    if not form.validate_on_submit():
        if order.admin_approver:
            form.admin_approver.data = str(order.admin_approver.id)
        return render_template(
            "/approve_orders/supervisor_supplier/supervisor_supplier_approve_page.html",
            order_id=order_id,
            form=form,
            order=order,
            organization=organization,
        )
    order.admin_approver = models.User.objects(id=form.admin_approver.data).first()
    order.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_admin,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_supervisor_supplier_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for(
            "approve_orders.supervisor_supplier_approve",
            organization_id=organization_id,
            order_id=order_id,
        )
    )


# ----------------- Admin -----------------


@module.route("/admin", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    orders = models.OrderItem.objects(
        approval_status="pending",
        status="pending on admin",
        organization=organization,
        admin_approver=current_user,
    )

    form = forms.inventories.SearchStartEndDateForm()
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
    page = request.args.get("page", default=1, type=int)
    if form.start_date.data:
        page = 1
    paginated_orders = Pagination(orders, page=page, per_page=100)
    return render_template(
        "/approve_orders/admin/admin_approve_index.html",
        paginated_orders=paginated_orders,
        form=form,
        orders=orders,
        organization=organization,
    )


@module.route("/<order_id>/admin_approve", methods=["GET"])
@acl.organization_roles_required("admin")
def admin_approve(order_id):
    organization_id = request.args.get("organization_id")

    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")

    for checkout in checkout_items:
        checkout.status = "active"
        # checkout.save()
        item = checkout.item
        quantity = (checkout.set_ * item.piece_per_set) + checkout.piece
        if quantity > item.get_amount_pieces():
            return redirect(
                url_for(
                    "approve_orders.admin_approved_detail",
                    organization_id=organization_id,
                    order_id=order_id,
                    error_message=True,
                )
            )
        inventories = models.Inventory.objects(item=item, remain__gt=0)
        for inventory in inventories:
            if inventory.remain >= quantity:
                inventory.remain -= quantity
                quantity = 0
            else:
                quantity -= inventory.remain
                inventory.remain = 0

            inventory.save()
            checkout.inventories.append(inventory)
            if quantity <= 0:
                break
        checkout.save()
    order.approval_status = "approved"
    order.status = "approved"
    order.approved_date = datetime.datetime.now()
    order.save()
    return redirect(
        url_for("approve_orders.admin_index", organization_id=organization_id)
    )


@module.route("/<order_id>/admin_denied", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_denied(order_id):
    organization_id = request.args.get("organization_id")
    order = models.OrderItem.objects.get(id=order_id)
    checkout_items = models.CheckoutItem.objects(order=order, status="active")
    order.approval_status = "denied"
    order.status = "denied"
    order.denied_reason = request.args.get("reason", default="", type=str)

    order.save()

    for checkout in checkout_items:
        checkout.status = "denied"
        checkout.save()

    return redirect(
        url_for(
            "approve_orders.admin_index",
            organization_id=organization_id,
        )
    )


@module.route("/<order_id>/admin_approved_detail", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_approved_detail(order_id):
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    order = models.OrderItem.objects.get(id=order_id)
    checkouts = models.CheckoutItem.objects(order=order, status="active")
    page = request.args.get("page", default=1, type=int)
    paginated_checkouts = Pagination(checkouts, page=page, per_page=100)
    return render_template(
        "/approve_orders/admin/admin_approve_detail.html",
        paginated_checkouts=paginated_checkouts,
        order_id=order_id,
        order=order,
        checkouts=checkouts,
        organization=organization,
    )


@module.route("/<order_id>/admin_approve_page", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def admin_approve_page(order_id):
    form = forms.approve_orders.AdminApproveForm()
    order = models.OrderItem.objects.get(id=order_id)
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not form.validate_on_submit():
        return render_template(
            "/approve_orders/admin/admin_approve_page.html",
            order_id=order_id,
            form=form,
            order=order,
            organization=organization,
        )
    order.sent_item_date = form.sent_item_date.data
    order.save()
    job = redis_rq.redis_queue.queue.enqueue(
        utils.email_utils.force_send_email_to_staff,
        args=(order, current_user._get_current_object(), current_app.config),
        job_id=f"force_sent_email_staff_order_{order.id}",
        timeout=600,
        job_timeout=600,
    )
    print("=====> submit", job.get_id())
    return redirect(
        url_for(
            "approve_orders.admin_approve",
            organization_id=organization_id,
            order_id=order_id,
        )
    )
