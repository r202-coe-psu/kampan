import mongoengine as me
import datetime

SUPPLIER_TYPE = [
    ("person", "บุคคล"),
    ("market", "ร้านค้า"),
    ("incorporated", "บริษัท / Inc."),
    ("company limited", "บริษัทจำกัด / Co., Ltd."),
    ("corporation limited", "บริษัทจำกัด (ขนาดใหญ่) / Corp., Ltd."),
    ("public company limited", "บริษัทจำกัด (มหาชน) / Pub Co., Ltd."),
    ("partnership limited", "ห้างหุ้นส่วนจำกัด / Part., Ltd."),
    # ("limited", "จำกัด / Ltd."),
]


class Supplier(me.Document):
    meta = {"collection": "suppliers"}

    company_name = me.StringField(max_length=256)
    person_name = me.StringField(max_length=256)
    supplier_type = me.StringField(
        max_length=256, choices=SUPPLIER_TYPE, default="person"
    )
    description = me.StringField()
    address = me.StringField(required=True, max_length=256)

    status = me.StringField(default="active")
    tax_id = me.StringField(required=True, max_length=256, default="")

    email = me.StringField(max_length=256)
    person_phone = me.StringField(max_length=256)
    company_phone = me.StringField(max_length=256)

    organization = me.ReferenceField("Organization", dbref=True)

    created_by = me.ReferenceField("User", dbref=True)
    last_modifier = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_supplier_name(self):
        if self.supplier_type == "person":
            return self.person_name
        return self.company_name
