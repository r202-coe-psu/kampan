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
            {
                "source": "custom",
                "key": "project_no",
                "label": "เลขที่โครงการ",
                "field_type": "text",
            },
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


def _problems(org, **kwargs):
    template = _template(org, **kwargs)
    with pytest.raises(me.ValidationError) as error:
        template.validate()
    return error.value.errors["__all__"].problems


def _custom(key, label, field_type="text"):
    return {"source": "custom", "key": key, "label": label, "field_type": field_type}


@pytest.mark.parametrize("label", [None, "", "   "])
def test_custom_field_without_a_name_is_reported_by_position(app, create_org, label):
    """ฟิลด์ custom ที่ไม่มีชื่อ (ว่างหรือเว้นวรรค) ต้องถูกแจ้งตามลำดับฟิลด์ ไม่ใช่ตาม key"""
    problems = _problems(
        create_org(name="องค์กรทดสอบ"),
        fields=[_custom("f_aaaa", "วัตถุประสงค์"), _custom("f_bbbb", label)],
    )

    assert problems == ["ฟิลด์ที่ 2: ต้องกรอกชื่อฟิลด์"]


def test_fields_with_the_same_name_are_reported_against_the_first_one(app, create_org):
    """ฟิลด์ที่ชื่อซ้ำกัน (เทียบแบบ trim) ต้องแจ้งชื่อและลำดับของฟิลด์แรกที่ซ้ำด้วย"""
    problems = _problems(
        create_org(name="องค์กรทดสอบ"),
        fields=[
            _custom("f_aaaa", "วัตถุประสงค์"),
            _custom("f_bbbb", "ผู้ติดต่อ"),
            _custom("f_cccc", "  วัตถุประสงค์ "),
        ],
    )

    assert problems == ["ฟิลด์ที่ 3: ชื่อ “วัตถุประสงค์” ซ้ำกับฟิลด์ที่ 1"]


def test_custom_field_named_like_a_catalog_field_default_label_is_a_duplicate(
    app, create_org
):
    """ฟิลด์ catalog ที่ไม่ตั้ง label แสดงด้วยชื่อ default ของ catalog จึงชนกับฟิลด์ custom ที่ตั้งชื่อเดียวกัน"""
    problems = _problems(
        create_org(name="องค์กรทดสอบ"),
        fields=[
            {"source": "catalog", "key": "province"},
            _custom("f_aaaa", "จังหวัด"),
        ],
    )

    assert problems == ["ฟิลด์ที่ 2: ชื่อ “จังหวัด” ซ้ำกับฟิลด์ที่ 1"]


def test_same_catalog_field_chosen_twice_is_reported_once(app, create_org):
    """เลือกฟิลด์ catalog ตัวเดียวกันซ้ำ ต้องแจ้งข้อความ 'เลือกซ้ำ' ข้อความเดียวต่อคู่ (ไม่ซ้ำด้วยข้อความชื่อซ้ำ/key ซ้ำ)"""
    problems = _problems(
        create_org(name="องค์กรทดสอบ"),
        fields=[
            {"source": "catalog", "key": "vehicle_count"},
            _custom("f_aaaa", "ผู้ติดต่อ"),
            {"source": "catalog", "key": "vehicle_count", "label": "จำนวนรถที่ขอ"},
        ],
    )

    assert problems == ["ฟิลด์ที่ 3: เลือก “จำนวนรถ” ซ้ำกับฟิลด์ที่ 1"]


def _named_step(key, label, assigns_vehicle=False):
    step = _step(key, assigns_vehicle=assigns_vehicle)
    step.label = label
    return step


def test_steps_with_the_same_name_are_reported_against_the_first_one(app, create_org):
    """ขั้นอนุมัติที่ชื่อซ้ำกัน (เทียบแบบ trim) ต้องแจ้งชื่อและลำดับของขั้นแรกที่ซ้ำ"""
    problems = _problems(
        create_org(name="องค์กรทดสอบ"),
        steps=[
            _named_step("s_aaaa", "หัวหน้างาน"),
            _named_step("s_bbbb", " หัวหน้างาน", assigns_vehicle=True),
        ],
    )

    assert problems == ["ขั้นที่ 2: ชื่อ “หัวหน้างาน” ซ้ำกับขั้นที่ 1"]


INTERNAL_PROBLEM = "ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่"

BAD_FIELD_KEYS = {
    "thai key": [_custom("ผู้บังคับบัญชา", "ผู้ติดต่อ")],
    "uppercase key": [_custom("Admin", "ผู้ติดต่อ")],
    "key starting with a digit": [_custom("1abc", "ผู้ติดต่อ")],
    "duplicate custom key": [
        _custom("f_aaaa", "ผู้ติดต่อ"),
        _custom("f_aaaa", "วัตถุประสงค์"),
    ],
}


@pytest.mark.parametrize("case", BAD_FIELD_KEYS)
def test_custom_field_with_bad_internal_key_asks_user_to_re_add_it_without_saying_key(
    app, create_org, case
):
    """ฟิลด์ custom ที่ key ผิดรูปแบบหรือซ้ำ ต้องแจ้งเป็น 'ข้อมูลภายในไม่ถูกต้อง' ตามลำดับฟิลด์ และไม่พูดถึงคำว่า key"""
    fields = BAD_FIELD_KEYS[case]

    problems = _problems(create_org(name="องค์กรทดสอบ"), fields=fields)

    assert problems == [f"ฟิลด์ที่ {len(fields)}: {INTERNAL_PROBLEM}"]


BAD_STEP_KEYS = {
    "thai key": [_named_step("ผู้บังคับบัญชา", "ผู้บังคับบัญชา", assigns_vehicle=True)],
    "uppercase key": [_named_step("Admin", "แอดมิน", assigns_vehicle=True)],
    "duplicate step key": [
        _named_step("s_aaaa", "หัวหน้างาน"),
        _named_step("s_aaaa", "ผู้อำนวยการ", assigns_vehicle=True),
    ],
}


@pytest.mark.parametrize("case", BAD_STEP_KEYS)
def test_step_with_bad_internal_key_asks_user_to_re_add_it_without_saying_key(
    app, create_org, case
):
    """ขั้นที่ key ผิดรูปแบบหรือซ้ำ ต้องแจ้งเป็น 'ข้อมูลภายในไม่ถูกต้อง' ตามลำดับขั้น และไม่พูดถึงคำว่า key"""
    steps = BAD_STEP_KEYS[case]

    problems = _problems(create_org(name="องค์กรทดสอบ"), steps=steps)

    assert problems == [f"ขั้นที่ {len(steps)}: {INTERNAL_PROBLEM}"]
