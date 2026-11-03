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


def _display_user(user):
    return user.get_resources_fullname_th() if user else ""


def _change(field, label, old, new):
    return {"field": field, "label": label, "old": old, "new": new}


def _audit(car_application, action, user, step=None, comment="", changes=None):
    car_application.audit_logs.append(
        models.vehicle_applications.CarApplicationAuditLog(
            action=action,
            actor=user,
            created_date=datetime.datetime.now(),
            step_key=(step or {}).get("key", ""),
            step_label=(step or {}).get("label", ""),
            comment=comment or "",
            changes=changes or [],
        )
    )


def record_submitted(car_application, user):
    _audit(car_application, "submitted", user)


def can_edit(car_application, user):
    """ผู้ยื่นแก้คำขอได้จนกว่าผู้อนุมัติคนแรกจะดำเนินการ"""
    return (
        car_application.status == "pending"
        and not car_application.step_approvals
        and car_application.creator is not None
        and car_application.creator.id == user.id
    )


def record_edited(car_application, user, changes):
    _audit(car_application, "edited", user, changes=changes)


def approve(car_application, user, comment="", car=None, driver=None):
    step = current_step_def(car_application)
    if step is None:
        raise ValueError("no step to approve")

    changes = []
    if step.get("assigns_vehicle"):
        if car is None:
            raise ValueError("car is required on a vehicle assigning step")
        old_car = car_application.car.license_plate if car_application.car else ""
        old_driver = _display_user(car_application.driver)
        car_application.car = car
        car_application.assigned_vehicle_type = car.vehicle_type
        car_application.driver = driver
        changes.append(_change("car", "รถ", old_car, car.license_plate or ""))
        changes.append(_change("driver", "พนักงานขับรถ", old_driver, _display_user(driver)))

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
        changes.append(_change("status", "สถานะ", car_application.status, "active"))
        car_application.status = "active"
    _audit(car_application, "approved", user, step, comment, changes)
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
    _audit(
        car_application, "denied", user, step, reason,
        [_change("status", "สถานะ", car_application.status, "denied")],
    )
    car_application.status = "denied"
    car_application.denied_reason = reason
    car_application.save()
    return car_application


def can_view(car_application, user, organization):
    """ผู้ที่เห็นในรายการคำขอ, ผู้ที่อนุมัติขั้นปัจจุบันได้ หรือเคยตัดสินขั้นใดขั้นหนึ่ง"""
    if car_application.organization.id != organization.id:
        return False
    if visible_requests(user, organization).filter(id=car_application.id).first():
        return True
    if any(a.decided_by and a.decided_by.id == user.id for a in car_application.step_approvals):
        return True
    return can_act(car_application, user, organization)


def _approver_text(step):
    if step.get("approver_type") == "user":
        user = models.User.objects(id=step.get("user")).first() if step.get("user") else None
        return _display_user(user)
    role = dict(models.organizations.ORGANIZATION_ROLES).get(step.get("role"), step.get("role") or "")
    return f"{role} (ฝ่ายเดียวกับผู้ขอ)" if step.get("same_division") else role


def step_progress(car_application):
    """สถานะของแต่ละขั้นสำหรับ stepper: done / current / denied / waiting / skipped"""
    steps = (car_application.template_snapshot or {}).get("steps", [])
    if not steps:
        return _legacy_step_progress(car_application)
    decisions = {a.step_key: a for a in car_application.step_approvals}
    progress = []
    for index, step in enumerate(steps):
        decision = decisions.get(step["key"])
        if decision and decision.decision == "approved":
            state = "done"
        elif decision and decision.decision == "denied":
            state = "denied"
        elif car_application.status == "pending" and index == car_application.current_step:
            state = "current"
        elif car_application.status in ("denied", "disactive"):
            state = "skipped"
        else:
            state = "waiting"
        progress.append(
            {
                "index": index + 1,
                "label": step.get("label") or step["key"],
                "approver": _approver_text(step),
                "assigns_vehicle": bool(step.get("assigns_vehicle")),
                "state": state,
                "decided_by": _display_user(decision.decided_by) if decision else "",
                "decided_at": decision.decided_at if decision else None,
                "comment": decision.comment if decision else "",
            }
        )
    return progress


def _legacy_step_progress(car_application):
    """คำขอแบบเดิม (ไม่มี template): หัวหน้าฝ่าย → พัสดุ → ผอ. (เฉพาะไปต่างจังหวัด)"""
    steps = [("header", "หัวหน้าฝ่าย", car_application.header_approval),
             ("admin", "เจ้าหน้าที่พัสดุ", car_application.admin_approval)]
    if car_application.using_type == "out of town":
        steps.append(("director", "ผู้อำนวยการ", car_application.director_approval))
    status = car_application.status
    progress = []
    for index, (key, label, approval) in enumerate(steps):
        if approval and approval.approved_at:
            state = "done"
        elif status == f"denied by {key}":
            state = "denied"
        elif status == f"pending on {key}":
            state = "current"
        elif status.startswith("denied") or status == "disactive":
            state = "skipped"
        elif status in ("active", "completed"):
            state = "done"
        else:
            state = "waiting"
        progress.append(
            {
                "index": index + 1,
                "label": label,
                "approver": label,
                "assigns_vehicle": key == "admin",
                "state": state,
                "decided_by": _display_user(approval.approved_by) if approval else "",
                "decided_at": approval.approved_at if approval else None,
                "comment": "",
            }
        )
    return progress


def _search_text(car_application):
    creator = car_application.creator
    parts = [
        car_application.location,
        car_application.request_reason,
        car_application.form_template.name if car_application.form_template else "",
        car_application.car.license_plate if car_application.car else "",
        car_application.division.name if car_application.division else "",
        creator.first_name if creator else "",
        creator.last_name if creator else "",
        _display_user(creator),
        _display_user(car_application.driver),
    ]
    return " ".join(str(p) for p in parts if p).lower()


def search(car_applications, q="", status="", template_id=""):
    """กรองรายการคำขอด้วยข้อความ (สถานที่/เหตุผล/แบบฟอร์ม/ทะเบียน/ฝ่าย/ผู้ขอ/คนขับ), สถานะ และแบบฟอร์ม"""
    q = (q or "").strip().lower()
    results = []
    for car_application in car_applications:
        if status and car_application.status != status:
            continue
        if template_id and (
            not car_application.form_template or str(car_application.form_template.id) != template_id
        ):
            continue
        if q and q not in _search_text(car_application):
            continue
        results.append(car_application)
    return results
