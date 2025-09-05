import datetime
import mongoengine as me

from kampan.models.procurement import CATEGORY_CHOICES


class Requisition(me.Document):
    meta = {"collection": "requisitions"}

    requisition_code = me.StringField(max_length=50, unique=True, required=True)
    purchaser = me.ReferenceField("OrganizationUserRole", dbref=True, required=True)
    phone = me.IntField()
    reason = me.StringField(max_length=255)
    start_date = me.DateTimeField(required=True)
    tor_document = me.FileField(collection_name="tor_documents")

    product_name = me.StringField(max_length=100, required=True)
    quantity = me.IntField(min_value=1, required=True)
    category = me.StringField(max_length=20, choices=CATEGORY_CHOICES, required=True)
    amount = me.DecimalField(required=True, min_value=0, precision=2)
    company = me.StringField(max_length=255, required=True)

    fund = me.ReferenceField("MAS", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)
    created_by = me.ReferenceField("User", dbref=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def save(self, *args, **kwargs):
        if not self.requisition_code:
            # ใช้ปี พ.ศ.
            now = datetime.datetime.now()
            buddhist_year = now.year + 543
            # หาเลขรันนิ่งล่าสุดของปีนี้
            prefix = f"{buddhist_year}-"
            last = (
                Requisition.objects(requisition_code__startswith=prefix)
                .order_by("-requisition_code")
                .first()
            )
            if last and last.requisition_code:
                last_number = int(last.requisition_code.split("-")[1])
                next_number = last_number + 1
            else:
                next_number = 1
            self.requisition_code = f"{buddhist_year}-{next_number:04d}"
        return super().save(*args, **kwargs)
