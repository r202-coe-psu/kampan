import re

from kampan.models import car_form_templates as cft
from kampan.utils.car_form_keys import rekey_template

from tests.test_car_form_templates_model import _placement, _step, _template


def _legacy_template(org):
    """template แบบเก่า: custom field และ step ใช้ key ที่ admin ตั้งเอง"""
    template = _template(
        org,
        fields=[
            {"source": "catalog", "key": "province", "label": "จังหวัดปลายทาง"},
            {"source": "custom", "key": "project_no", "label": "เลขที่โครงการ", "field_type": "text"},
            {"source": "custom", "key": "budget", "label": "งบประมาณ", "field_type": "number"},
        ],
        steps=[_step("head", assigns_vehicle=False), _step("admin")],
    )
    template.steps[0].label = "หัวหน้า"
    template.steps[1].label = "ผู้จัดรถ"
    template.paper_file = cft.CarFormPaperFile(
        organization=org, filename="form.pdf", data=b"%PDF-1.4 stub", page_count=1, page_sizes=[[595, 842]]
    )
    template.paper_file.save()
    template.placements = [
        _placement(variable="details.custom_project_no"),
        _placement(variable="details.province"),
        _placement(variable="app.phone"),
        _placement(variable="org.name"),
        _placement(variable="approvals.head.name"),
        _placement(variable="approvals.admin.date"),
        _placement(variable="details.custom_budget"),
    ]
    return template


def _field_key_by_label(template, label):
    return next(f.key for f in template.fields if f.label == label)


def _step_key_by_label(template, label):
    return next(s.key for s in template.steps if s.label == label)


def test_rekey_gives_custom_fields_and_steps_random_keys_and_placements_follow(app, create_org):
    """custom field และ step ได้ key สุ่ม (f_xxxxxx / s_xxxxxx), placement ที่อ้างถึงตามไป, catalog/app/org ไม่ถูกแตะ, validate() ยังผ่าน"""
    template = _legacy_template(create_org(name="องค์กรทดสอบ"))

    field_map, step_map = rekey_template(template)

    project_no = _field_key_by_label(template, "เลขที่โครงการ")
    budget = _field_key_by_label(template, "งบประมาณ")
    head = _step_key_by_label(template, "หัวหน้า")
    admin = _step_key_by_label(template, "ผู้จัดรถ")
    for key in (project_no, budget):
        assert re.fullmatch(r"f_[a-z0-9]{6}", key)
    for key in (head, admin):
        assert re.fullmatch(r"s_[a-z0-9]{6}", key)
    assert len({project_no, budget, head, admin}) == 4

    assert _field_key_by_label(template, "จังหวัดปลายทาง") == "province"
    assert field_map == {"project_no": project_no, "budget": budget}
    assert step_map == {"head": head, "admin": admin}

    assert [p.variable for p in template.placements] == [
        f"details.custom_{project_no}",
        "details.province",
        "app.phone",
        "org.name",
        f"approvals.{head}.name",
        f"approvals.{admin}.date",
        f"details.custom_{budget}",
    ]
    template.validate()


def test_rekey_twice_changes_nothing(app, create_org):
    """เรียก rekey_template ซ้ำ: คืน map ว่าง และ key/placement เดิมทุกตัว"""
    template = _legacy_template(create_org(name="องค์กรทดสอบ"))
    rekey_template(template)
    fields_before = [f.key for f in template.fields]
    steps_before = [s.key for s in template.steps]
    placements_before = [p.variable for p in template.placements]

    field_map, step_map = rekey_template(template)

    assert (field_map, step_map) == ({}, {})
    assert [f.key for f in template.fields] == fields_before
    assert [s.key for s in template.steps] == steps_before
    assert [p.variable for p in template.placements] == placements_before
    template.validate()
