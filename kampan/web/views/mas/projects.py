import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user

import mongoengine as me

from kampan.web import acl
from kampan.models import MASProject
from kampan.models.organizations import Organization, OrganizationUserRole
from kampan.web.forms.mas import MASProjectForm

projects = Blueprint("projects", __name__)


@projects.route("/")
@acl.organization_roles_required("admin")
def index():
    """List all MAS projects for the organization"""

    organization = current_user.user_setting.current_organization

    # Get query parameters for filtering
    fiscal_year = request.args.get("fiscal_year", "")
    expense_category = request.args.get("expense_category", "")
    status = request.args.get("status", "")

    # Build query
    query = MASProject.objects(organization=organization)

    if fiscal_year:
        query = query.filter(fiscal_year=fiscal_year)
    if expense_category:
        query = query.filter(expense_category=expense_category)
    if status:
        query = query.filter(status=status)

    # Order by created date (newest first)
    projects = query.order_by("-created_date")

    # Get unique fiscal years for filter dropdown
    fiscal_years = MASProject.objects(organization=organization).distinct("fiscal_year")
    fiscal_years = [year for year in fiscal_years if year]  # Remove empty values
    fiscal_years.sort(reverse=True)

    # Calculate summary statistics
    total_budget = sum(project.budget for project in projects)
    total_actual = sum(project.actual_payment for project in projects)
    total_remaining = total_budget - total_actual

    return render_template(
        "mas/projects/index.html",
        projects=projects,
        organization=organization,
        fiscal_years=fiscal_years,
        current_fiscal_year=fiscal_year,
        current_expense_category=expense_category,
        current_status=status,
        total_budget=total_budget,
        total_actual=total_actual,
        total_remaining=total_remaining,
        expense_categories=MASProject._fields["expense_category"].choices,
        status_choices=MASProject._fields["status"].choices,
    )


@projects.route("/create", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def create():
    """Create a new MAS project"""

    organization = current_user.user_setting.current_organization

    form = MASProjectForm()

    # Set choices for responsible_by field
    form.responsible_by.queryset = OrganizationUserRole.objects(
        organization=organization
    )

    if form.validate_on_submit():
        try:
            # Create new MAS project
            project = MASProject(
                mas_code=form.mas_code.data,
                expense_category=form.expense_category.data,
                expense_subcategory=form.expense_subcategory.data,
                project_name=form.project_name.data,
                project_description=form.project_description.data,
                amount=form.amount.data,
                budget=form.budget.data,
                actual_payment=form.actual_payment.data or 0,
                fiscal_year=form.fiscal_year.data,
                start_date=form.start_date.data,
                end_date=form.end_date.data,
                status=form.status.data,
                organization=organization,
                responsible_by=form.responsible_by.data,
                created_by=current_user._get_current_object(),
                last_updated_by=current_user._get_current_object(),
            )

            project.save()
            flash("สร้างโครงการ MAS สำเร็จ", "success")
            return redirect(
                url_for("mas.projects.index", organization_id=organization.id)
            )

        except me.NotUniqueError:
            flash("รหัสแหล่งเงินนี้มีอยู่แล้ว กรุณาใช้รหัสอื่น", "error")
        except Exception as e:
            flash(f"เกิดข้อผิดพลาด: {str(e)}", "error")

    return render_template(
        "mas/projects/create.html", form=form, organization=organization
    )


@projects.route("/<project_id>/edit", methods=["GET", "POST"])
@acl.organization_roles_required("admin")
def edit(project_id):
    """Edit an existing MAS project"""

    organization = current_user.user_setting.current_organization

    try:
        project = MASProject.objects(id=project_id, organization=organization).get()
    except MASProject.DoesNotExist:
        abort(404)

    form = MASProjectForm(obj=project)

    # Set choices for responsible_by field
    form.responsible_by.queryset = OrganizationUserRole.objects(
        organization=organization
    )

    if form.validate_on_submit():
        try:
            # Update project
            project.mas_code = form.mas_code.data
            project.expense_category = form.expense_category.data
            project.expense_subcategory = form.expense_subcategory.data
            project.project_name = form.project_name.data
            project.project_description = form.project_description.data
            project.amount = form.amount.data
            project.budget = form.budget.data
            project.actual_payment = form.actual_payment.data or 0
            project.fiscal_year = form.fiscal_year.data
            project.start_date = form.start_date.data
            project.end_date = form.end_date.data
            project.status = form.status.data
            project.responsible_by = form.responsible_by.data
            project.last_updated_by = current_user._get_current_object()
            project.updated_date = datetime.datetime.now()

            project.save()
            flash("แก้ไขโครงการ MAS สำเร็จ", "success")
            return redirect(
                url_for(
                    "mas.projects.view",
                    organization_id=organization.id,
                    project_id=project.id,
                )
            )

        except me.NotUniqueError:
            flash("รหัสแหล่งเงินนี้มีอยู่แล้ว กรุณาใช้รหัสอื่น", "error")
        except Exception as e:
            flash(f"เกิดข้อผิดพลาด: {str(e)}", "error")

    return render_template(
        "mas/projects/edit.html", form=form, project=project, organization=organization
    )


@projects.route("/<project_id>")
@acl.organization_roles_required("admin")
def view(project_id):
    """View MAS project details"""

    organization = current_user.user_setting.current_organization

    try:
        project = MASProject.objects(id=project_id, organization=organization).get()
    except MASProject.DoesNotExist:
        abort(404)

    return render_template(
        "mas/projects/view.html", project=project, organization=organization
    )


@projects.route("/<project_id>/delete", methods=["POST"])
@acl.organization_roles_required("admin")
def delete(project_id):
    """Delete an existing MAS project"""

    organization = current_user.user_setting.current_organization

    try:
        project = MASProject.objects(id=project_id, organization=organization).get()
        project.delete()
        flash("ลบโครงการ MAS สำเร็จ", "success")
    except MASProject.DoesNotExist:
        flash("ไม่พบโครงการที่ต้องการลบ", "error")
    except Exception as e:
        flash(f"เกิดข้อผิดพลาด: {str(e)}", "error")

    return redirect(url_for("mas.projects.index", organization_id=organization.id))


@projects.route("/dashboard")
@acl.organization_roles_required("admin")
def dashboard():
    """MAS Dashboard with summary statistics"""

    organization = current_user.user_setting.current_organization

    # Get current fiscal year or use current Buddhist year
    current_buddhist_year = datetime.datetime.now().year + 543
    fiscal_year = request.args.get("fiscal_year", str(current_buddhist_year))

    # Get all projects for the fiscal year
    projects = MASProject.objects(organization=organization, fiscal_year=fiscal_year)

    # Calculate summary by expense category
    category_summary = {}
    for category_code, category_name in MASProject._fields["expense_category"].choices:
        category_projects = projects.filter(expense_category=category_code)
        total_budget = sum(p.budget for p in category_projects)
        total_actual = sum(p.actual_payment for p in category_projects)

        category_summary[category_code] = {
            "name": category_name,
            "total_budget": total_budget,
            "total_actual": total_actual,
            "remaining": total_budget - total_actual,
            "utilization_percentage": (
                (total_actual / total_budget * 100) if total_budget > 0 else 0
            ),
            "project_count": category_projects.count(),
        }

    # Get fiscal years for dropdown
    fiscal_years = MASProject.objects(organization=organization).distinct("fiscal_year")
    fiscal_years = [year for year in fiscal_years if year]
    fiscal_years.sort(reverse=True)

    # Overall totals
    total_budget = sum(p.budget for p in projects)
    total_actual = sum(p.actual_payment for p in projects)
    total_remaining = total_budget - total_actual

    return render_template(
        "mas/projects/dashboard.html",
        organization=organization,
        fiscal_year=fiscal_year,
        fiscal_years=fiscal_years,
        category_summary=category_summary,
        total_budget=total_budget,
        total_actual=total_actual,
        total_remaining=total_remaining,
        total_projects=projects.count(),
    )
