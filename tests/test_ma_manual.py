"""คู่มือ MA ฉบับใหม่ที่ /procurement/manuals

ตั้งต้นแสดงคู่มือ MA ใหม่ คู่มือเก่า (MAS / ขอซื้อขอจ้าง) ซ่อนไว้หลัง PROCUREMENT_LEGACY_MANUAL_ENABLED
เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import pytest

LEGACY_FLAG = "PROCUREMENT_LEGACY_MANUAL_ENABLED"
NEW_MARK = "data-ma-manual"
SECTION_IDS = ("overview", "list", "create", "payment", "reminders", "renewal", "tips")


@pytest.fixture
def legacy_flag(app, monkeypatch):
    def _set(value):
        if value is None:
            monkeypatch.delitem(app.config, LEGACY_FLAG, raising=False)
        else:
            monkeypatch.setitem(app.config, LEGACY_FLAG, value)

    return _set


@pytest.fixture
def get_manual(app, create_org, create_user, assign_user_to_org, login_as):
    def _get(role="admin"):
        org = create_org("[TEST] Manual Org")
        user = create_user(role.capitalize(), "Manual")
        assign_user_to_org(user, org, roles=[role])
        client = app.test_client()
        login_as(client, user)
        return client.get(f"/procurement/manuals?organization_id={org.id}")

    return _get


@pytest.mark.parametrize("value", (None, False, "False"))
@pytest.mark.parametrize("role", ("admin", "staff", "head", "manager"))
def test_new_manual_is_default_for_every_role(legacy_flag, get_manual, value, role):
    legacy_flag(value)

    response = get_manual(role)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert NEW_MARK in html
    for section_id in SECTION_IDS:
        assert f'id="{section_id}"' in html


def test_new_manual_names_the_organization_and_only_covers_ma(legacy_flag, get_manual):
    legacy_flag(None)

    html = get_manual("admin").get_data(as_text=True)

    assert "[TEST] Manual Org" in html
    assert "ระบบจัดการสัญญา (MA)" in html
    # ไม่พูดถึงระบบที่ปิดอยู่
    assert "MAS" not in html
    assert "/procurement/requisitions" not in html
    assert "/admin/mas" not in html


def test_new_manual_does_not_link_the_closed_upload_page(app, monkeypatch, legacy_flag, get_manual):
    legacy_flag(None)
    monkeypatch.delitem(app.config, "PROCUREMENT_UPLOAD_FILES_ENABLED", raising=False)

    html = get_manual("admin").get_data(as_text=True)

    assert "/admin/upload_files" not in html


def test_new_manual_states_renewal_rules_matching_permissions(legacy_flag, get_manual):
    legacy_flag(None)

    html = get_manual("staff").get_data(as_text=True)

    # ขอต่ออายุได้เฉพาะผู้รับผิดชอบ (รวม admin ที่เป็นผู้รับผิดชอบ) และ admin เป็นผู้อนุมัติ
    assert "ผู้รับผิดชอบ" in html
    assert "อนุมัติต่ออายุ" in html
    assert "แม้เป็น admin ก็ต้องเป็นผู้รับผิดชอบก่อน" in html


@pytest.mark.parametrize("value", (True, "true"))
def test_legacy_manual_returns_when_flag_on(legacy_flag, get_manual, value):
    legacy_flag(value)

    html = get_manual("admin").get_data(as_text=True)

    assert NEW_MARK not in html
    assert 'id="upload-files"' in html


def test_new_manual_requires_login(app, create_org, legacy_flag):
    legacy_flag(None)
    org = create_org("[TEST] Manual Org")

    response = app.test_client().get(f"/procurement/manuals?organization_id={org.id}")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
