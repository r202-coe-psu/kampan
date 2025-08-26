import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

import mongoengine as me

from kampan.web import acl
from kampan.models import MASProject
from kampan.web.forms.procurement import MASProjectForm

module = Blueprint("mas", __name__, url_prefix="/mas")


@module.route("/")
@acl.organization_roles_required("admin")
def index():
    """List all MAS projects"""

    organization = current_user.user_setting.current_organization

    # Get query parameters for filtering
    fiscal_year = request.args.get("fiscal_year", "")
    expense_category = request.args.get("expense_category", "")

    # Build the query
    query = {"organization": organization, "status": "active"}

    if fiscal_year:
        query["fiscal_year"] = fiscal_year
    if expense_category:
        query["expense_category"] = expense_category

    # Get projects with pagination
    page = request.args.get("page", 1, type=int)
    per_page = 20

    projects_query = MASProject.objects(**query).order_by("-created_date")
    total_projects = projects_query.count()

    # Calculate offset for pagination
    offset = (page - 1) * per_page
    projects = projects_query.skip(offset).limit(per_page)

    # Create simple pagination info
    has_prev = page > 1
    has_next = offset + per_page < total_projects
    prev_num = page - 1 if has_prev else None
    next_num = page + 1 if has_next else None

    # Calculate summary statistics from all projects (not just current page)
    all_projects = projects_query
    total_budget = sum(p.budget for p in all_projects if p.budget)
    total_actual = sum(p.actual_payment for p in all_projects if p.actual_payment)
    total_remaining = (
        total_budget - total_actual
    )  # Get unique fiscal years and expense categories for filters
    fiscal_years = MASProject.objects(
        organization=organization, status="active"
    ).distinct("fiscal_year")
    expense_categories = MASProject.objects(
        organization=organization, status="active"
    ).distinct("expense_category")

    return render_template(
        "procurement/mas/index.html",
        projects=projects,
        organization=organization,
        page=page,
        per_page=per_page,
        total=total_projects,
        has_prev=has_prev,
        has_next=has_next,
        prev_num=prev_num,
        next_num=next_num,
        total_budget=total_budget,
        total_actual=total_actual,
        total_remaining=total_remaining,
        total_projects=total_projects,
        fiscal_years=sorted(fiscal_years),
        expense_categories=sorted(expense_categories),
        current_fiscal_year=fiscal_year,
        current_expense_category=expense_category,
    )


@module.route("/create", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create():
    """Create a new MAS project"""

    organization = current_user.user_setting.current_organization
    form = MASProjectForm()

    if form.validate_on_submit():
        project = MASProject()
        form.populate_obj(project)

        # Set additional fields
        project.organization = organization
        project.status = "active"
        project.created_date = datetime.datetime.utcnow()
        project.created_by = current_user._get_current_object()
        project.last_updated_date = datetime.datetime.utcnow()
        project.last_updated_by = current_user._get_current_object()

        try:
            project.save()
            flash("เพิ่มโครงการ MAS สำเร็จ", "success")
            return redirect(
                url_for("procurement.mas.index", organization_id=organization.id)
            )
        except Exception as e:
            flash(f"เกิดข้อผิดพลาด: {str(e)}", "error")

    return render_template(
        "procurement/mas/create.html",
        form=form,
        organization=organization,
    )


@module.route("/<mas_project_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def edit(mas_project_id):
    """Edit an existing MAS project"""

    organization = current_user.user_setting.current_organization

    # Get the project
    project = MASProject.objects(
        id=mas_project_id, organization=organization, status="active"
    ).first()

    if not project:
        abort(404)

    form = MASProjectForm(obj=project)

    if form.validate_on_submit():
        form.populate_obj(project)

        # Update metadata
        project.last_updated_date = datetime.datetime.utcnow()
        project.last_updated_by = current_user._get_current_object()

        try:
            project.save()
            flash("แก้ไขโครงการ MAS สำเร็จ", "success")
            return redirect(
                url_for("procurement.mas.index", organization_id=organization.id)
            )
        except Exception as e:
            flash(f"เกิดข้อผิดพลาด: {str(e)}", "error")

    return render_template(
        "procurement/mas/create.html",
        form=form,
        project=project,
        organization=organization,
        is_edit=True,
    )


@module.route("/<mas_project_id>")
@acl.organization_roles_required("admin")
def view(mas_project_id):
    """View a specific MAS project"""

    organization = current_user.user_setting.current_organization

    project = MASProject.objects(
        id=mas_project_id, organization=organization, status="active"
    ).first()

    if not project:
        abort(404)

    return render_template(
        "procurement/mas/view.html",
        project=project,
        organization=organization,
    )


@module.route("/<mas_project_id>/delete", methods=["POST"])
@acl.organization_roles_required("admin")
def delete(mas_project_id):
    """Delete a MAS project (soft delete)"""

    organization = current_user.user_setting.current_organization

    project = MASProject.objects(
        id=mas_project_id, organization=organization, status="active"
    ).first()

    if not project:
        abort(404)

    # Soft delete
    project.status = "deleted"
    project.last_updated_date = datetime.datetime.utcnow()
    project.last_updated_by = current_user._get_current_object()
    project.save()

    flash("ลบโครงการ MAS สำเร็จ", "success")
    return redirect(url_for("procurement.mas.index", organization_id=organization.id))
