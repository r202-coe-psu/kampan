import mongoengine as me
import datetime
import markdown
import json

from flask import url_for, request
from kampan import models

ORGANIZATION_ROLES = [
    ("staff", "พนักงาน"),
    ("endorser", "ผู้มีสิทธิ์อนุมัติ"),
    ("head", "หัวหน้าฝ่าย"),
    ("supervisor supplier", "หัวหน้าฝ่ายบริหารจัดการ"),
    ("admin", "ผู้ดูแล/เจ้าหน้าที่พัสดุ"),
    ("driver", "พนักงานขับรถ"),
    ("director", "ผู้อำนวยการ"),
    ("manager", "ผู้บริหาร"),
    # ตำแหน่งผู้อนุมัติของระบบจองรถ key ตรงกับ step key ของเส้นทางอนุมัติ
    ("dispatcher", "ผู้จัดรถ"),
    ("vehicle_unit_head", "หัวหน้าหน่วยยานพาหนะ"),
    ("strategy_head", "หัวหน้างานยุทธศาสตร์และบริการกลาง"),
    ("physical_director", "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม"),
    ("vice_president_hatyai", "รองอธิการบดีวิทยาเขตหาดใหญ่"),
    ("president", "อธิการบดี"),
]

# role ที่ org ใช้ได้เมื่อยังไม่เคยตั้ง enabled_roles (8 role เดิม)
DEFAULT_ENABLED_ROLE_KEYS = [
    "staff",
    "endorser",
    "head",
    "supervisor supplier",
    "admin",
    "driver",
    "director",
    "manager",
]

# role ผู้อนุมัติของระบบจองรถ (ผู้ถือ driver ร่วมด้วยไม่ได้)
RESERVATION_APPROVER_ROLE_KEYS = [
    "dispatcher",
    "vehicle_unit_head",
    "strategy_head",
    "physical_director",
    "vice_president_hatyai",
    "president",
]

ORGANIZATION_USER_ROLE_STATUS = [
    ("active", "เข้าสู่ระบบแล้ว"),
    ("disactive", "นำออกแล้ว"),
    ("pending", "รอการเข้าสู่ระบบ"),
]

MODULES = [
    ("inventory", "ระบบพัสดุ/เบิกของ"),
    ("procurement", "ระบบจัดซื้อจัดจ้าง"),
    ("car", "ระบบขอใช้รถยนต์"),
    ("car_reservation", "ระบบจองรถออนไลน์"),
    ("motorcycle", "ระบบขอใช้รถจักรยานยนต์"),
]

class OrganizationUserRole(me.Document):
    meta = {"collection": "organization_user_roles"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    division = me.ReferenceField("Division", dbref=True)
    user = me.ReferenceField("User", dbref=True)
    roles = me.ListField(
        me.StringField(choices=ORGANIZATION_ROLES), default=["staff"], required=True
    )

    first_name = me.StringField(default="")
    last_name = me.StringField(default="")
    email = me.StringField(default="")
    appointment = me.StringField(default="")

    last_ip_address = me.StringField()
    status = me.StringField(default="active", choices=ORGANIZATION_USER_ROLE_STATUS)

    added_by = me.ReferenceField("User", dbref=True, required=True)
    last_modifier = me.ReferenceField("User", dbref=True, required=True)
    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def role_items(self):
        """Return [(role_key, label), ...] for each known role of this member."""
        role_labels = dict(ORGANIZATION_ROLES)
        return [(role, role_labels[role]) for role in self.roles if role in role_labels]

    def display_roles(self):
        roles = []
        for role in self.roles:
            for organization_role, display_role in ORGANIZATION_ROLES:
                if role == organization_role:
                    roles.append(display_role)
        return " ,".join(roles)

    def display_fullname(self):
        if self.user:
            return self.user.get_resources_fullname()
        return self.first_name + " " + self.last_name

    def display_name(self):
        return self.first_name + " " + self.last_name

    def display_user_fullname(self):
        if self.user:
            return self.user.get_resources_fullname_th()
        return self.first_name + " " + self.last_name

    def display_email(self):
        if self.user:
            return self.user.email
        return self.email

    def display_appointment(self):
        if len(self.appointment) >= 30:
            return self.appointment[:30] + "..."

        return self.appointment


class Organization(me.Document):
    meta = {"collection": "organizations"}

    name = me.StringField(min_length=4, max_length=255, required=True)
    description = me.StringField()
    # authenticity_text = me.StringField(required=True, default="")

    status = me.StringField(required=True, default="active")

    # None = ยังไม่เคยตั้งค่า ถือว่าเปิดทุกโมดูล (ListField ปกติ default เป็น [])
    enabled_modules = me.ListField(me.StringField(choices=MODULES), default=None)

    # None = ยังไม่เคยตั้งค่า ใช้ 8 role เดิม (role ผู้อนุมัติของระบบจองรถซ่อนจนกว่าจะเปิด)
    enabled_roles = me.ListField(me.StringField(choices=ORGANIZATION_ROLES), default=None)

    # เบอร์ติดต่อฝ่ายจองรถ แสดงในหน้ายืนยันขอใช้รถกะทันหัน (ว่าง = ไม่แสดง)
    car_reservation_contact_phone = me.StringField(default="", max_length=32)

    # ช่วง IP (CIDR) ของมหาวิทยาลัย ใช้ตรวจว่า พขร. ปิดงานจากในมหาวิทยาลัยหรือไม่ (ว่าง = ไม่ตรวจ)
    car_reservation_campus_networks = me.ListField(me.StringField())

    created_by = me.ReferenceField("User", dbref=True)
    last_updated_by = me.ReferenceField("User", dbref=True)

    created_date = me.DateTimeField(required=True, default=datetime.datetime.now)
    updated_date = me.DateTimeField(
        required=True, default=datetime.datetime.now, auto_now=True
    )

    def get_description(self):
        return markdown.markdown(self.description)

    def has_module(self, key):
        return self.enabled_modules is None or key in self.enabled_modules

    def available_roles(self):
        """[(key, label), ...] ของ role ที่ org นี้เลือกใช้ได้ เรียงตาม ORGANIZATION_ROLES"""
        enabled = (
            DEFAULT_ENABLED_ROLE_KEYS
            if self.enabled_roles is None
            else self.enabled_roles
        )
        return [(key, label) for key, label in ORGANIZATION_ROLES if key in enabled]

    def get_distinct_users(self):
        if OrganizationUserRole.objects().count():
            return (
                OrganizationUserRole.objects(organization=self, status="active")
                .order_by("-first_name")
                .distinct(field="user")
            )

    def get_organization_users(self, division=None):
        if OrganizationUserRole.objects().count():
            if not division:
                return OrganizationUserRole.objects(
                    organization=self, status__ne="disactive"
                ).order_by("-first_name")
            return OrganizationUserRole.objects(
                organization=self, status__ne="disactive", division=division
            ).order_by("-first_name")

    def get_logo(self):
        return Logo.objects(organization=self, marked_as_organization_logo=True).first()

    def get_logo_picture(self):
        logo = Logo.objects(organization=self, marked_as_organization_logo=True).first()
        if logo:
            return url_for(
                "organizations.download_logo",
                organization_id=self.id,
                logo_id=logo.id,
                filename=logo.logo_file.filename,
                thumbnail="thumbnail",
            )

        return url_for("static", filename="images/globe.png")

    def get_logos(self):
        return models.Logo.objects(organization=self).order_by("-id")

    def get_logo_ids(self):
        return [
            str(l.id) for l in models.Logo.objects(organization=self).order_by("-id")
        ]

    def get_url_download_logo_images(self, format=""):
        logos = models.Logo.objects(organization=self)
        data = []

        for logo in logos:
            data.append(
                dict(
                    id=str(logo.id),
                    uri=url_for(
                        "organizations.download_logo",
                        organization_id=self.id,
                        logo_id=logo.id,
                        thumbnail="thumbnail",
                        filename=logo.logo_file.filename,
                    ),
                )
            )

        if format == "json":
            return json.dumps(data)

        return data

    def get_classes(self):
        return models.Class.objects(organization=self, status="active").order_by("-id")

    def get_endorsers(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["endorser"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_admins(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["admin"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_heads(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["head"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_heads_by_division(self, division):
        if not division:
            return self.get_heads()

        head_roles = models.OrganizationUserRole.objects(
            organization=self, division=division, roles__in=["head"], status="active"
        )
        user_ids = [role.user.id for role in head_roles if role.user]
        return models.User.objects(id__in=user_ids)

    def get_default_email_template(self, email_type):
        try:
            email_template = models.EmailTemplate.objects(
                organization=self, is_default=True, type=email_type
            ).first()
        except:
            email_template = models.EmailTemplate.objects(
                organization=self, is_default=True
            ).first()
        return email_template

    def get_supervisor_supplier(self):
        endorsers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["supervisor supplier"], status="active"
        )
        user_ids = [endorser.user.id for endorser in endorsers_in_org]
        return models.User.objects(id__in=user_ids)

    def get_director(self):
        directors_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["director"], status="active"
        )
        user_ids = [director.user.id for director in directors_in_org if director.user]
        return models.User.objects(id__in=user_ids)

    def get_all_drivers(self):
        drivers_in_org = models.OrganizationUserRole.objects(
            organization=self, roles__in=["driver"], status="active"
        )
        user_ids = [driver.user.id for driver in drivers_in_org]
        return models.User.objects(id__in=user_ids)


class Logo(me.Document):
    meta = {"collection": "logos"}

    organization = me.ReferenceField("Organization", dbref=True, required=True)
    logo_name = me.StringField(required=True, max_length=256)
    logo_file = me.ImageField(
        required=True,
        collection_name="logo_fs",
        size=(3840, 2160, False),
        thumbnail_size=(1920, 1920, False),
    )

    uploaded_by = me.ReferenceField("User", dbref=True)
    uploaded_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    last_updated_by = me.ReferenceField("User", dbref=True)
    updated_date = me.DateTimeField(required=True, default=datetime.datetime.now)

    marked_as_organization_logo = me.BooleanField(default=False)
