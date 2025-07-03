import datetime

from kampan.models.inventories import Inventory
from kampan.models.item_checkouts import CheckoutItem
from kampan.models.lost_break_items import LostBreakItem
from kampan.models.items import Item, ItemSnapshot


class DashboardRepository:
    @staticmethod
    def get_item_report(
        start_date: datetime,
        end_date: datetime,
        item_id: str,
        organization_id: str,
    ):
        reports = []
        inventories = Inventory.objects(
            item=item_id,
            status="active",
            organization=organization_id,
            created_date__gte=start_date,
            created_date__lte=end_date,
        ).order_by("-created_date")
        for inventory in inventories:
            data = {
                "type": "inventory",
                "created_date": inventory.created_date,
                "description": "เติมวัสดุ: "
                + str(inventory.registration.description)
                + "<br>"
                + "เลขกำกับใบเสร็จ "
                + str(inventory.registration.receipt_id),
                "warehouse": inventory.warehouse.name,
                "quantity": inventory.get_all_quantity(),
                "unit": (
                    inventory.item.piece_unit
                    if inventory.item.item_format == "one to many"
                    else inventory.item.set_unit
                ),
                "price": inventory.item.get_last_price_per_piece(),
                "total": inventory.get_all_price(),
                "remain": 0,
                "id": str(inventory.id),
            }
            reports.append(data)
        checkouts = CheckoutItem.objects(
            item=item_id,
            organization=organization_id,
            status="active",
            # created_date__gte=start_date,
            # created_date__lte=end_date,
        ).order_by("-created_date")
        for checkout in checkouts:
            try:
                if (
                    checkout.order.approved_date >= start_date
                    and checkout.order.approved_date <= end_date
                ):
                    data = {
                        "type": "checkout",
                        "created_date": checkout.order.approved_date,
                        "description": "เบิกวัสดุ: "
                        + str(checkout.order.description)
                        + "<br>"
                        + "เบิกโดย:"
                        + checkout.user.get_name(),
                        "warehouse": "",
                        "quantity": -checkout.quantity,
                        "unit": (
                            checkout.item.piece_unit
                            if checkout.item.item_format == "one to many"
                            else checkout.item.set_unit
                        ),
                        "price": checkout.item.get_last_price_per_piece(),
                        "total": checkout.get_all_price(),
                        "remain": 0,
                        "id": str(checkout.id),
                    }
                    reports.append(data)
            except:
                pass
        lost_breaks = LostBreakItem.objects(
            item=item_id,
            organization=organization_id,
            status="active",
            created_date__gte=start_date,
            created_date__lte=end_date,
        ).order_by("-created_date")
        for lost_break in lost_breaks:

            data = {
                "type": "lost_break",
                "created_date": lost_break.created_date,
                "description": "วัสดุชำรุด/สูญหาย/แก้ไข: " + str(lost_break.description),
                "warehouse": "",
                "quantity": lost_break.quantity,
                "unit": (
                    lost_break.item.piece_unit
                    if lost_break.item.item_format == "one to many"
                    else lost_break.item.set_unit
                ),
                "price": lost_break.item.get_last_price_per_piece(),
                "total": lost_break.get_all_price(),
                "remain": 0,
                "id": str(lost_break.id),
            }
            reports.append(data)
        snapshots = ItemSnapshot.objects(
            item=item_id,
            organization=organization_id,
            status="active",
            created_date__gte=start_date,
            created_date__lte=end_date,
        ).order_by("-created_date")
        for snapshot in snapshots:
            data = {
                "type": "snapshot",
                "created_date": snapshot.created_date,
                "description": "ยกยอด: "
                + str(snapshot.created_date.strftime("%Y-%m-%d")),
                "warehouse": "",
                "quantity": snapshot.amount,
                "unit": (
                    snapshot.item.piece_unit
                    if snapshot.item.item_format == "one to many"
                    else snapshot.item.set_unit
                ),
                "price": snapshot.last_price_per_piece,
                "total": snapshot.get_all_price(),
                "remain": 0,
                "id": str(snapshot.id),
            }
            reports.append(data)
        reports.sort(key=lambda x: x["created_date"])
        total = 0
        for i in range(len(reports)):
            if i == 0:
                total += reports[i]["quantity"]
            elif reports[i]["type"] != "snapshot":
                total += reports[i]["quantity"]
            reports[i]["remain"] = total
        return reports
