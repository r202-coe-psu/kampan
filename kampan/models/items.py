from flask import url_for
from email.policy import default
import mongoengine as me
from mongoengine import Q
import datetime, calendar
from kampan import models


from kampan.models.inventories import Inventory
from kampan.models.item_checkouts import CheckoutItem
from kampan.models.lost_break_items import LostBreakItem

ITEM_FORMAT = [
    ("one to many", "หนึ่งต่อหลายๆ"),
    ("one to one", "หนึ่งต่อหนึ่ง"),
]

ITEM_SNAPSHOT = [
    ("carry", "ยกยอด"),
    ("check", "เช็คสต๊อก"),
]


class ItemSize(me.EmbeddedDocument):
    width = me.FloatField()
    height = me.FloatField()
    deep = me.FloatField()


class Item(me.Document):
    meta = {
        "collection": "items",
        "indexes": ["name", "created_date"],
    }

    status = me.StringField(default="pending")

    name = me.StringField(required=True, max_length=255)
    description = me.StringField()
    remark = me.StringField()
    organization = me.ReferenceField("Organization", dbref=True)

    item_format = me.StringField(
        required=True, choices=ITEM_FORMAT, default=ITEM_FORMAT[0][0]
    )
    set_ = me.IntField(required=True, min_value=1, default=1)
    set_unit = me.StringField(required=True, default="ชุด", max_length=50)
    piece_per_set = me.IntField(min_value=1, default=1, required=True)
    piece_unit = me.StringField(default="ชิ้น", max_length=50, required=True)

    categories = me.ReferenceField("Category", dbref=True)
    image = me.ImageField()
    minimum = me.IntField(required=True, min_value=0, default=0)
    barcode_id = me.StringField(max_length=255)
    notification_status = me.BooleanField(default=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_items_quantity(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])

            if self.item_format == "one to many":
                return f"{sumary // self.piece_per_set} {self.set_unit} " + (
                    (str(sumary % self.piece_per_set) + " " + str(self.piece_unit))
                    if (sumary % self.piece_per_set) != 0
                    else ""
                )
            else:
                return f"{sumary // self.piece_per_set} {self.set_unit}"
        return f"0 {self.set_unit}"

    def get_amount_items(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])
            return sumary // self.piece_per_set
        return 0

    def get_amount_pieces(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            sumary = sum([inventory.remain for inventory in inventories])
            return sumary
        return 0

    def get_last_price(self):
        inventories = models.Inventory.objects(item=self, status="active")
        if inventories:
            return inventories.order_by("-created_date").first().price
        return 0

    def get_last_price_per_piece(self):
        value = self.get_last_price()
        if value != None:

            return round(value / self.piece_per_set, 2)

        return 0

    def get_remaining_balance(self):
        value = self.get_last_price()
        amount_item = self.get_amount_items()
        amount_piece = self.get_amount_pieces()
        if value:
            set_remaining = (value * amount_item) + (
                (amount_piece % self.piece_per_set)
                * round(value / self.piece_per_set, 2)
            )
            return set_remaining
        return ""

    def get_booking_item(self):
        checkout_items = models.CheckoutItem.objects(
            item=self, status="active", approval_status="pending"
        )
        if checkout_items:
            return sum([checkout_item.quantity for checkout_item in checkout_items])
        return 0


class ItemPosition(me.Document):
    meta = {"collection": "item_positions"}
    status = me.StringField(default="active")

    description = me.StringField(required=True, max_length=255)
    rack = me.StringField(required=True, max_length=255)
    row = me.StringField(max_length=255)
    locker = me.StringField(max_length=255)
    organization = me.ReferenceField("Organization", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)

    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class ItemSnapshot(me.Document):
    meta = {"collection": "item_snapshots"}
    type_ = me.StringField(default="carry", choices=ITEM_SNAPSHOT, required=True)

    item = me.ReferenceField("Item", dbref=True)
    amount = me.IntField()
    last_price = me.DecimalField()
    last_price_per_piece = me.DecimalField()

    remaining_balance = me.DecimalField()
    status = me.StringField(default="active")

    organization = me.ReferenceField("Organization", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_amount_pieces(self):
        return self.amount

    def get_amount(self):
        if self.item.item_format == "one to many":
            return self.amount // self.item.piece_per_set
        return self.amount

    def get_pieces(self):
        if self.item.item_format == "one to many":
            return self.amount % self.item.piece_per_set
        return 0

    def get_all_price(self):
        if self.item.item_format == "one to one":
            return self.last_price_per_piece * self.amount
        return self.last_price_per_piece * self.amount

    def update_data(self):
        date = self.created_date

        item_id = self.item.id
        organization_id = self.organization.id

        start_date = datetime.datetime(2024, 1, 1, 0, 0, 0)
        end_date = date
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
                "description": "วัสดุชำรุด/สูญหาย: " + str(lost_break.description),
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

        reports.sort(key=lambda x: x["created_date"])
        total = 0

        for i in range(len(reports)):
            if i == 0:
                total += reports[i]["quantity"]
            elif reports[i]["type"] != "snapshot":
                total += reports[i]["quantity"]
            reports[i]["remain"] = total

        if not reports:
            last_snap = ItemSnapshot.objects(
                item=self, status="active", created_date__lte=end_date
            ).order_by("-created_date")
            if last_snap:
                self.amount = last_snap.amount
                self.last_price_per_piece = last_snap.last_price_per_piece
                self.last_price = last_snap.last_price
                self.remaining_balance = last_snap.remaining_balance
        else:
            self.amount = total
            self.last_price_per_piece = reports[-1]["price"]
            self.last_price = self.item.get_last_price()
            self.remaining_balance = int(str(total * int(reports[-1]["price"])))
        self.save()
