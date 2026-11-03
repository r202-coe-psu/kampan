import json

import pytest

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
