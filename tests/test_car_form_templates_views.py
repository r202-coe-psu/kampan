import io
import json
import re

import pytest
from reportlab.pdfgen import canvas

from kampan import models

BASE = "/vehicle_lending/car_form_templates"


@pytest.fixture
def setup(create_org, create_user, assign_user_to_org):
    org = create_org(name="กองกายภาพ")
    admin = create_user("Admin", "User")
    staff = create_user("Staff", "User")
    approver = create_user("Approver", "User")
    assign_user_to_org(admin, org, roles=["admin"])
    assign_user_to_org(staff, org, roles=["staff"])
    assign_user_to_org(approver, org, roles=["head"])
    return {"org": org, "admin": admin, "staff": staff, "approver": approver}


def valid_payload(org, **overrides):
    data = {
        "organization_id": str(org.id),
        "name": "ใบขอใช้รถทั่วไป",
        "description": "ใช้กับงานทั่วไป",
        "fields_data": json.dumps(
            [
                {"source": "catalog", "key": "district", "is_required": True},
                {
                    "source": "custom",
                    "key": "note",
                    "label": "หมายเหตุ",
                    "field_type": "text",
                    "is_required": False,
                },
            ]
        ),
        "steps_data": json.dumps(
            [
                {
                    "key": "head",
                    "label": "ผู้บังคับบัญชา",
                    "approver_type": "role",
                    "role": "head",
                    "same_division": True,
                    "assigns_vehicle": False,
                },
                {
                    "key": "admin",
                    "label": "ผู้จัดรถ",
                    "approver_type": "role",
                    "role": "admin",
                    "same_division": False,
                    "assigns_vehicle": True,
                },
            ]
        ),
    }
    data.update(overrides)
    return data


def test_org_admin_creates_template_with_fields_and_steps(app, setup, login_as):
    """An org admin creates a template by posting name, fields_data, steps_data; it is saved for that org with the given fields and steps"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["admin"])

    res = client.get(f"{BASE}/create", query_string={"organization_id": str(org.id)})
    assert res.status_code == 200

    res = client.post(f"{BASE}/create", data=valid_payload(org))
    assert res.status_code == 302

    template = models.car_form_templates.CarFormTemplate.objects(organization=org).get()
    assert template.name == "ใบขอใช้รถทั่วไป"
    assert [(f.source, f.key, f.is_required) for f in template.fields] == [
        ("catalog", "district", True),
        ("custom", "note", False),
    ]
    assert [(s.key, s.role, s.same_division, s.assigns_vehicle) for s in template.steps] == [
        ("head", "head", True, False),
        ("admin", "admin", False, True),
    ]


def test_create_with_empty_keys_generates_distinct_random_keys(app, setup, login_as):
    """When an admin creates a template whose custom fields and steps have empty keys, the saved template gets f_xxxxxx / s_xxxxxx keys, all distinct, and catalog fields keep their catalog key"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["admin"])
    fields = [
        {"source": "catalog", "key": "district", "is_required": True},
        {"source": "custom", "key": "", "label": "ชื่อโครงการ", "field_type": "text"},
        {"source": "custom", "key": "", "label": "งบประมาณ", "field_type": "text"},
    ]
    steps = [
        {"key": "", "label": "ผู้บังคับบัญชา", "approver_type": "role", "role": "head"},
        {
            "key": "",
            "label": "ผู้จัดรถ",
            "approver_type": "role",
            "role": "admin",
            "assigns_vehicle": True,
        },
    ]

    res = client.post(
        f"{BASE}/create",
        data=valid_payload(
            org, fields_data=json.dumps(fields), steps_data=json.dumps(steps)
        ),
    )

    assert res.status_code == 302
    template = models.car_form_templates.CarFormTemplate.objects(organization=org).get()
    assert template.fields[0].key == "district"
    custom_keys = [f.key for f in template.fields[1:]]
    step_keys = [s.key for s in template.steps]
    assert all(re.fullmatch(r"f_[a-z0-9]{6}", k) for k in custom_keys)
    assert all(re.fullmatch(r"s_[a-z0-9]{6}", k) for k in step_keys)
    assert len(set(custom_keys + step_keys)) == 4


def count_templates(org):
    return models.car_form_templates.CarFormTemplate.objects(organization=org).count()


@pytest.mark.parametrize(
    "bad_fields, bad_steps",
    [
        (
            None,
            [
                {"key": "a", "label": "A", "role": "head", "assigns_vehicle": True},
                {"key": "b", "label": "B", "role": "admin", "assigns_vehicle": True},
            ],
        ),
        ([{"source": "catalog", "key": "no_such_key"}], None),
    ],
    ids=["two_assigns_vehicle_steps", "unknown_catalog_key"],
)
def test_invalid_definition_is_not_saved_and_form_shows_error(
    app, setup, login_as, bad_fields, bad_steps
):
    """Posting an invalid definition (e.g. two assigns_vehicle steps or unknown catalog key) does not save and re-renders the form with an error"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["admin"])
    overrides = {}
    if bad_fields is not None:
        overrides["fields_data"] = json.dumps(bad_fields)
    if bad_steps is not None:
        overrides["steps_data"] = json.dumps(bad_steps)

    res = client.post(f"{BASE}/create", data=valid_payload(org, **overrides))

    assert res.status_code == 200
    assert 'id="templateError"' in res.get_data(as_text=True)
    assert count_templates(org) == 0


def test_non_admin_member_cannot_create_or_list_templates(app, setup, login_as):
    """A non-admin member (staff) cannot create or list templates"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["staff"])

    create_res = client.post(f"{BASE}/create", data=valid_payload(org))
    list_res = client.get(f"{BASE}/", query_string={"organization_id": str(org.id)})

    # the app's 403 handler redirects to /login
    assert create_res.status_code == 302
    assert "/login" in create_res.headers["Location"]
    assert list_res.status_code == 302
    assert "/login" in list_res.headers["Location"]
    assert count_templates(org) == 0


def create_template(org, admin, **overrides):
    template = models.car_form_templates.CarFormTemplate(
        organization=org,
        name=overrides.pop("name", "เดิม"),
        steps=[
            models.car_form_templates.ApprovalStepDef(
                key="admin", label="ผู้จัดรถ", role="admin", assigns_vehicle=True
            )
        ],
        created_by=admin,
        **overrides,
    )
    template.save()
    return template


def test_editing_a_template_updates_its_steps(app, setup, login_as):
    """Editing a template updates its steps"""
    org = setup["org"]
    template = create_template(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = client.get(
        f"{BASE}/{template.id}/edit", query_string={"organization_id": str(org.id)}
    )
    assert res.status_code == 200

    res = client.post(
        f"{BASE}/{template.id}/edit",
        data=valid_payload(org, name="ใหม่"),
    )
    assert res.status_code == 302

    template.reload()
    assert template.name == "ใหม่"
    assert [s.key for s in template.steps] == ["head", "admin"]
    assert count_templates(org) == 1


def test_admin_of_another_org_cannot_edit_template(
    app, setup, create_org, create_user, assign_user_to_org, login_as
):
    """An admin of org B cannot edit org A's template"""
    org_a = setup["org"]
    template = create_template(org_a, setup["admin"], name="ของ A")
    org_b = create_org(name="Org B")
    admin_b = create_user("Boss", "B")
    assign_user_to_org(admin_b, org_b, roles=["admin"])
    client = login_as(app.test_client(), admin_b)

    get_res = client.get(
        f"{BASE}/{template.id}/edit", query_string={"organization_id": str(org_b.id)}
    )
    post_res = client.post(
        f"{BASE}/{template.id}/edit", data=valid_payload(org_b, name="ถูกแก้")
    )

    assert get_res.status_code == 404
    assert post_res.status_code == 404
    template.reload()
    assert template.name == "ของ A"
    assert [s.key for s in template.steps] == ["admin"]


def user_step_payload(org, user_id):
    return valid_payload(
        org,
        steps_data=json.dumps(
            [
                {
                    "key": "boss",
                    "label": "ผู้อนุมัติระบุตัวคน",
                    "approver_type": "user",
                    "user": user_id,
                },
                {"key": "admin", "label": "ผู้จัดรถ", "role": "admin", "assigns_vehicle": True},
            ]
        ),
    )


def test_user_step_with_non_member_is_rejected(app, setup, create_user, login_as):
    """A user step whose user is not a member of the org is rejected"""
    org = setup["org"]
    outsider = create_user("Outsider", "Other")
    client = login_as(app.test_client(), setup["admin"])

    res = client.post(f"{BASE}/create", data=user_step_payload(org, str(outsider.id)))

    assert res.status_code == 200
    assert 'id="templateError"' in res.get_data(as_text=True)
    assert count_templates(org) == 0


def test_user_step_with_org_member_is_saved_with_that_user(app, setup, login_as):
    """A user step naming a member of the org is saved with that user"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["admin"])

    res = client.post(
        f"{BASE}/create", data=user_step_payload(org, str(setup["approver"].id))
    )

    assert res.status_code == 302
    template = models.car_form_templates.CarFormTemplate.objects(organization=org).get()
    assert template.steps[0].approver_type == "user"
    assert template.steps[0].user == setup["approver"]


def test_delete_sets_status_disactive_and_template_leaves_the_index(app, setup, login_as):
    """Delete sets status disactive and it disappears from the index list"""
    org = setup["org"]
    template = create_template(org, setup["admin"], name="แบบที่จะลบ")
    client = login_as(app.test_client(), setup["admin"])
    query = {"organization_id": str(org.id)}

    before = client.get(f"{BASE}/", query_string=query)
    assert before.status_code == 200
    assert "แบบที่จะลบ" in before.get_data(as_text=True)

    res = client.post(f"{BASE}/{template.id}/delete", data=query)
    assert res.status_code == 302

    template.reload()
    assert template.status == "disactive"
    after = client.get(f"{BASE}/", query_string=query)
    assert "แบบที่จะลบ" not in after.get_data(as_text=True)


def make_pdf(pages=2, size=(595, 842)):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=size)
    for number in range(pages):
        pdf.drawString(100, 700, f"page {number + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def upload_pdf(client, org, template, content, filename="form.pdf"):
    return client.post(
        f"{BASE}/{template.id}/paper_file",
        data={"organization_id": str(org.id), "pdf": (io.BytesIO(content), filename)},
        content_type="multipart/form-data",
    )


def test_admin_uploads_pdf_and_template_points_to_new_paper_file(app, setup, login_as):
    """An admin uploads a PDF for a template; it is stored as a new CarFormPaperFile of the org with its page count and the template points to it"""
    org = setup["org"]
    template = create_template(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    first = upload_pdf(client, org, template, make_pdf(pages=2), "ใบขอใช้รถ.pdf")
    template.reload()
    first_file = template.paper_file
    second = upload_pdf(client, org, template, make_pdf(pages=3))
    template.reload()

    assert first.status_code == 302
    assert second.status_code == 302
    assert first_file.organization == org
    assert first_file.filename == "ใบขอใช้รถ.pdf"
    assert first_file.page_count == 2
    assert first_file.page_sizes == [[595.0, 842.0], [595.0, 842.0]]
    assert template.paper_file.page_count == 3
    assert template.paper_file.id != first_file.id
    assert models.car_form_templates.CarFormPaperFile.objects(organization=org).count() == 2


@pytest.mark.parametrize(
    "content, filename",
    [
        (b"hello, not a pdf", "note.pdf"),
        (b"%PDF-1.4 but actually garbage", "broken.pdf"),
        (make_pdf(pages=1) + b"\0" * (10 * 1024 * 1024), "huge.pdf"),
    ],
    ids=["text_file", "corrupt_pdf", "over_10mb"],
)
def test_invalid_pdf_upload_is_rejected_and_template_unchanged(
    app, setup, login_as, content, filename
):
    """A non-PDF (text, corrupt or over 10 MB) upload is rejected with an error and the template is unchanged"""
    org = setup["org"]
    template = create_template(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = upload_pdf(client, org, template, content, filename)

    assert res.status_code == 400
    assert 'id="paperError"' in res.get_data(as_text=True)
    template.reload()
    assert template.paper_file is None
    assert models.car_form_templates.CarFormPaperFile.objects(organization=org).count() == 0


def template_with_paper(org, admin, pages=2):
    pdf_bytes = make_pdf(pages=pages)
    paper = models.car_form_templates.CarFormPaperFile(
        organization=org,
        filename="form.pdf",
        data=pdf_bytes,
        page_count=pages,
        page_sizes=[[595.0, 842.0]] * pages,
        uploaded_by=admin,
    )
    paper.save()
    return create_template(org, admin, paper_file=paper), pdf_bytes


def test_get_paper_file_returns_the_pdf_to_org_admin(app, setup, login_as):
    """GET /<id>/paper_file returns the template's PDF to org admins"""
    org = setup["org"]
    template, pdf_bytes = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = client.get(
        f"{BASE}/{template.id}/paper_file", query_string={"organization_id": str(org.id)}
    )

    assert res.status_code == 200
    assert res.mimetype == "application/pdf"
    assert res.data == pdf_bytes


def test_get_paper_file_is_404_for_another_org(
    app, setup, create_org, create_user, assign_user_to_org, login_as
):
    """GET /<id>/paper_file returns 404 to an admin of another org"""
    template, _ = template_with_paper(setup["org"], setup["admin"])
    org_b = create_org(name="Org B")
    admin_b = create_user("Boss", "B")
    assign_user_to_org(admin_b, org_b, roles=["admin"])
    client = login_as(app.test_client(), admin_b)

    res = client.get(
        f"{BASE}/{template.id}/paper_file", query_string={"organization_id": str(org_b.id)}
    )

    assert res.status_code == 404


def save_placements(client, org, template, placements):
    data = {
        "organization_id": str(org.id),
        "placements_data": placements if isinstance(placements, str) else json.dumps(placements),
    }
    return client.post(f"{BASE}/{template.id}/placements", data=data)


def placement(**overrides):
    data = {
        "page": 0,
        "x": 0.1,
        "y": 0.2,
        "w": 0.3,
        "h": 0.05,
        "variable": "app.location",
        "kind": "text",
        "match_value": "",
        "font_size": 16,
        "align": "center",
    }
    data.update(overrides)
    return data


def test_admin_saves_placements_and_they_are_stored_on_the_template(app, setup, login_as):
    """An admin saves placements_data (JSON list) and the placements are stored on the template"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = save_placements(
        client,
        org,
        template,
        [
            placement(),
            placement(page=1, variable="approvals.admin.decision", kind="check", match_value="approved"),
        ],
    )

    assert res.status_code == 302
    template.reload()
    assert [
        (p.page, p.x, p.y, p.w, p.h, p.variable, p.kind, p.match_value, p.font_size, p.align)
        for p in template.placements
    ] == [
        (0, 0.1, 0.2, 0.3, 0.05, "app.location", "text", "", 16, "center"),
        (1, 0.1, 0.2, 0.3, 0.05, "approvals.admin.decision", "check", "approved", 16, "center"),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        placement(variable="app.no_such_variable"),
        placement(x=0.9, w=0.3),
        placement(page=5),
        placement(kind="sticker"),
        placement(x="abc"),
        "not json",
    ],
    ids=["unknown_variable", "out_of_bounds", "page_out_of_range", "bad_kind", "non_numeric", "not_json"],
)
def test_invalid_placement_is_rejected_and_nothing_changes(app, setup, login_as, bad):
    """An invalid placement (unknown variable, out of bounds, ...) is rejected with an error and the stored placements do not change"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    template.placements = [models.car_form_templates.PaperPlacement(**placement(variable="org.name"))]
    template.save()
    client = login_as(app.test_client(), setup["admin"])

    res = save_placements(client, org, template, bad if isinstance(bad, str) else [placement(), bad])

    assert res.status_code == 400
    assert 'id="paperError"' in res.get_data(as_text=True)
    template.reload()
    assert [p.variable for p in template.placements] == ["org.name"]


def test_non_admin_cannot_upload_pdf_or_save_placements(app, setup, login_as):
    """A non-admin member cannot upload a PDF or save placements"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    old_paper = template.paper_file
    client = login_as(app.test_client(), setup["staff"])

    upload_res = upload_pdf(client, org, template, make_pdf(pages=4))
    placements_res = save_placements(client, org, template, [placement()])

    for res in (upload_res, placements_res):
        assert res.status_code == 302
        assert "/login" in res.headers["Location"]
    template.reload()
    assert template.paper_file.id == old_paper.id
    assert template.placements == []
    assert models.car_form_templates.CarFormPaperFile.objects(organization=org).count() == 1


def test_paper_editor_page_lists_template_variables_and_points_to_the_pdf(app, setup, login_as):
    """The editor page renders for an admin with the template's variables and the URL of its PDF"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = client.get(
        f"{BASE}/{template.id}/paper_editor", query_string={"organization_id": str(org.id)}
    )

    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "app.location" in body
    assert "approvals.admin.decision" in body
    assert f"{BASE}/{template.id}/paper_file?organization_id={org.id}" in body


def _steps_with_first_key(key):
    return json.dumps(
        [
            {"key": key, "label": "ผู้บังคับบัญชา", "approver_type": "role", "role": "head", "same_division": True},
            {"key": "admin", "label": "ผู้จัดรถ", "approver_type": "role", "role": "admin", "assigns_vehicle": True},
        ]
    )


def test_keys_pasted_with_invisible_characters_are_cleaned_and_saved(app, setup, login_as):
    org = setup["org"]
    client = app.test_client()
    login_as(client, setup["admin"])

    res = client.post(
        "/vehicle_lending/car_form_templates/create",
        data=valid_payload(org, steps_data=_steps_with_first_key("​head﻿ ")),
    )

    assert res.status_code == 302
    template = models.car_form_templates.CarFormTemplate.objects(organization=org).first()
    assert [s.key for s in template.steps] == ["head", "admin"]


def test_malformed_step_key_asks_to_re_add_the_step_by_position_in_thai(app, setup, login_as):
    org = setup["org"]
    client = app.test_client()
    login_as(client, setup["admin"])

    res = client.post(
        "/vehicle_lending/car_form_templates/create",
        data=valid_payload(org, steps_data=_steps_with_first_key("ผู้บังคับบัญชา")),
    )

    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert count_templates(org) == 0
    assert "ขั้นที่ 1: ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่" in body
    assert "ValidationError" not in body


RAW_MONGO_PHRASES = ("ValidationError", "Field is required", "did not match validation regex", "Value must be one of")


def test_every_problem_is_listed_in_readable_thai_at_once(app, setup, login_as):
    org = setup["org"]
    client = app.test_client()
    login_as(client, setup["admin"])

    res = client.post(
        "/vehicle_lending/car_form_templates/create",
        data=valid_payload(
            org,
            fields_data=json.dumps(
                [
                    {"source": "catalog", "key": "vehicle_kind", "choices": ["รถตู้", "บัส"]},
                    {"source": "custom", "key": "note", "label": "", "field_type": ""},
                ]
            ),
            steps_data=json.dumps(
                [
                    {"key": "ผู้บังคับบัญชา", "label": "", "approver_type": "role", "role": ""},
                    {"key": "admin", "label": "ผู้จัดรถ", "approver_type": "role", "role": "admin", "assigns_vehicle": True},
                    {"key": "admin", "label": "ซ้ำ", "approver_type": "role", "role": "director", "assigns_vehicle": True},
                ]
            ),
        ),
    )

    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert count_templates(org) == 0
    for expected in (
        "ฟิลด์ที่ 1 (ชนิดรถ): ตัวเลือก “รถตู้” ไม่มีใน catalog (ใช้ได้: บัส, ตู้, เก๋ง, มินิบัส)",
        "ฟิลด์ที่ 2: ต้องเลือกชนิดข้อมูล",
        "ฟิลด์ที่ 2: ต้องกรอกชื่อฟิลด์",
        "ขั้นที่ 1: ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่",
        "ขั้นที่ 1: ต้องกรอกชื่อขั้น",
        "ขั้นที่ 1: ต้องเลือก role",
        "ขั้นที่ 3: ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่",
        "ต้องมีขั้นจัดรถพอดี 1 ขั้น (ตอนนี้มี 2 ขั้น)",
    ):
        assert expected in body, expected
    for raw in RAW_MONGO_PHRASES:
        assert raw not in body, raw


def test_user_step_without_a_user_is_rejected_in_thai(app, setup, login_as):
    org = setup["org"]
    client = app.test_client()
    login_as(client, setup["admin"])

    res = client.post(
        "/vehicle_lending/car_form_templates/create",
        data=valid_payload(
            org,
            steps_data=json.dumps(
                [
                    {"key": "approver", "label": "ผู้อนุมัติ", "approver_type": "user", "user": ""},
                    {"key": "admin", "label": "ผู้จัดรถ", "approver_type": "role", "role": "admin", "assigns_vehicle": True},
                ]
            ),
        ),
    )

    body = res.get_data(as_text=True)
    assert count_templates(org) == 0
    assert "ขั้นที่ 1: ต้องเลือกผู้อนุมัติ" in body


def test_paper_editor_sends_sample_text_and_the_thai_font_for_true_size_preview(app, setup, login_as):
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])

    res = client.get(f"{BASE}/{template.id}/paper_editor", query_string={"organization_id": str(org.id)})

    body = res.get_data(as_text=True)
    assert res.status_code == 200
    import re

    variables = json.loads(re.search(r'id="variablesData">(.*?)</script>', body, re.S).group(1))
    samples = {v["name"]: v["sample"] for v in variables}
    assert samples["app.requester_name"] == "สมชาย ใจดี"
    assert "THSarabunNew.ttf" in body


def test_saving_without_placements_data_keeps_the_existing_placements(app, setup, login_as):
    """A save that carries no placements_data at all (e.g. the page script did not fill it) must not wipe the boxes"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])
    save_placements(client, org, template, [placement()])

    res = save_placements(client, org, template, "")

    template.reload()
    assert res.status_code == 400
    assert len(template.placements) == 1
    assert "ไม่พบข้อมูลตำแหน่ง" in res.get_data(as_text=True)


def test_saving_an_empty_list_clears_the_placements(app, setup, login_as):
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    client = login_as(app.test_client(), setup["admin"])
    save_placements(client, org, template, [placement()])

    res = save_placements(client, org, template, [])

    template.reload()
    assert res.status_code == 302
    assert template.placements == []


def test_renaming_and_reordering_keeps_keys_and_placements_pointing_at_the_same_field_and_step(
    app, setup, login_as
):
    """Editing a template that has a PDF and placements: renaming a custom field and a step and swapping the two steps, with the existing keys in the payload, keeps every key and every placement, and the placements resolve to the new labels by key"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    template.fields = [
        models.car_form_templates.FormFieldDef(
            source="custom", key="f_abc123", label="ชื่อโครงการ", field_type="text"
        )
    ]
    template.steps = [
        models.car_form_templates.ApprovalStepDef(
            key="s_aaa111", label="ผู้บังคับบัญชา", role="head", same_division=True
        ),
        models.car_form_templates.ApprovalStepDef(
            key="s_bbb222", label="ผู้จัดรถ", role="admin", assigns_vehicle=True
        ),
    ]
    template.save()
    client = login_as(app.test_client(), setup["admin"])
    placed = [
        placement(variable="details.custom_f_abc123"),
        placement(variable="approvals.s_aaa111.decision", kind="check", match_value="approved"),
        placement(variable="approvals.s_bbb222.name"),
    ]
    assert save_placements(client, org, template, placed).status_code == 302

    res = client.post(
        f"{BASE}/{template.id}/edit",
        data=valid_payload(
            org,
            fields_data=json.dumps(
                [{"source": "custom", "key": "f_abc123", "label": "ชื่อกิจกรรม", "field_type": "text"}]
            ),
            steps_data=json.dumps(
                [
                    {"key": "s_bbb222", "label": "เจ้าหน้าที่จัดรถ", "approver_type": "role", "role": "admin", "assigns_vehicle": True},
                    {"key": "s_aaa111", "label": "หัวหน้างาน", "approver_type": "role", "role": "head", "same_division": True},
                ]
            ),
        ),
    )

    assert res.status_code == 302
    template.reload()
    assert [f.key for f in template.fields] == ["f_abc123"]
    assert [(s.key, s.label) for s in template.steps] == [
        ("s_bbb222", "เจ้าหน้าที่จัดรถ"),
        ("s_aaa111", "หัวหน้างาน"),
    ]
    assert [p.variable for p in template.placements] == [
        "details.custom_f_abc123",
        "approvals.s_aaa111.decision",
        "approvals.s_bbb222.name",
    ]
    template.validate()
    page = client.get(
        f"{BASE}/{template.id}/paper_editor", query_string={"organization_id": str(org.id)}
    )
    variables = json.loads(
        re.search(r'id="variablesData">(.*?)</script>', page.get_data(as_text=True), re.S).group(1)
    )
    labels = {v["name"]: v["label"] for v in variables}
    assert labels["details.custom_f_abc123"] == "ชื่อกิจกรรม"
    assert labels["approvals.s_aaa111.decision"].startswith("หัวหน้างาน")
    assert labels["approvals.s_bbb222.name"].startswith("เจ้าหน้าที่จัดรถ")


def paper_editor_variables(client, org, template):
    page = client.get(
        f"{BASE}/{template.id}/paper_editor", query_string={"organization_id": str(org.id)}
    )
    return json.loads(
        re.search(r'id="variablesData">(.*?)</script>', page.get_data(as_text=True), re.S).group(1)
    )


def test_paper_editor_sends_choices_as_value_label_pairs(app, setup, login_as):
    """Decision choices carry a Thai label while the stored value stays approved/denied; field choices use the value as its own label"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    template.fields = [
        models.car_form_templates.FormFieldDef(
            source="catalog", key="vehicle_kind", choices=["ตู้", "บัส"]
        )
    ]
    template.save()
    client = login_as(app.test_client(), setup["admin"])

    variables = paper_editor_variables(client, org, template)

    choices = {v["name"]: v["choices"] for v in variables}
    assert choices["approvals.admin.decision"] == [
        ["approved", "อนุมัติ"],
        ["denied", "ไม่อนุมัติ"],
    ]
    assert choices["details.vehicle_kind"] == [["ตู้", "ตู้"], ["บัส", "บัส"]]
    assert choices["app.location"] == []


def test_paper_editor_appends_the_group_to_labels_that_collide(app, setup, login_as):
    """Variables sharing a label get their group appended; labels that are unique stay as they are"""
    org = setup["org"]
    template, _ = template_with_paper(org, setup["admin"])
    form_field = models.car_form_templates.FormFieldDef
    template.fields = [
        form_field(source="catalog", key="vehicle_kind"),
        form_field(source="custom", key="f_kind", label="ชนิดรถ", field_type="text"),
        form_field(source="custom", key="f_phone", label="เบอร์โทรศัพท์", field_type="text"),
        form_field(source="custom", key="f_sign", label="ผู้จัดรถ : ชื่อผู้อนุมัติ", field_type="text"),
    ]
    template.save(validate=False)
    client = login_as(app.test_client(), setup["admin"])

    variables = paper_editor_variables(client, org, template)

    labels = {v["name"]: v["label"] for v in variables}
    assert labels["details.vehicle_kind"] == "ชนิดรถ (ฟิลด์มาตรฐาน)"
    assert labels["details.custom_f_kind"] == "ชนิดรถ (ฟิลด์เพิ่มเติม)"
    assert labels["details.custom_f_phone"] == "เบอร์โทรศัพท์ (ฟิลด์เพิ่มเติม)"
    assert labels["app.phone"] == "เบอร์โทรศัพท์ (ข้อมูลคำขอ)"
    assert labels["details.custom_f_sign"] == "ผู้จัดรถ : ชื่อผู้อนุมัติ (ฟิลด์เพิ่มเติม)"
    assert labels["approvals.admin.name"] == "ผู้จัดรถ : ชื่อผู้อนุมัติ (ขั้นอนุมัติ)"
    assert labels["app.requester_name"] == "ชื่อผู้ขอ"
    assert labels["approvals.admin.date"] == "ผู้จัดรถ : วันที่อนุมัติ"


def _builder_json(body, element_id):
    match = re.search(rf'<script type="application/json" id="{element_id}">(.*?)</script>', body, re.S)
    return json.loads(match.group(1))


def test_role_step_for_driver_is_rejected_in_thai(app, setup, login_as):
    """คนขับไม่มีขั้นอนุมัติในแบบฟอร์ม: ขั้นที่ role เป็น driver ต้องไม่ถูกบันทึก"""
    org = setup["org"]
    client = login_as(app.test_client(), setup["admin"])

    res = client.post(
        f"{BASE}/create",
        data=valid_payload(
            org,
            steps_data=json.dumps(
                [
                    {"key": "drive", "label": "คนขับรับทราบ", "approver_type": "role", "role": "driver"},
                    {"key": "admin", "label": "ผู้จัดรถ", "approver_type": "role", "role": "admin", "assigns_vehicle": True},
                ]
            ),
        ),
    )

    assert count_templates(org) == 0
    assert "ขั้นที่ 1: พนักงานขับรถเป็นผู้อนุมัติไม่ได้" in res.get_data(as_text=True)


def test_builder_offers_neither_the_driver_role_nor_driver_only_members(
    app, setup, create_user, assign_user_to_org, login_as
):
    org = setup["org"]
    driver = create_user("Driver", "Only")
    driving_head = create_user("Driving", "Head")
    assign_user_to_org(driver, org, roles=["driver", "staff"])
    assign_user_to_org(driving_head, org, roles=["driver", "head"])
    client = login_as(app.test_client(), setup["admin"])

    body = client.get(f"{BASE}/create?organization_id={org.id}").get_data(as_text=True)

    assert "driver" not in [value for value, _ in _builder_json(body, "rolesData")]
    member_ids = [m["id"] for m in _builder_json(body, "membersData")]
    assert str(driver.id) not in member_ids
    assert str(driving_head.id) in member_ids


def test_user_step_naming_a_driver_only_member_is_rejected(
    app, setup, create_user, assign_user_to_org, login_as
):
    org = setup["org"]
    driver = create_user("Driver", "Only")
    assign_user_to_org(driver, org, roles=["driver"])
    client = login_as(app.test_client(), setup["admin"])

    res = client.post(f"{BASE}/create", data=user_step_payload(org, str(driver.id)))

    assert count_templates(org) == 0
    assert "ขั้นที่ 1: พนักงานขับรถเป็นผู้อนุมัติไม่ได้" in res.get_data(as_text=True)
