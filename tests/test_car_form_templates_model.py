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


def _paper_file(org, page_count=2):
    paper_file = cft.CarFormPaperFile(
        organization=org,
        filename="form.pdf",
        data=b"%PDF-1.4 stub",
        page_count=page_count,
        page_sizes=[[595, 842]] * page_count,
    )
    paper_file.save()
    return paper_file


def _placement(**overrides):
    values = dict(page=0, x=0.1, y=0.1, w=0.3, h=0.05, variable="app.phone")
    values.update(overrides)
    return cft.PaperPlacement(**values)


def _template_with_paper(org, placements, with_file=True):
    template = _template(org, fields=[{"source": "catalog", "key": "province"}])
    if with_file:
        template.paper_file = _paper_file(org)
    template.placements = placements
    return template


def test_template_accepts_placements_of_variables_the_template_really_has(app, create_org):
    """placements ของตัวแปร app.*, details.<key ของฟิลด์>, approvals.<step>.*, org.name ที่ template มีจริง ต้องผ่าน validate()"""
    placements = [
        _placement(variable="app.phone"),
        _placement(variable="app.departure.month_th", page=1),
        _placement(variable="details.province"),
        _placement(variable="approvals.admin.name"),
        _placement(variable="org.name", x=0.7, w=0.3, y=0.95, h=0.05),
    ]

    _template_with_paper(create_org(name="องค์กรทดสอบ"), placements).validate()


PLACEMENT_CASES = {
    "unknown app variable": dict(placements=[_placement(variable="app.no_such")]),
    "details key the template has no field for": dict(
        placements=[_placement(variable="details.district")]
    ),
    "approval step the template does not have": dict(
        placements=[_placement(variable="approvals.head.name")]
    ),
    "page beyond the PDF": dict(placements=[_placement(page=2)]),
    "negative x": dict(placements=[_placement(x=-0.1)]),
    "box sticking out right edge": dict(placements=[_placement(x=0.8, w=0.3)]),
    "box sticking out bottom edge": dict(placements=[_placement(y=0.98, h=0.05)]),
    "placements without a paper file": dict(
        placements=[_placement()], with_file=False
    ),
}


@pytest.mark.parametrize("case", PLACEMENT_CASES)
def test_template_validation_rejects_invalid_placement(app, create_org, case):
    """validate() ต้องปฏิเสธ placement ที่ตัวแปรไม่มีใน template, หน้าเกิน PDF, กล่องหลุดหน้า หรือไม่มี paper_file"""
    template = _template_with_paper(create_org(name="องค์กรทดสอบ"), **PLACEMENT_CASES[case])

    with pytest.raises(me.ValidationError):
        template.validate()
