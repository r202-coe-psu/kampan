import mongoengine as me
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from flask_mongoengine import Pagination

from kampan import models
from kampan.web import acl, forms

module = Blueprint("system_users", __name__, url_prefix="/system/users")

EDITABLE_USER_ROLES = [role for role, _ in forms.user_roles.USER_ROLE_CHOICES if role]


def editable_role_choices():
    return [choice for choice in forms.user_roles.USER_ROLE_CHOICES if choice[0]]


def summarize_roles():
    """นับผู้ใช้ทั้งระบบแยกตาม role คนหนึ่งมีได้หลาย role จึงนับซ้ำได้"""
    counts = {}
    rows = models.User.objects().aggregate(
        [
            {"$project": {"roles": {"$ifNull": ["$roles", []]}}},
            {"$unwind": {"path": "$roles", "preserveNullAndEmptyArrays": True}},
            {"$group": {"_id": "$roles", "count": {"$sum": 1}}},
        ]
    )
    for row in rows:
        counts[row["_id"] or forms.user_roles.NO_ROLE] = row["count"]

    labels = dict(forms.user_roles.USER_ROLE_CHOICES)
    known = [role for role, _ in forms.user_roles.USER_ROLE_CHOICES if role]
    unknown = sorted(role for role in counts if role not in known + [forms.user_roles.NO_ROLE])
    summary = [
        {"role": role, "label": labels[role], "count": counts.get(role, 0), "filterable": True}
        for role in known
    ]
    # role ที่ไม่มีในรายการตัวเลือก กรองจากหน้านี้ไม่ได้ แต่ยังต้องเห็นว่ามีอยู่
    summary += [
        {"role": role, "label": role, "count": counts[role], "filterable": False}
        for role in unknown
    ]
    summary.append(
        {
            "role": forms.user_roles.NO_ROLE,
            "label": "ยังไม่มีระดับ",
            "count": counts.get(forms.user_roles.NO_ROLE, 0),
            "filterable": True,
        }
    )
    return summary


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
    if role == forms.user_roles.NO_ROLE:
        query &= me.Q(roles__size=0) | me.Q(roles__exists=False)
    elif role:
        query &= me.Q(roles=role)

    users = models.User.objects(query).order_by("last_name", "first_name")
    page = max(request.args.get("page", default=1, type=int), 1)

    return render_template(
        "/organizations/system/users/index.html",
        paginated_users=Pagination(users, page=page, per_page=30),
        form=search_form,
        role_labels=dict(forms.user_roles.USER_ROLE_CHOICES),
        role_summary=summarize_roles(),
        total_users=models.User.objects().count(),
        selected_role=role,
        organization=current_user.get_viewing_organization(),
    )


@module.route("/<user_id>/edit-roles", methods=["GET", "POST"])
@acl.roles_required("admin")
def edit_roles(user_id):
    user = models.User.objects(id=user_id).first()
    if not user:
        abort(404)

    form = forms.user_roles.UserRolesForm(obj=user)
    form.roles.choices = editable_role_choices()

    if not form.validate_on_submit():
        return render_template(
            "/organizations/system/users/edit_roles.html",
            form=form,
            user=user,
            organization=current_user.get_viewing_organization(),
        )

    # role เก่าที่ไม่อยู่ในรายการตัวเลือกแล้ว ต้องคงไว้ ไม่ให้หายตอนบันทึก
    kept_roles = [role for role in user.roles if role not in EDITABLE_USER_ROLES]
    user.roles = form.roles.data + kept_roles
    user.save()

    flash(f"บันทึกระดับผู้ใช้ของ {user.get_name()} แล้ว", "success")
    return redirect(url_for("organizations.system_users.index"))
