"""#23 เงินทุกจุดเก็บและคำนวณเป็น Decimal ปัดแบบ ROUND_HALF_EVEN และไม่รับ input ทศนิยมเกิน 2 ตำแหน่ง"""

import datetime
import decimal
import re
from decimal import Decimal
from unittest.mock import MagicMock, patch

import mongoengine as me
import pytest
from flask import g, request
from flask_wtf import FlaskForm
from mongoengine.base import _document_registry
from openpyxl import Workbook
from wtforms import DecimalField

from kampan import models
from kampan.utils import export_file
from kampan.utils.money import (
    MONEY_PLACES_ERROR,
    has_money_places,
    money_sum,
    to_money,
)
from kampan.web import forms, redis_rq
from kampan.web.forms.money_validators import MoneyPlaces

# ---------------------------------------------------------------------------
# helper กลาง
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        (Decimal("0.125"), Decimal("0.12")),
        (Decimal("0.135"), Decimal("0.14")),
        ("2.675", Decimal("2.68")),
        ("2.665", Decimal("2.66")),
        (None, Decimal("0")),
        ("", Decimal("0")),
        (0, Decimal("0")),
        (0.1 + 0.2, Decimal("0.30")),
        (1234.5, Decimal("1234.50")),
    ],
)
def test_to_money_rounds_half_even(value, expected):
    result = to_money(value)

    assert isinstance(result, Decimal)
    assert result == expected
    assert result.as_tuple().exponent == -2


def test_money_sum_returns_exact_decimal():
    assert money_sum([Decimal("0.10"), Decimal("0.20")]) == Decimal("0.30")
    assert money_sum([0.1, 0.2]) == Decimal("0.30")
    assert money_sum([Decimal("1.00"), None]) == Decimal("1.00")


def test_money_sum_of_empty_is_decimal_zero():
    result = money_sum([])

    assert isinstance(result, Decimal)
    assert result == Decimal("0")


@pytest.mark.parametrize("value", [None, "1", "1.2", "1.23", "1.230", Decimal("100000.00"), 5])
def test_has_money_places_accepts_up_to_two_places(value):
    assert has_money_places(value)


@pytest.mark.parametrize("value", ["1.234", "0.001", Decimal("33333.333"), "NaN", "Infinity", "abc"])
def test_has_money_places_rejects_more_than_two_places(value):
    assert not has_money_places(value)


class _AmountForm(FlaskForm):
    amount = DecimalField(validators=[MoneyPlaces()])


@pytest.mark.parametrize(
    "raw, valid",
    [("1.234", False), ("1.23", True), ("1", True), ("1000000.50", True), ("0.005", False)],
)
def test_money_places_validator(app, raw, valid):
    with app.test_request_context(method="POST", data={"amount": raw}):
        form = _AmountForm()

        assert form.validate() is valid
        if not valid:
            assert form.amount.errors == [MONEY_PLACES_ERROR]
        # ไม่ปัด input ของผู้ใช้เงียบ ๆ: ค่าที่ได้คือค่าที่กรอกตรง ๆ
        assert form.amount.data == Decimal(raw)


@pytest.mark.parametrize(
    "form_factory, field_name",
    [
        (lambda: forms.procurement.ProcurementHeaderForm(), "total_amount"),
        (lambda: forms.procurement.ProcurementItemForm(request.form), "amount"),
        (lambda: forms.procurement.ProcurementItemForm(request.form), "unit_price"),
        (lambda: forms.procurement.InstallmentPaymentForm(), "paid_amount"),
        (lambda: forms.inventories.InventoryForm(), "price"),
        (lambda: forms.mas.MASForm(), "amount"),
        (lambda: forms.requisitions.RequisitionItemForm(request.form), "amount"),
        (lambda: forms.requisition_timeline.DetailsSpecifiedItemForm(), "amount"),
    ],
)
def test_money_forms_reject_more_than_two_places(app, form_factory, field_name):
    with app.test_request_context(method="POST", data={field_name: "1.234"}):
        form = form_factory()
        field = getattr(form, field_name)
        # ตรวจเฉพาะ field เงิน (ฟอร์มบางตัวมี SelectField ที่ต้องเติม choices ตอนใช้งานจริง)
        field.validate(form)

        assert MONEY_PLACES_ERROR in field.errors


# ---------------------------------------------------------------------------
# registry: field เงินใหม่ต้องเป็น DecimalField(precision=2, ROUND_HALF_EVEN)
# ---------------------------------------------------------------------------

MONEY_NAME = re.compile(r"(^|_)(amounts?|prices?|balance|total|cost|budget)(_|$)")

# IntField ที่ชื่อคล้ายเงินแต่เป็นจำนวนชิ้น
QUANTITY_FIELDS = {
    ("ApprovedCheckoutItem", "aprroved_amount"),
    ("FundAllocationSource", "item_amount"),
    ("ItemSnapshot", "amount"),
}


def _leaf_field(field):
    while isinstance(field, (me.ListField, me.MapField)) and field.field is not None:
        field = field.field
    return field


def find_bad_money_fields(registry):
    bad = []
    for class_name, document in sorted(registry.items()):
        for name, field in document._fields.items():
            if not MONEY_NAME.search(name) or (class_name, name) in QUANTITY_FIELDS:
                continue
            leaf = _leaf_field(field)
            if isinstance(leaf, (me.EmbeddedDocumentField, me.ReferenceField)):
                continue
            if not (
                isinstance(leaf, me.DecimalField)
                and leaf.precision == 2
                and leaf.rounding == decimal.ROUND_HALF_EVEN
            ):
                bad.append(f"{class_name}.{name} ({type(leaf).__name__})")
    return bad


def test_every_money_field_is_decimal_two_places_half_even():
    assert find_bad_money_fields(_document_registry) == []


def test_registry_check_catches_float_money_field():
    class _BadMoneyDoc(me.Document):
        meta = {"collection": "_bad_money_docs"}
        price = me.FloatField()

    try:
        assert find_bad_money_fields(_document_registry) == ["_BadMoneyDoc.price (FloatField)"]
    finally:
        _document_registry.pop("_BadMoneyDoc", None)


def test_quantity_allow_list_is_still_accurate():
    # ถ้า field ใน allow-list ถูกลบหรือเปลี่ยนชื่อ ให้ลบออกจาก allow-list ด้วย
    for class_name, name in QUANTITY_FIELDS:
        assert isinstance(_document_registry[class_name]._fields[name], me.IntField)


def _requisition(org, user, purchaser, code="0001/2569", amounts=("0.30",)):
    return models.Requisition(
        requisition_code=code,
        organization=org,
        purchaser=purchaser,
        start_date=datetime.datetime(2026, 11, 1),
        items=[
            models.RequisitionItem(
                product_name=f"รายการ {i}", quantity=1, category="material", amount=Decimal(amount)
            )
            for i, amount in enumerate(amounts)
        ],
        created_by=user,
    ).save()


def test_fund_usage_amounts_reads_legacy_double_as_decimal(
    app, create_org, create_user, assign_user_to_org
):
    with app.app_context():
        org = create_org()
        user = create_user()
        requisition = _requisition(org, user, assign_user_to_org(user, org))
        timeline = models.RequisitionTimeline(organization=org, requisition=requisition).save()
        # ข้อมูลเดิมเขียนเป็น double ผ่าน DictField
        models.RequisitionTimeline._get_collection().update_one(
            {"_id": timeline.id}, {"$set": {"fund_usage_amounts": {"abc": 33333.33}}}
        )

        timeline.reload()

        assert timeline.fund_usage_amounts == {"abc": Decimal("33333.33")}
        assert isinstance(timeline.fund_usage_amounts["abc"], Decimal)


# ---------------------------------------------------------------------------
# model helpers
# ---------------------------------------------------------------------------


def _procurement_items(org, amounts):
    now = datetime.datetime(2026, 1, 1)
    return [
        models.ProcurementItem(
            name=f"รายการ {i}",
            category="service",
            amount=Decimal(amount),
            start_date=now,
            end_date=now + datetime.timedelta(days=60),
            installments=[models.Installment(due_date=now)],
        )
        for i, amount in enumerate(amounts)
    ]


def test_ma_item_sum_is_exact_decimal(app, create_org):
    """0.10 + 0.20 ต้องเท่ายอด MA 0.30 พอดี (float จะได้ 0.30000000000000004)"""
    with app.app_context():
        org = create_org()
        procurement = models.Procurement(name="สัญญา", company="บริษัท", total_amount=Decimal("0.30"), organization=org)

        procurement.save_with_items(_procurement_items(org, ["0.10", "0.20"]))

        procurement.reload()
        assert procurement.total_amount == Decimal("0.30")
        assert models.ProcurementItem.objects(procurement=procurement).count() == 2


def test_ma_item_sum_check_message_shows_difference_in_baht():
    message = models.procurement.check_item_sum(Decimal("100000.00"), [Decimal("95000.00")])

    assert message == "ผลรวมรายการย่อย 95,000.00 บาท ไม่ตรงกับยอด MA 100,000.00 บาท (ขาด 5,000.00 บาท)"
    assert "เกิน 0.01 บาท" in models.procurement.check_item_sum(Decimal("1.00"), [Decimal("0.50"), Decimal("0.51")])
    assert models.procurement.check_item_sum(Decimal("0"), []) is None


def _item(org, piece_per_set=2):
    return models.Item(
        name="[TEST] ปากกา",
        organization=org,
        item_format="one to many",
        piece_per_set=piece_per_set,
    ).save()


def test_inventory_price_per_piece_rounds_half_even(app, create_org):
    with app.app_context():
        org = create_org()
        item = _item(org)
        inventory = models.Inventory(item=item, organization=org, price=Decimal("0.25"))

        # 0.25 / 2 = 0.125 → banker's rounding ได้ 0.12
        assert inventory.get_price_per_piece() == Decimal("0.12")
        inventory.price = Decimal("0.27")
        assert inventory.get_price_per_piece() == Decimal("0.14")


def test_item_last_price_per_piece_without_inventory_is_decimal(app, create_org):
    with app.app_context():
        price = _item(create_org()).get_last_price_per_piece()

        assert isinstance(price, Decimal)
        assert price == Decimal("0")


def test_decimal_field_stores_system_value_with_half_even(app, create_org):
    with app.app_context():
        org = create_org()
        inventory = models.Inventory(item=_item(org), organization=org, price=Decimal("0.125"))
        inventory.save()
        inventory.reload()

        assert inventory.price == Decimal("0.12")


def test_approved_checkout_item_default_price_is_decimal():
    assert models.ApprovedCheckoutItem().price == Decimal("0")
    assert isinstance(models.ApprovedCheckoutItem().price, Decimal)
    assert isinstance(models.FundAllocation().item_total, Decimal)


# ---------------------------------------------------------------------------
# export / dashboard
# ---------------------------------------------------------------------------


def test_mas_export_accumulates_actual_amount_as_decimal(
    app, create_org, create_user, assign_user_to_org
):
    with app.app_context():
        org = create_org()
        user = create_user()
        mas = models.MAS(
            organization=org,
            year=2569,
            mas_code="MAS-X",
            description="งบ",
            direction="-",
            amount=Decimal("100.00"),
            remaining_amount=Decimal("99.70"),
            reservable_amount=Decimal("99.70"),
        ).save()
        requisition = _requisition(org, user, assign_user_to_org(user, org))
        models.RequisitionTimeline(
            organization=org,
            requisition=requisition,
            progress=[
                models.Progress(progress_status="order_confirmed", timestamp=datetime.datetime(2026, 11, 2))
            ],
        ).save()
        for actual in ("0.10", "0.20"):
            models.Reservation(
                organization=org,
                requisition=requisition,
                mas=mas,
                amount=Decimal(actual),
                actual_amount=Decimal(actual),
                reservation_status="finished",
            ).save()

        ws = Workbook().active
        export_file.get_purchased_items_in_mas(
            ws, mas.id, 1, datetime.date(2026, 11, 1), datetime.date(2026, 11, 30)
        )

        # 0.1 + 0.2 แบบ float ได้ 0.30000000000000004
        assert ws.cell(row=2, column=4).value == 0.3


def test_admin_daily_dashboard_total_is_decimal(app, create_user, login_as):
    with app.app_context():
        admin = create_user("SysAdmin", "Root", roles=["admin"])
        captured = {}

        def fake_render(template, **context):
            captured.update(context)
            return "ok"

        with app.test_client() as client, patch(
            "kampan.web.views.admin.dashboard.render_template", fake_render
        ):
            login_as(client, admin)
            response = client.get("/admin/dashboard/daily")

        assert response.status_code == 200
        # ไม่มีรายการอนุมัติ ยอดรวมต้องเป็น Decimal("0") ไม่ใช่ int 0
        assert isinstance(captured["total_values"], Decimal)
        assert captured["total_values"] == Decimal("0")


def test_order_item_total_price_is_exact_decimal(app, create_org):
    with app.app_context():
        org = create_org()
        order = models.OrderItem(organization=org, status="active").save()
        for price in ("0.10", "0.20"):
            models.ApprovedCheckoutItem(
                organization=org, order=order, price=Decimal(price), aprroved_amount=1
            ).save()
        empty_order = models.OrderItem(organization=org, status="active").save()

        assert order.get_all_price() == Decimal("0.30")
        assert isinstance(empty_order.get_all_price(), Decimal)


# ---------------------------------------------------------------------------
# ขอซื้อขอจ้าง (ปิดอยู่ด้วย flag แต่โค้ดต้องใช้ได้เมื่อเปิด)
# ---------------------------------------------------------------------------


@pytest.fixture
def requisition_enabled(app, monkeypatch):
    monkeypatch.setitem(app.config, "PROCUREMENT_REQUISITION_ENABLED", True)


@pytest.fixture
def billing_world(app, requisition_enabled, create_org, create_user, assign_user_to_org):
    """คำขอ 3 รายการ ใช้ reservation เดียวยอดจอง 100,000.00 จาก MAS ที่ remaining 100,000.00"""
    with app.app_context():
        org = create_org()
        admin = create_user("Admin", "Money")
        admin_role = assign_user_to_org(admin, org, roles=["admin"])
        mas = models.MAS(
            organization=org,
            year=2569,
            mas_code="MAS-B",
            description="งบ",
            direction="-",
            amount=Decimal("100000.00"),
            remaining_amount=Decimal("100000.00"),
            reservable_amount=Decimal("0.00"),
        ).save()
        requisition = models.Requisition(
            requisition_code="0002/2569",
            organization=org,
            purchaser=admin_role,
            start_date=datetime.datetime(2026, 11, 1),
            items=[
                models.RequisitionItem(
                    product_name=f"รายการ {i}", quantity=1, category="material", amount=Decimal("33333.33")
                )
                for i in range(3)
            ],
            created_by=admin,
        ).save()
        reservation = models.Reservation(
            organization=org, requisition=requisition, mas=mas, amount=Decimal("100000.00")
        ).save()
        requisition.fund = [models.requisitions.Funds(mas=mas, reservation=reservation, amount=Decimal("100000.00"))]
        requisition.save()
        timeline = models.RequisitionTimeline(
            organization=org,
            requisition=requisition,
            progress=[models.Progress(progress_status="order_confirmed")],
        ).save()
        return {
            "org": org,
            "admin": admin,
            "mas": mas,
            "requisition": requisition,
            "reservation": reservation,
            "timeline": timeline,
        }


def _billing_data(world, amounts):
    data = {"purchase_method": "specific"}
    for idx, (item, amount) in enumerate(zip(world["requisition"].items, amounts)):
        data[f"items-{idx}-item_id"] = str(item._id)
        data[f"items-{idx}-source_id"] = str(world["reservation"].id)
        data[f"items-{idx}-single_amount"] = amount
        data[f"items-{idx}-single_qty"] = "1"
    return data


def _post_billing(app, login_as, world, amounts):
    with app.test_client() as client:
        login_as(client, world["admin"])
        return client.post(
            f"/procurement/requisition_timeline/{world['timeline'].id}/billing_modal"
            f"?organization_id={world['org'].id}",
            data=_billing_data(world, amounts),
        )


def test_billing_settles_reservation_with_exact_decimals(app, login_as, billing_world):
    world = billing_world
    with app.app_context():
        response = _post_billing(app, login_as, world, ["33333.33"] * 3)

        assert response.status_code == 302
        mas = models.MAS.objects.get(id=world["mas"].id)
        assert mas.remaining_amount == Decimal("0.01")
        assert mas.reservable_amount == Decimal("0.01")

        timeline = models.RequisitionTimeline.objects.get(id=world["timeline"].id)
        assert timeline.payment_amount == Decimal("99999.99")
        usage = timeline.fund_usage_amounts[str(world["reservation"].id)]
        assert isinstance(usage, Decimal)
        assert usage == Decimal("99999.99")
        sources = [s for alloc in timeline.fund_allocations for s in alloc.allocations]
        assert [s.amount for s in sources] == [Decimal("33333.33")] * 3
        assert all(isinstance(alloc.item_total, Decimal) for alloc in timeline.fund_allocations)

        reservation = models.Reservation.objects.get(id=world["reservation"].id)
        assert reservation.actual_amount == Decimal("99999.99")
        requisition = models.Requisition.objects.get(id=world["requisition"].id)
        assert requisition.fund[0].amount == Decimal("99999.99")

        # ค่าใน DB ยังเป็น double เหมือนเดิม (ไม่เปลี่ยน storage)
        raw = models.RequisitionTimeline._get_collection().find_one({"_id": world["timeline"].id})
        assert raw["fund_usage_amounts"][str(world["reservation"].id)] == 99999.99


def test_billing_rejects_amount_with_more_than_two_places(app, login_as, billing_world):
    world = billing_world
    with app.app_context():
        response = _post_billing(app, login_as, world, ["33333.333", "33333.33", "33333.33"])

        assert response.status_code == 200
        assert MONEY_PLACES_ERROR in response.get_data(as_text=True)
        mas = models.MAS.objects.get(id=world["mas"].id)
        assert mas.remaining_amount == Decimal("100000.00")
        timeline = models.RequisitionTimeline.objects.get(id=world["timeline"].id)
        assert timeline.payment_amount is None
        assert timeline.progress[-1].progress_status == "order_confirmed"


def test_details_specified_rejects_amount_with_more_than_two_places(app, login_as, billing_world):
    world = billing_world
    timeline = world["timeline"]
    with app.app_context():
        timeline.progress = [models.Progress(progress_status="vendor_contacted")]
        timeline.save()
        item = world["requisition"].items[0]
        data = {
            "project_name": "[TEST]",
            "items-0-item_id": str(item._id),
            "items-0-product_name": item.product_name,
            "items-0-quantity": "1",
            "items-0-amount": "100.005",
        }
        with app.test_client() as client:
            login_as(client, world["admin"])
            response = client.post(
                f"/procurement/requisition_timeline/{timeline.id}/details_specified"
                f"?organization_id={world['org'].id}",
                data=data,
            )

        assert response.status_code == 200
        assert MONEY_PLACES_ERROR in response.get_data(as_text=True)
        requisition = models.Requisition.objects.get(id=world["requisition"].id)
        assert requisition.items[0].amount == Decimal("33333.33")


@pytest.fixture
def mock_queue():
    queue = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", queue, create=True):
        yield queue


def test_admin_approval_rejects_fund_amount_with_more_than_two_places(
    app, requisition_enabled, mock_queue, create_org, create_user, assign_user_to_org, login_as
):
    with app.app_context():
        org = create_org()
        division = models.Division(name="ฝ่าย", organization=org).save()
        staff = create_user("Staff", "Money")
        staff_role = assign_user_to_org(staff, org, roles=["staff"])
        staff_role.division = division
        staff_role.save()
        head = create_user("Head", "Money")
        head_role = assign_user_to_org(head, org, roles=["head"])
        head_role.division = division
        head_role.save()
        admin = create_user("Admin", "Money")
        assign_user_to_org(admin, org, roles=["admin"])
        manager = create_user("Manager", "Money")
        manager_role = assign_user_to_org(manager, org, roles=["manager"])
        mas = models.MAS(
            organization=org,
            year=2569,
            mas_code="MAS-C",
            description="งบ",
            direction="-",
            amount=Decimal("100000.00"),
            remaining_amount=Decimal("100000.00"),
            reservable_amount=Decimal("100000.00"),
        ).save()
        requisition = models.Requisition(
            requisition_code="0003/2569",
            organization=org,
            purchaser=staff_role,
            start_date=datetime.datetime(2026, 11, 1),
            items=[
                models.RequisitionItem(
                    product_name="เครื่องพิมพ์", quantity=1, category="product", amount=Decimal("10000.00")
                )
            ],
            created_by=staff,
        ).save()
        url = f"/procurement/requisitions/{requisition.id}/action?organization_id={org.id}"

        with app.test_client() as client:
            login_as(client, head)
            client.post(url, data={"approver_role": "head", "action": "approved"})
            g.pop("_login_user", None)
            login_as(client, admin)
            client.post(
                url,
                data={
                    "approver_role": "admin",
                    "action": "approved",
                    "fund_ids": str(mas.id),
                    f"fund_amounts[{mas.id}]": "10000.005",
                    "manager": str(manager_role.id),
                },
            )

        requisition.reload()
        assert [(h.approver_role, h.action) for h in requisition.approval_history] == [("head", "approved")]
        assert models.Reservation.objects(requisition=requisition).count() == 0
        mas.reload()
        assert mas.reservable_amount == Decimal("100000.00")
