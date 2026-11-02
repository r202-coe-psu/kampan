import mongoengine as me
from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user
from flask_mongoengine import Pagination

from kampan import models
from kampan.web import acl, forms

module = Blueprint("system_users", __name__, url_prefix="/system/users")

EDITABLE_USER_ROLES = [
    ("admin", "Admin"),
    ("supervisor", "Supervisor"),
    ("user", "User"),
]


@module.route("/")
@acl.roles_required("admin")
def index():
    search_form = forms.user_roles.UserRolesSearchForm(request.args)
    if not search_form.validate():
        abort(400, description="Invalid user search filters")

    query = me.Q()
    email = (search_form.email.data or "").strip()
    name = (search_form.name.data or "").strip()
    role = (search_form.role.data or "").strip()

    if email:
        query &= me.Q(email__icontains=email)
    if name:
        query &= (
            me.Q(first_name__icontains=name)
            | me.Q(last_name__icontains=name)
            | me.Q(resources__psu__display_name_th__icontains=name)
            | me.Q(resources__psu__display_name__icontains=name)
        )
    if role:
        query &= me.Q(roles=role)

    users = models.User.objects(query).order_by("last_name", "first_name")
    page = max(request.args.get("page", default=1, type=int), 1)

    return render_template(
        "/organizations/system/users/index.html",
        paginated_users=Pagination(users, page=page, per_page=30),
        form=search_form,
        role_labels=dict(forms.user_roles.USER_ROLE_CHOICES),
        organization=current_user.get_viewing_organization(),
    )


@module.route("/<user_id>/edit-roles", methods=["GET", "POST"])
@acl.roles_required("admin")
def edit_roles(user_id):
    user = models.User.objects(id=user_id).first()
    if not user:
        abort(404)

    form = forms.user_roles.UserRolesForm(obj=user)
    form.roles.choices = EDITABLE_USER_ROLES

    if not form.validate_on_submit():
        return render_template(
            "/organizations/system/users/edit_roles.html",
            form=form,
            user=user,
            organization=current_user.get_viewing_organization(),
        )

    user.roles = form.roles.data
    user.save()

    return redirect(url_for("organizations.system_users.index"))
