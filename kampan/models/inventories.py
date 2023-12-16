# Inventories --> คลังสินค้า, สินค้าคงเหลือ

from email.policy import default
import mongoengine as me
import datetime


class RegistrationItem(me.Document):
    # อุปกรณ์ที่ลงทะเบียน
    meta = {"collection": "registration_items"}
    receipt_id = me.StringField(required=True, max_length=255)
    description = me.StringField()
    supplier = me.ReferenceField("Supplier", dbref=True)
    bill = me.FileField()
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class Inventory(me.Document):
    # คลังอุปกรณ์
    meta = {"collection": "inventories"}

    registration = me.ReferenceField("RegistrationItem", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)
    # bill = me.FileField()

    quantity = me.IntField(required=True, min_value=1, default=1)
    remain = me.IntField(required=True, default=0)
    price = me.FloatField(required=True, default=0)

    registeration_date = me.DateTimeField(
        required=True, default=datetime.datetime.now()
    )
    expiration_date = me.DateTimeField()
    position = me.ReferenceField("ItemPosition", dbref=True)

    notification_status = me.BooleanField(default=True)
    user = me.ReferenceField("User", dbref=True)

    def get_checkout_items(self):
        return CheckoutItem.objects(checkout_from=self)


class OrderItem(me.Document):
    # เบิกอุปกรณ์
    meta = {"collection": "order_items"}

    status = me.StringField(default="pending")
    description = me.StringField()
    user = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class CheckoutItem(me.Document):
    # รายการนำเข้าอุปกรณ์ออก
    meta = {"collection": "checkout_items"}

    user = me.ReferenceField("User", dbref=True)

    order = me.ReferenceField("OrderItem", dbref=True)
    checkout_from = me.ReferenceField("Inventory", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    item = me.ReferenceField("Item", dbref=True)
    status = me.StringField(default="pending")

    quantity = me.IntField(required=True, min_value=1, default=1)
    price = me.FloatField()
    message = me.StringField()

    checkout_date = me.DateTimeField(required=True, default=datetime.datetime.now())


class LostBreakItem(me.Document):
    # ไอเทมที่ชำรุด หรือ เสียหาย
    mete = {"collection": "lost_break_items"}

    user = me.ReferenceField("User", dbref=True)
    item = me.ReferenceField("Item", dbref=True)

    lost_from = me.ReferenceField("Inventory", dbref=True)
    warehouse = me.ReferenceField("Warehouse", dbref=True)
    description = me.StringField(max_length=255)
    quantity = me.IntField(required=True, min_value=1, default=1)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)


class Approve_orders(me.Document):
    # อนุมัติเบิก
    meta = {"collection": "approve_orders"}
    reated_date = me.DateTimeField(required=True, default=datetime.datetime.now)
