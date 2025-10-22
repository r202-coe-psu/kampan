import datetime
import mongoengine as me
from dateutil.relativedelta import relativedelta

CATEGORY_CHOICES = [
    ("material", "วัสดุ"),
    ("product", "ครุภัณฑ์"),
    ("service", "จ้างเหมาบริการ"),
    ("software", "ซอฟต์แวร์"),
]

PAYEMENT_STATUS_CHOICES = [
    ("unpaid", "ยังไม่ชำระเงิน"),
    ("overdue", "เลยกำหนดชำระ"),
    ("paid", "ชำระเงินแล้ว"),
    ("upcoming", "ใกล้ครบกำหนด"),
]

RENEWAL_STATUS_CHOICES = [
    ("pending", "รอดำเนินการ"),
    ("renewal-requested", "ยื่นขอต่ออายุ"),
    ("disactive", "ไม่อนุมัติ"),
    ("active", "จัดซื้อเรียบร้อย"),
]


class PaymentRecord(me.EmbeddedDocument):
    """Record for each payment period"""

    period_index = me.IntField(required=True)
    product_number = me.StringField(max_length=50, required=True)
    amount = me.DecimalField(required=True, min_value=0, precision=2, max_value=1e12)
    paid_date = me.DateTimeField(required=True)  # วันที่จ่าย
    paid_by = me.ReferenceField("User", dbref=True)  # ผู้ยืนยันการจ่าย
    due_date = me.DateTimeField(required=True)  # วันที่ครบกำหนดของงวดนี้


class Procurement(me.Document):
    meta = {"collection": "procurements"}

    # Core fields
    image = me.ImageField()
    product_number = me.StringField(max_length=50, unique=True, required=True)
    asset_code = me.StringField(max_length=50, required=True)
    name = me.StringField(max_length=255, required=True)
    category = me.StringField(max_length=20, choices=CATEGORY_CHOICES, required=True)
    start_date = me.DateTimeField(required=True)
    end_date = me.DateTimeField(required=True)
    amount = me.DecimalField(required=True, min_value=0, precision=2, max_value=1e12)
    period = me.IntField(required=True, min_value=1)
    quantity = me.IntField(min_value=1, default=1)
    # status: สถานะการต่ออายุ (renewal process)
    status = me.StringField(choices=RENEWAL_STATUS_CHOICES, default="active")

    # References
    company = me.StringField(max_length=255, required=True)
    payment_status = me.StringField(default=PAYEMENT_STATUS_CHOICES[0][0])
    responsible_by = me.ListField(me.ReferenceField("OrganizationUserRole", dbref=True))

    # Audit fields
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )
    paid_period_index = me.IntField(default=-1)  # เปลี่ยนกลับเป็น -1
    payment_records = me.ListField(
        me.EmbeddedDocumentField(PaymentRecord)
    )  # ประวัติการจ่ายเงิน

    def get_payment_due_dates(self):
        """
        Return a list of due dates (datetime.date) for each payment period.
        """
        if (
            not self.start_date
            or not self.end_date
            or not self.period
            or self.period < 1
        ):
            return []

        start = (
            self.start_date.date()
            if isinstance(self.start_date, datetime.date)
            else self.start_date
        )
        end = (
            self.end_date.date()
            if isinstance(self.end_date, datetime.date)
            else self.end_date
        )

        total_days = (end - start).days + 1  # รวมวันสุดท้าย
        days_per_period = total_days // self.period
        remainder = total_days % self.period

        due_dates = []
        current_start = start
        for i in range(self.period):
            days_this_period = days_per_period + (1 if i < remainder else 0)
            current_end = current_start + datetime.timedelta(days=days_this_period - 1)
            # ป้องกันเกิน end_date
            if current_end > end:
                current_end = end
            due_dates.append(current_end)
            current_start = current_end + datetime.timedelta(days=1)
        return due_dates

    def get_next_payment_index(self):
        """
        Return the index (0-based) of the next unpaid period.
        """
        if len(self.payment_records) >= self.period:
            return self.period
        return len(self.payment_records)

    def get_total_payment_record(self):
        total = 0
        for record in self.payment_records:
            total += record.amount
        return total

    def get_remaining_amount(self):
        total_paid = self.get_total_payment_record()
        remaining = self.amount - total_paid
        return remaining

    def is_last_period(self):
        return self.get_next_payment_index() == self.period - 1

    def get_current_payment_status(self, today=None):
        """
        Return payment status string: 'unpaid', 'upcoming', 'overdue', or 'paid'
        - ดูเฉพาะงวดถัดไปที่ยังไม่จ่าย
        """
        if today is None:
            today = datetime.date.today()
        due_dates = self.get_payment_due_dates()

        # ถ้าจ่ายครบทุกงวดแล้ว
        if len(self.payment_records) >= self.period:
            return "paid"

        if not due_dates:
            return "unpaid"

        # หางวดถัดไปที่ยังไม่จ่าย
        next_idx = len(self.payment_records)
        if next_idx >= len(due_dates):
            return "paid"

        due_date = due_dates[next_idx]
        if today > due_date:
            return "overdue"
        elif 0 <= (due_date - today).days <= 7:
            return "upcoming"
        else:
            return "unpaid"

    def add_payment_record(self, period_index, paid_by, amount, product_number=None):
        """Add payment record for specific period, storing product_number at time of payment"""
        due_dates = self.get_payment_due_dates()
        due_date = None
        if 0 <= period_index < len(due_dates):
            due_date = datetime.datetime.combine(
                due_dates[period_index], datetime.time.min
            )
        payment_record = PaymentRecord(
            period_index=period_index,
            paid_date=datetime.datetime.now(),
            paid_by=paid_by,
            due_date=due_date,
            amount=amount,
            product_number=(
                product_number if product_number is not None else self.product_number
            ),
        )
        self.payment_records.append(payment_record)

    def get_payment_record_for_period(self):
        """Get payment record for specific period"""
        for record in self.payment_records:
            if record.period_index == (self.paid_period_index or -1) + 1:
                return record
        return None
