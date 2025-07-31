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


class ToRYear(me.Document):
    year = me.StringField(requred=True, max_length=100)
    started_date = me.DateTimeField(required=True)
    ended_date = me.DateTimeField(required=True)

    created_by = me.ReferenceField("User", dbref=True, required=True)
    last_updated_by = me.ReferenceField("User", dbref=True, required=True)
    status = me.StringField(required=True, default="active")
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    meta = {"collection": "tor_years"}


class PaymentRecord(me.EmbeddedDocument):
    """Record for each payment period"""

    period_index = me.IntField(required=True)
    paid_date = me.DateTimeField(required=True)  # วันที่จ่าย
    paid_by = me.ReferenceField("User", dbref=True)  # ผู้ยืนยันการจ่าย
    due_date = me.DateTimeField(required=True)  # วันที่ครบกำหนดของงวดนี้


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
    tor_year = me.ReferenceField(ToRYear, dbref=True)
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

    @classmethod
    def generate_product_number(cls, tor_year=None):
        """
        Generate product number in format มอ 011/YY-N using the last 2 digits of ToRYear.year.
        """
        import datetime

        prefix = "มอ 011"
        if tor_year and tor_year.year:
            thai_year = str(tor_year.year)[-2:]  # Use last 2 digits of the ToR year
        else:
            current_year = datetime.datetime.now().year
            thai_year = str(current_year + 543)[-2:]  # Default to current Buddhist year

        # Query all matching product numbers in that year
        year_prefix = f"{prefix}/{thai_year}-"
        matching_products = cls.objects(product_number__startswith=year_prefix)

        # Extract number after the dash and convert to int
        last_number = 0
        for item in matching_products:
            try:
                number_part = int(item.product_number.split("-")[-1])
                if number_part > last_number:
                    last_number = number_part
            except (ValueError, IndexError):
                continue

        new_number = last_number + 1
        return f"{prefix}/{thai_year}-{new_number}"

    def save(self, *args, **kwargs):
        """Override save to auto-generate product_number"""
        if not self.product_number:
            tor_year = getattr(self, "tor_year", None)
            self.product_number = self.generate_product_number(tor_year=tor_year)
        return super().save(*args, **kwargs)

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
            if hasattr(self.start_date, "date")
            else self.start_date
        )
        end = self.end_date.date() if hasattr(self.end_date, "date") else self.end_date

        total_days = (end - start).days
        if total_days < 1:
            return []

        period_days = total_days // self.period
        due_dates = []
        for i in range(1, self.period + 1):
            due_date = start + datetime.timedelta(days=period_days * i)
            # อย่าให้เกิน end_date
            if due_date > end:
                due_date = end
            due_dates.append(due_date)
        return due_dates

    def get_next_payment_index(self):
        """
        Return the index (0-based) of the next unpaid period.
        """
        if self.payment_status == "paid":
            return self.period  # หมายถึงจ่ายครบทุกงวดแล้ว
        return (self.paid_period_index or -1) + 1

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
        elif today <= due_date <= today + datetime.timedelta(days=7):
            return "upcoming"
        else:
            return "unpaid"

    def add_payment_record(self, period_index, paid_by):
        """Add payment record for specific period"""
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
        )
        self.payment_records.append(payment_record)

    def get_payment_record_for_period(self):
        """Get payment record for specific period"""
        for record in self.payment_records:
            if record.period_index == (self.paid_period_index or -1) + 1:
                return record
        return None
        for record in self.payment_records:
            if record.period_index == (self.paid_period_index or -1) + 1:
                return record
        return None
