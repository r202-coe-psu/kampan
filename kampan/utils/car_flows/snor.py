"""ขั้นอนุมัติใบขอใช้รถของ org แบบ snor (กองกายภาพฯ)

เส้นทางกำหนดในโค้ดตามประเภทใบขอ ตอนยื่นจะตรึงเส้นทางลงคำขอ (route_snapshot)
เปลี่ยน SNOR_ROUTES ภายหลังแล้วคำขอเก่ายังเดินตามเส้นทางเดิม
"""

import datetime

from kampan import models

SNOR_STEP_LABELS = {
    "supervisor": "ผู้บังคับบัญชา",
    **dict(models.SNOR_POSITIONS),
}

SNOR_ROUTES = {
    ("domestic", "in_province"): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ],
    ("domestic", "out_of_province"): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
    ],
    ("airport", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
    ],
    ("welfare", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
    ],
    ("abroad", None): [
        "supervisor",
        "dispatcher",
        "vehicle_unit_head",
        "strategy_head",
        "physical_director",
        "vice_president_hatyai",
        "president",
    ],
}


class FlowError(Exception):
    pass


def route_for(request_type, province_scope):
    if request_type == "domestic":
        return list(SNOR_ROUTES[(request_type, province_scope)])
    return list(SNOR_ROUTES[(request_type, None)])


def step_label(step_key):
    return SNOR_STEP_LABELS.get(step_key, step_key)


def _log(app, action, actor, step_key="", comment=""):
    app.audit_logs.append(
        models.vehicle_applications.CarApplicationAuditLog(
            action=action,
            actor=actor,
            step_key=step_key,
            step_label=step_label(step_key) if step_key else "",
            comment=comment,
        )
    )


def submit(app, actor):
    app.route_snapshot = route_for(app.request_type, app.province_scope)
    app.current_step = 0
    app.status = "pending"
    _log(app, "submitted", actor)
    app.save()


def current_step_key(app):
    if app.status != "pending" or app.current_step >= len(app.route_snapshot):
        return None
    return app.route_snapshot[app.current_step]


def has_division_head(organization, division, excluding=None):
    """ฝ่ายมีหัวหน้า active อย่างน้อยหนึ่งคน (ไม่นับ excluding)"""
    if division is None:
        return False
    return any(
        member.user is not None and member.user != excluding
        for member in models.OrganizationUserRole.objects(
            organization=organization,
            status="active",
            roles="head",
            division=division,
        )
    )


def _is_division_head(app, user):
    if app.division is None:
        return False
    return (
        models.OrganizationUserRole.objects(
            organization=app.organization,
            user=user,
            status="active",
            roles="head",
            division=app.division,
        ).first()
        is not None
    )


def can_act(app, user):
    key = current_step_key(app)
    if key is None or user is None:
        return False
    if key == "supervisor":
        return _is_division_head(app, user)
    return models.CarFlowPosition.can_act(app.organization, key, user)


def approve(app, user, comment=""):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์อนุมัติขั้นนี้")

    key = current_step_key(app)
    app.step_approvals.append(
        models.vehicle_applications.StepApproval(
            step_key=key,
            label=step_label(key),
            decision="approved",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=comment,
        )
    )
    _log(app, "approved", user, step_key=key, comment=comment)
    app.current_step += 1
    if app.current_step >= len(app.route_snapshot):
        app.status = "active"
    app.save()


def deny(app, user, comment):
    if not can_act(app, user):
        raise FlowError("ไม่มีสิทธิ์ดำเนินการขั้นนี้")
    if not comment or not comment.strip():
        raise FlowError("ต้องระบุเหตุผลที่ไม่อนุมัติ")

    key = current_step_key(app)
    app.step_approvals.append(
        models.vehicle_applications.StepApproval(
            step_key=key,
            label=step_label(key),
            decision="denied",
            decided_by=user,
            decided_at=datetime.datetime.now(),
            comment=comment,
        )
    )
    _log(app, "denied", user, step_key=key, comment=comment)
    app.status = "denied"
    app.save()
