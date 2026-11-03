import mongoengine as me
import pytest

from kampan import models

cft = models.car_form_templates


def _step(key="admin", assigns_vehicle=True):
    return cft.ApprovalStepDef(
        key=key,
        label=key,
        approver_type="role",
        role="admin",
        assigns_vehicle=assigns_vehicle,
    )


def _template(org, fields=None, steps="default"):
    return cft.CarFormTemplate(
        organization=org,
        name="template ทดสอบ",
        fields=[cft.FormFieldDef(**f) for f in (fields or [])],
        steps=[_step()] if steps == "default" else steps,
    )


def test_valid_template_with_catalog_and_custom_fields_passes_validation(app, create_org):
    """template ที่ฟิลด์ catalog ถูกต้อง, choices เป็นสับเซต, custom มี field_type และมีขั้นจัดรถ 1 ขั้น ต้องผ่าน validate()"""
    template = _template(
        create_org(name="องค์กรทดสอบ"),
        fields=[
            {"source": "catalog", "key": "vehicle_kind", "choices": ["ตู้", "เก๋ง"]},
            {"source": "custom", "key": "project_no", "field_type": "text"},
        ],
    )

    template.validate()


INVALID_CASES = {
    "catalog key not in CATALOG": dict(
        fields=[{"source": "catalog", "key": "no_such_field"}]
    ),
    "catalog choices not a subset": dict(
        fields=[{"source": "catalog", "key": "vehicle_kind", "choices": ["เรือ"]}]
    ),
    "custom without field_type": dict(
        fields=[{"source": "custom", "key": "project_no"}]
    ),
    "zero steps": dict(steps=[]),
    "no assigns_vehicle step": dict(steps=[_step("a", assigns_vehicle=False)]),
    "two assigns_vehicle steps": dict(steps=[_step("a"), _step("b")]),
}


@pytest.mark.parametrize("case", INVALID_CASES)
def test_template_validation_rejects_invalid_definition(app, create_org, case):
    """validate() ต้องปฏิเสธ template ที่นิยามไม่ถูกต้องด้วย ValidationError"""
    template = _template(create_org(name="องค์กรทดสอบ"), **INVALID_CASES[case])

    with pytest.raises(me.ValidationError):
        template.validate()
