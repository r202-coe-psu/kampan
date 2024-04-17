# Inventories --> คลังสินค้า, สินค้าคงเหลือ

from email.policy import default
import mongoengine as me
import datetime


class RegistrationItem(me.Document):
    meta = {"collection": "registration_items"}

    bill = me.FileField(collection_name="bill_registration")
    status = me.StringField(default="active")
    receipt_id = me.StringField(required=True, max_length=255)
    description = me.StringField()

    supplier = me.ReferenceField("Supplier", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    def get_item_in_bill(self):
        inventories = Inventory.objects(registration=self, status__ne="disactive")
        if inventories:
            return [inventory.item.id for inventory in inventories]

    def get_quantity_of_item(self):
        quantiy_item = Inventory.objects(
            registration=self, status__ne="disactive"
        ).count()
        return quantiy_item


class Inventory(me.Document):
    # อุปกรณ์
    meta = {"collection": "inventories"}
    status = me.StringField(default="active", required=True)

    registration = me.ReferenceField("RegistrationItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)

    item = me.ReferenceField("Item", dbref=True)
    # bill = me.FileField()

    set_ = me.IntField(required=True, min_value=1, default=1)
    quantity = me.IntField(required=True, min_value=1, default=1)
    remain = me.IntField(required=True, default=0)
    price = me.DecimalField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField()
    position = me.ReferenceField("ItemPosition", dbref=True)

    # notification_status = me.BooleanField(default=True)
    created_by = me.ReferenceField("User", dbref=True)

    def get_checkout_items(self):
        return CheckoutItem.objects(checkout_from=self, status="active")

    def get_bill_file_name(self):
        if self.registration.bill:
            return self.registration.bill.filename
        else:
            return "ไม่พบบิล"


class InventoryEngagementFile(me.Document):
    meta = {"collection": "inventory_engagement_file"}

    file = me.FileField()
    status = "waiting"
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)
    registration = me.ReferenceField("RegistrationItem", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )


class OrderEmail(me.EmbeddedDocument):
    receiver_email = me.StringField(required=True)
    status = me.StringField(required=True, default="not_sent")
    sent_date = me.DateTimeField()
    updateded_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    sent_by = me.ReferenceField("User", dbref=True)
    remark = me.StringField(default="")


class OrderItem(me.Document):
    # เบิกอุปกรณ์
    meta = {"collection": "order_items"}
    status = me.StringField(default="active")

    approval_status = me.StringField(default="pending")
    description = me.StringField()
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)
    division = me.ReferenceField("Division", dbref=True)

    emails = me.EmbeddedDocumentListField(OrderEmail)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    approved_date = me.DateTimeField()

    def get_all_price(self):
        return sum(
            [
                approved_item.price * approved_item.aprroved_amount
                for approved_item in ApprovedCheckoutItem.objects(
                    status="active",
                    order=self,
                )
            ]
        )

    def get_item_in_bill(self):
        checkout_items = CheckoutItem.objects(order=self, status="active")
        if checkout_items:
            return [checkout_item.item.id for checkout_item in checkout_items]

    def get_item_detail(self):
        checkout_items = CheckoutItem.objects(order=self, status="active")
        if checkout_items:
            return [
                (
                    checkout_item.item.id,
                    checkout_item.item.name,
                    checkout_item.quantity,
                    checkout_item.item.get_items_quantity(),
                )
                for checkout_item in checkout_items
            ]


class BaseCheckoutItem:
    status = me.StringField(default="active")

    order = me.ReferenceField("OrderItem", dbref=True)

    message = me.StringField()
    item = me.ReferenceField("Item", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    set_ = me.IntField(required=True, min_value=1, default=1)
    quantity = me.IntField(required=True, min_value=1, default=1)
    checkout_date = me.DateTimeField(required=True, default=datetime.datetime.now())


class CheckoutItem(me.Document, BaseCheckoutItem):
    # รายการนำเข้าอุปกรณ์ออก
    meta = {"collection": "checkout_items"}
    approval_status = me.StringField(default="pending")

    def get_amount_items(self):
        sumary = (self.set_ * self.item.piece_per_set) + self.quantity
        return sumary


class ApprovedCheckoutItem(me.Document, BaseCheckoutItem):
    meta = {"collection": "approved_checkout_items"}

    warehouse = me.ReferenceField("Warehouse", dbref=True)
    # checkout_from = me.ReferenceField("Inventory", dbref=True)
    approved_date = me.DateTimeField()
    price = me.DecimalField(default=0.0)
    aprroved_amount = me.IntField(default=0)


class LostBreakItem(me.Document):
    # ไอเทมที่ชำรุด หรือ เสียหาย
    mete = {"collection": "lost_break_items"}
    status = me.StringField(default="active")

    user = me.ReferenceField("User", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    lost_from = me.ReferenceField("Inventory", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    description = me.StringField(max_length=255)
    quantity = me.IntField(required=True, min_value=1, default=1)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
