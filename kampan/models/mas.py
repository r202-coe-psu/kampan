import datetime
import mongoengine as me

STATUS_CHOICES = [
    ("active", "ใช้งาน"),
    ("inactive", "ไม่ใช้งาน"),
    ("completed", "เสร็จสิ้น"),
    ("cancelled", "ยกเลิก"),
]


class MASProject(me.Document):
    """MAS (Management Accounting System) Project Model"""

    meta = {"collection": "mas_projects"}

    # Core identification fields
    mas_code = me.StringField(
        max_length=50,
        required=True,
        unique=True,
        help_text="รหัสแหล่งเงิน เช่น 0.0EU310108.N28.66",
    )

    # Expense categories
    expense_category = me.StringField(
        max_length=50,
        required=True,
        help_text="หมวดรายจ่าย (หมวดหมู่ใหญ่ของค่าใช้จ่าย)",
    )

    expense_subcategory = me.StringField(
        max_length=50,
        required=True,
        help_text="หมวดรายจ่ายย่อย (หมวดที่เจาะจงยิ่งขึ้น)",
    )

    # Project information
    project_name = me.StringField(
        max_length=500,
        required=True,
        help_text="ชื่อโครงการ/คำอธิบาย เช่น โครงการจ้างเหมาพัฒนาฐานโครงสร้างระบบ",
    )

    project_description = me.StringField(help_text="รายละเอียดโครงการ")

    # Financial information
    amount = me.FloatField(required=True, min_value=0, help_text="จำนวนเงินที่ใช้")

    budget = me.FloatField(required=True, min_value=0, help_text="วงเงินประมาณที่ตั้งไว้")

    actual_payment = me.FloatField(default=0, min_value=0, help_text="จำนวนเงินที่จ่ายจริง")

    # Additional fields
    fiscal_year = me.StringField(max_length=10, help_text="ปีงบประมาณ เช่น 2567")

    start_date = me.DateTimeField(help_text="วันที่เริ่มโครงการ")

    end_date = me.DateTimeField(help_text="วันที่สิ้นสุดโครงการ")

    status = me.StringField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        help_text="สถานะโครงการ",
    )

    # Organization references
    organization = me.ReferenceField("Organization", dbref=True)
    responsible_by = me.ListField(me.ReferenceField("OrganizationUserRole", dbref=True))

    # Audit fields
    created_by = me.ReferenceField("User", dbref=True, required=True)
    last_updated_by = me.ReferenceField("User", dbref=True, required=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def __str__(self):
        return f"{self.mas_code} - {self.project_name}"

    @property
    def remaining_budget(self):
        """Calculate remaining budget"""
        return self.budget - self.actual_payment

    @property
    def budget_utilization_percentage(self):
        """Calculate budget utilization percentage"""
        if self.budget == 0:
            return 0
        return (self.actual_payment / self.budget) * 100

    @property
    def is_over_budget(self):
        """Check if actual payment exceeds budget"""
        return self.actual_payment > self.budget

    @property
    def expense_category_display(self):
        """Get display name for expense category"""
        return self.expense_category

    @property
    def expense_subcategory_display(self):
        """Get display name for expense subcategory"""
        return self.expense_subcategory

    @property
    def status_display(self):
        """Get display name for status"""
        return dict(STATUS_CHOICES).get(self.status, self.status)

    @classmethod
    def get_by_fiscal_year(cls, fiscal_year):
        """Get all projects by fiscal year"""
        return cls.objects(fiscal_year=fiscal_year)

    @classmethod
    def get_by_expense_category(cls, category):
        """Get all projects by expense category"""
        return cls.objects(expense_category=category)

    @classmethod
    def get_total_budget_by_category(cls, category, fiscal_year=None):
        """Get total budget by category and optionally by fiscal year"""
        query = cls.objects(expense_category=category)
        if fiscal_year:
            query = query.filter(fiscal_year=fiscal_year)

        total = 0
        for project in query:
            total += project.budget
        return total

    @classmethod
    def get_total_actual_payment_by_category(cls, category, fiscal_year=None):
        """Get total actual payment by category and optionally by fiscal year"""
        query = cls.objects(expense_category=category)
        if fiscal_year:
            query = query.filter(fiscal_year=fiscal_year)

        total = 0
        for project in query:
            total += project.actual_payment
        return total
