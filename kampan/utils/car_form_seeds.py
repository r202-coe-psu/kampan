from kampan import models

cft = models.car_form_templates

def _physical_domestic(approver_user):
    if approver_user is not None:
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="user",
            user=approver_user,
        )
    else:
        # ไม่ระบุตัวผู้อนุมัติ: fallback เป็น role endorser (ต้องระบุตัวคนภายหลัง)
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="role",
            role="endorser",
        )
    return dict(
        name="ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ",
        fields=[
            cft.FormFieldDef(source="catalog", key="vehicle_kind", is_required=True),
            cft.FormFieldDef(source="catalog", key="vehicle_count"),
            cft.FormFieldDef(source="catalog", key="district"),
            cft.FormFieldDef(source="catalog", key="province", is_required=True),
            cft.FormFieldDef(source="catalog", key="cost_responsibility"),
            cft.FormFieldDef(
                source="custom",
                key="project_no",
                label="เลขที่โครงการ/หนังสือ",
                field_type="text",
            ),
        ],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="ผู้บังคับบัญชาผู้ขอใช้รถ",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
            approver_step,
            cft.ApprovalStepDef(
                key="director",
                label="ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
                approver_type="role",
                role="director",
            ),
        ],
    )


def _diis_general(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)",
        fields=[],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="หัวหน้าฝ่าย",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้ควบคุมยานพาหนะ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
        ],
    )


_BUILDERS = {
    "diis_general": _diis_general,
    "physical_domestic": _physical_domestic,
}
TEMPLATE_KEYS = tuple(_BUILDERS)


def seed_template(organization, key, created_by=None, approver_user=None):
    spec = _BUILDERS[key](approver_user)
    existing = cft.CarFormTemplate.objects(
        organization=organization, name=spec["name"]
    ).first()
    if existing:
        return existing
    template = cft.CarFormTemplate(
        organization=organization,
        created_by=created_by,
        last_updated_by=created_by,
        **spec,
    )
    template.save()
    return template

