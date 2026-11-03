"""การอนุมัติคำขอซื้อขอจ้าง (requisition_action) ต้องตรวจสิทธิ์ ลำดับขั้น และการกดซ้ำฝั่ง server"""

import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from flask import g

from kampan import models
from kampan.web import redis_rq


@pytest.fixture(autouse=True)
def mock_queue():
    queue = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", queue, create=True):
        yield queue


@pytest.fixture
def setup(app, create_org, create_user, assign_user_to_org):
    """หน่วยงาน 1 แห่ง ฝ่าย 2 ฝ่าย และผู้ใช้ครบทุกบทบาทในการอนุมัติ"""
    with app.app_context():
        org = create_org("Org A")
        division = models.Division(name="ฝ่าย A", organization=org)
        division.save()
        other_division = models.Division(name="ฝ่าย B", organization=org)
        other_division.save()

        def member(name, roles, member_division=None):
            user = create_user(name, "Member")
            role = assign_user_to_org(user, org, roles=roles)
            if member_division:
                role.division = member_division
                role.save()
            return user, role

        staff, staff_role = member("Staff", ["staff"], division)
        head, _ = member("Head", ["head"], division)
        other_head, _ = member("OtherHead", ["head"], other_division)
        no_division_head, _ = member("NoDivHead", ["head"])
        admin, _ = member("Admin", ["admin"])
        manager, manager_role = member("Manager", ["manager"])
        other_manager, _ = member("OtherManager", ["manager"])

        requisition = models.Requisition(
            requisition_code="0001/2569",
            organization=org,
            purchaser=staff_role,
            start_date=datetime.datetime(2026, 11, 1),
            items=[
                models.RequisitionItem(
                    product_name="เครื่องพิมพ์",
                    quantity=1,
                    category="product",
                    amount=Decimal("10000.00"),
                )
            ],
            created_by=staff,
        )
        requisition.save()

        mas = models.MAS(
            organization=org,
            year=2569,
            mas_code="MAS-A",
            description="งบ A",
            direction="-",
            amount=Decimal("100000.00"),
            remaining_amount=Decimal("100000.00"),
            reservable_amount=Decimal("100000.00"),
        )
        mas.save()

        return {
            "org": org,
            "staff": staff,
            "head": head,
            "other_head": other_head,
            "no_division_head": no_division_head,
            "admin": admin,
            "manager": manager,
            "manager_role": manager_role,
            "other_manager": other_manager,
            "requisition": requisition,
            "mas": mas,
        }


def switch_user(client, login_as, user):
    # app_context ของเทสต์ครอบทุก request ทำให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
    g.pop("_login_user", None)
    login_as(client, user)


def post_action(client, login_as, user, setup, approver_role, action="approved", **extra):
    switch_user(client, login_as, user)
    data = {"approver_role": approver_role, "action": action, **extra}
    if action == "rejected":
        data.setdefault("reason", "ไม่อยู่ในแผน")
    return client.post(
        f"/procurement/requisitions/{setup['requisition'].id}/action?organization_id={setup['org'].id}",
        data=data,
    )


def admin_approve_data(setup, amount="10000.00", mas=None):
    mas = mas or setup["mas"]
    return {
        "fund_ids": str(mas.id),
        f"fund_amounts[{mas.id}]": amount,
        "manager": str(setup["manager_role"].id),
    }


def roles_in_history(requisition):
    requisition.reload()
    return [(h.approver_role, h.action) for h in requisition.approval_history]


def test_staff_cannot_approve_as_head(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["staff"], setup, "head")

        assert roles_in_history(setup["requisition"]) == []


def test_staff_cannot_complete_requisition_by_posting_every_role(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        for role in ("head", "admin", "manager"):
            post_action(client, login_as, setup["staff"], setup, role, **admin_approve_data(setup))

        requisition = setup["requisition"]
        requisition.reload()
        assert requisition.status == "pending"
        assert not requisition.approval_history
        assert models.RequisitionTimeline.objects(requisition=requisition).count() == 0
        assert models.Reservation.objects(requisition=requisition).count() == 0


def test_head_of_other_division_cannot_approve(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["other_head"], setup, "head")

        assert roles_in_history(setup["requisition"]) == []


def test_head_without_division_cannot_approve(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["no_division_head"], setup, "head")

        assert roles_in_history(setup["requisition"]) == []


def test_head_of_same_division_can_approve(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        response = post_action(client, login_as, setup["head"], setup, "head")

        assert response.status_code == 302
        assert roles_in_history(setup["requisition"]) == [("head", "approved")]
        assert setup["requisition"].status == "progress"


def test_admin_cannot_approve_before_head(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))

        assert roles_in_history(setup["requisition"]) == []
        assert models.Reservation.objects(requisition=setup["requisition"]).count() == 0


def test_head_cannot_approve_admin_step(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head")
        post_action(client, login_as, setup["head"], setup, "admin", **admin_approve_data(setup))

        assert roles_in_history(setup["requisition"]) == [("head", "approved")]


def test_manager_not_selected_cannot_approve(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head")
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))
        post_action(client, login_as, setup["other_manager"], setup, "manager")

        assert roles_in_history(setup["requisition"]) == [("head", "approved"), ("admin", "approved")]


def test_full_flow_by_rightful_approvers_completes(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head")
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))
        post_action(client, login_as, setup["manager"], setup, "manager")

        requisition = setup["requisition"]
        assert roles_in_history(requisition) == [
            ("head", "approved"),
            ("admin", "approved"),
            ("manager", "approved"),
        ]
        assert requisition.status == "complete"
        assert models.RequisitionTimeline.objects(requisition=requisition).count() == 1


def test_admin_approving_twice_reserves_once(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head")
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))

        setup["mas"].reload()
        assert models.Reservation.objects(requisition=setup["requisition"]).count() == 1
        assert setup["mas"].reservable_amount == Decimal("90000.00")
        assert roles_in_history(setup["requisition"]) == [("head", "approved"), ("admin", "approved")]


def test_admin_cannot_reserve_mas_of_other_organization(app, login_as, setup, create_org):
    with app.test_client() as client, app.app_context():
        other_org = create_org("Org B")
        foreign_mas = models.MAS(
            organization=other_org,
            year=2569,
            mas_code="MAS-B",
            description="งบ B",
            direction="-",
            amount=Decimal("50000.00"),
            remaining_amount=Decimal("50000.00"),
            reservable_amount=Decimal("50000.00"),
        )
        foreign_mas.save()

        post_action(client, login_as, setup["head"], setup, "head")
        post_action(
            client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup, mas=foreign_mas)
        )

        foreign_mas.reload()
        assert foreign_mas.reservable_amount == Decimal("50000.00")
        assert foreign_mas.editable is True
        assert models.Reservation.objects(mas=foreign_mas).count() == 0


def test_admin_cannot_select_manager_of_other_organization(
    app, login_as, setup, create_org, create_user, assign_user_to_org
):
    with app.test_client() as client, app.app_context():
        other_org = create_org("Org B")
        foreign_manager = create_user("ForeignManager", "Member")
        foreign_manager_role = assign_user_to_org(foreign_manager, other_org, roles=["manager"])

        post_action(client, login_as, setup["head"], setup, "head")
        data = admin_approve_data(setup)
        data["manager"] = str(foreign_manager_role.id)
        response = post_action(client, login_as, setup["admin"], setup, "admin", **data)

        assert response.status_code == 400
        assert roles_in_history(setup["requisition"]) == [("head", "approved")]
        assert models.Reservation.objects(requisition=setup["requisition"]).count() == 0


def test_no_action_after_rejection(app, login_as, setup):
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head", action="rejected")
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))

        requisition = setup["requisition"]
        assert roles_in_history(requisition) == [("head", "rejected")]
        assert requisition.status == "incomplete"


@pytest.mark.parametrize(
    "approver_role, action",
    [("foo", "approved"), ("head", "maybe"), ("", "")],
)
def test_invalid_role_or_action_is_rejected(app, login_as, setup, approver_role, action):
    with app.test_client() as client, app.app_context():
        login_as(client, setup["head"])
        response = client.post(
            f"/procurement/requisitions/{setup['requisition'].id}/action?organization_id={setup['org'].id}",
            data={"approver_role": approver_role, "action": action},
        )

        assert response.status_code == 400
        assert roles_in_history(setup["requisition"]) == []


def test_global_admin_can_act_for_every_step_in_order(app, login_as, setup, create_user, assign_user_to_org):
    with app.test_client() as client, app.app_context():
        system_admin = create_user("SystemAdmin", "Member", roles=["admin"])
        assign_user_to_org(system_admin, setup["org"], roles=["staff"])

        post_action(client, login_as, system_admin, setup, "manager")
        assert roles_in_history(setup["requisition"]) == []

        for role in ("head", "admin", "manager"):
            post_action(client, login_as, system_admin, setup, role, **admin_approve_data(setup))

        assert roles_in_history(setup["requisition"]) == [
            ("head", "approved"),
            ("admin", "approved"),
            ("manager", "approved"),
        ]
        assert setup["requisition"].status == "complete"


def test_concurrent_admin_approvals_reserve_once(app, login_as, setup, monkeypatch):
    """จำลองกดอนุมัติซ้ำพร้อมกัน: ทั้งสอง request ผ่านการตรวจก่อนที่อีกฝั่งจะบันทึก"""
    with app.test_client() as client, app.app_context():
        post_action(client, login_as, setup["head"], setup, "head")

        monkeypatch.setattr(models.Requisition, "get_approval_error", lambda self, role, user: None)
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))
        post_action(client, login_as, setup["admin"], setup, "admin", **admin_approve_data(setup))

        setup["mas"].reload()
        assert models.Reservation.objects(requisition=setup["requisition"]).count() == 1
        assert setup["mas"].reservable_amount == Decimal("90000.00")
        assert roles_in_history(setup["requisition"]) == [("head", "approved"), ("admin", "approved")]
