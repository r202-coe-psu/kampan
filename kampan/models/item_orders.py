from email.policy import default
import mongoengine as me
import datetime
from kampan import models

ORDER_ITEM_STATUS = [
    ("admin denied", "ปฎิเสธ"),
    ("denied", "ปฎิเสธ"),
    ("approved", "อนุมัติรอรับวัสดุ"),
    ("pending on admin", "รอการจัดการจากเจ้าหน้าที่พัสดุ"),
    ("pending on supervisor supplier", "รอการอนุมัติจากหัวหน้าเจ้าหน้าที่พัสดุ"),
    ("pending", "รอการยืนยันการเบิก"),
    ("confirmed", "รอการอนุมัติจากหัวหน้าฝ่าย"),
    ("disactive", "ยกเลิก"),
    ("active", "ดำเนินการ"),
]


class OrderEmail(me.EmbeddedDocument):
    name = me.StringField()
    receiver_email = me.StringField(required=True)
    status = me.StringField(required=True, default="not_sent")
    sent_date = me.DateTimeField(default=datetime.datetime.now, required=True)
    updateded_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    sent_by = me.ReferenceField("User", dbref=True)
    remark = me.StringField(default="")


class OrderItem(me.Document):
    # เบิกวัสดุ
    meta = {"collection": "order_items"}
    ordinal_number = me.StringField(default="")

    status = me.StringField(required=True, default="pending", choices=ORDER_ITEM_STATUS)

    approval_status = me.StringField(default="pending")
    remark = me.StringField(default="")

    head_endorser = me.ReferenceField("User", dbref=True)
    # admin_approver = me.ReferenceField("User", dbref=True)

    description = me.StringField()
    created_by = me.ReferenceField("User", dbref=True)
    organization = me.ReferenceField("Organization", dbref=True)
    division = me.ReferenceField("Division", dbref=True)

    emails = me.EmbeddedDocumentListField(OrderEmail)
    sent_item_date = me.DateTimeField()
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    approved_date = me.DateTimeField()

    def get_all_price(self):
        return sum(
            [
                approved_item.price * approved_item.aprroved_amount
                for approved_item in models.ApprovedCheckoutItem.objects(
                    status="active",
                    order=self,
                )
            ]
        )

    def get_checkout_all_price(self):
        checkouts = models.CheckoutItem.objects(order=self, status__ne="disactive")
        if checkouts:
            summation = 0
            for check_out in checkouts:
                if check_out.get_all_price():
                    summation += check_out.get_all_price()

            return summation
        return ""

    def get_item_in_bill(self):
        checkout_items = models.CheckoutItem.objects(order=self, status="active")
        if checkout_items:
            return [checkout_item.item.id for checkout_item in checkout_items]

    def get_item_detail(self):
        checkout_items = models.CheckoutItem.objects(order=self, status="active")
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

    def get_status(self):
        key_color = {
            "denied": "text-error",
            "admin denied": "text-error",
            "approved": "text-green-500",
            "pending on admin": "text-primary",
            "pending on supervisor supplier": "text-orange-500",
            "pending": "text-pink-500",
            "confirmed": "text-yellow-500",
            "disactive": "text-error",
            "active": "text-primary",
        }
        return f'<td class="table-style" data-label="Status"><span class="{key_color[self.status]} font-medium">{self.get_status_display()}</span></td>'
