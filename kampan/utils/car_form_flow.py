import datetime

import mongoengine as me

from kampan import models


def current_step_def(car_application):
    steps = (car_application.template_snapshot or {}).get("steps", [])
    index = car_application.current_step
    if car_application.status != "pending" or index >= len(steps):
        return None
    return steps[index]


def _user_division(user, organization):
    member = models.OrganizationUserRole.objects(
        user=user, organization=organization, status__ne="disactive"
    ).first()
    return member.division if member else None


def can_act(car_application, user, organization):
    step = current_step_def(car_application)
    if step is None:
        return False

    if step.get("approver_type") == "user":
        return str(step.get("user")) == str(user.id)

    if step.get("role") not in user.get_organization_roles(organization):
        return False

    if step.get("same_division"):
        division = _user_division(user, organization)
        return (
            division is not None
            and car_application.division is not None
            and division.id == car_application.division.id
        )
    return True


def pending_for(user, organization):
    pending = models.vehicle_applications.CarApplication.objects(
        organization=organization,
        form_template__ne=None,
        status="pending",
    ).order_by("created_date")
    return [c for c in pending if can_act(c, user, organization)]


VIEW_ALL_ROLES = ("admin", "director", "endorser", "supervisor supplier")


def visible_requests(user, organization):
    """คำขอจาก template ที่ผู้ใช้ดูได้: admin/ผอ./ผู้อนุมัติ/หัวหน้าพัสดุ เห็นทั้ง org,
    หัวหน้าฝ่ายเห็นของฝ่ายตัวเองและของตัวเอง, คนอื่นเห็นเฉพาะที่ตัวเองยื่น"""
    requests = models.vehicle_applications.CarApplication.objects(
        organization=organization, form_template__ne=None
    ).order_by("-created_date")
    if user.has_organization_roles(*VIEW_ALL_ROLES, organization=organization):
        return requests
    division = _user_division(user, organization)
    if division and "head" in user.get_organization_roles(organization):
        return requests.filter(me.Q(division=division) | me.Q(creator=user))
    return requests.filter(creator=user)


def approve(car_application, user, comment="", car=None, driver=None):
    step = current_step_def(car_application)
    if step is None:
        raise ValueError("no step to approve")

    if step.get("assigns_vehicle"):
        if car is None:
            raise ValueError("car is required on a vehicle assigning step")
        car_application.car = car
        car_application.assigned_vehicle_type = car.vehicle_type
        car_application.driver = driver

    car_application.step_approvals.append(
        models.vehicle_applications.StepApproval(
            step_key=step["key"],
            label=step.get("label"),
            decision="approved",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=comment,
        )
    )
    car_application.current_step += 1
    if car_application.current_step >= len(car_application.template_snapshot["steps"]):
        car_application.status = "active"
    car_application.save()
    return car_application


def deny(car_application, user, reason):
    step = current_step_def(car_application)
    if step is None:
        raise ValueError("no step to deny")

    car_application.step_approvals.append(
        models.vehicle_applications.StepApproval(
            step_key=step["key"],
            label=step.get("label"),
            decision="denied",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=reason,
        )
    )
    car_application.status = "denied"
    car_application.denied_reason = reason
    car_application.save()
    return car_application
