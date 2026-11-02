import mongoengine as me
from flask import Blueprint, abort, render_template

from kampan import models
from kampan.web import acl, forms

module = Blueprint("overview", __name__, url_prefix="/<organization_id>")


def count_members_by_division(organization):
    """นับสมาชิกที่ยังไม่ถูกนำออก แยกตามแผนก คืน {division_id หรือ None: {"total", "pending"}}"""
    counts = {}
    rows = models.OrganizationUserRole.objects(
        organization=organization, status__ne="disactive"
    ).aggregate(
        [
            {
                "$group": {
                    "_id": {"division": "$division", "status": "$status"},
                    "count": {"$sum": 1},
                }
            }
        ]
    )
    for row in rows:
        division = row["_id"].get("division")
        division_id = getattr(division, "id", division)
        bucket = counts.setdefault(
            str(division_id) if division_id else None, {"total": 0, "pending": 0}
        )
        bucket["total"] += row["count"]
        if row["_id"].get("status") == "pending":
            bucket["pending"] += row["count"]
    return counts


@module.route("/")
@acl.organization_roles_required("admin")
def index(organization_id):
    try:
        organization = models.Organization.objects(
            id=organization_id, status="active"
        ).first()
    except me.ValidationError:
        organization = None
    if not organization:
        abort(404)

    counts = count_members_by_division(organization)
    empty = {"total": 0, "pending": 0}
    division_rows = [
        {"division": division, **counts.get(str(division.id), empty)}
        for division in models.Division.objects(
            organization=organization, status="active"
        ).order_by("name")
    ]
    active_division_ids = {str(row["division"].id) for row in division_rows}
    # สมาชิกที่ไม่มีแผนก หรือแผนกถูกลบไปแล้ว ถือว่ายังไม่ได้ระบุแผนก
    unassigned = {"total": 0, "pending": 0}
    for division_id, bucket in counts.items():
        if division_id not in active_division_ids:
            unassigned["total"] += bucket["total"]
            unassigned["pending"] += bucket["pending"]

    return render_template(
        "/organizations/overview.html",
        division_form=forms.divisions.DivisionForm(formdata=None),
        organization=organization,
        division_rows=division_rows,
        unassigned=unassigned,
        total_members=sum(bucket["total"] for bucket in counts.values()),
    )
