import datetime
import mongoengine as me
from dateutil.relativedelta import relativedelta

CATEGORY_CHOICES = [
    ("software", "ซอฟต์แวร์"),
    ("product", "ครุภัณฑ์"),
    ("service", "จ้างเหมาบริการ"),
]

PAYEMENT_STATUS_CHOICES = [
    ("unpaid", "ยังไม่ชำระเงิน"),
    ("overdue", "เลยกำหนดชำระ"),
    ("paid", "ชำระเงินแล้ว"),
    ("upcoming", "ใกล้ครบกำหนด"),
]


class Procurement(me.Document):
    meta = {"collection": "procurements"}

    # Core fields
    product_number = me.StringField(max_length=50, unique=True, required=True)
    asset_code = me.StringField(max_length=50, required=True)
    name = me.StringField(max_length=255, required=True)
    category = me.StringField(max_length=20, choices=CATEGORY_CHOICES, required=True)
    start_date = me.DateTimeField(required=True)
    end_date = me.DateTimeField(required=True)
    amount = me.FloatField(required=True, min_value=0)
    period = me.IntField(required=True, min_value=1)

    # References
    company = me.StringField(max_length=255, required=True)
    payment_status = me.StringField(default=PAYEMENT_STATUS_CHOICES[0][0])

    # Audit fields
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    @classmethod
    def generate_product_number(cls):
        """Generate product number in format มอ 011/YY-N using current Thai Buddhist year"""
        current_year = datetime.datetime.now().year
        thai_year = str(current_year + 543)[-2:]  # Get last 2 digits of Thai year
        prefix = "มอ 011"

        # Find the last procurement for the current Thai year
        last_procurement = (
            cls.objects(product_number__startswith=f"{prefix}/{thai_year}-")
            .order_by("-product_number")
            .first()
        )

        new_number = (
            int(last_procurement.product_number.split("-")[-1]) + 1
            if last_procurement
            else 1
        )
        return f"{prefix}/{thai_year}-{new_number}"

    def save(self, *args, **kwargs):
        """Override save to auto-generate product_number"""
        if not self.product_number:
            self.product_number = self.generate_product_number()
        return super().save(*args, **kwargs)
