"""ผู้ดูแลองค์กร snor ตั้งผู้ดำรงตำแหน่งอนุมัติ (position -> user + ผู้รักษาการ) ได้ที่หน้าตั้งค่า
ผู้ดำรงตำแหน่งเป็นการตั้งค่าต่อองค์กร ไม่ใช่ role"""

import pytest

from kampan import models

POSITIONS_PATH = "/snor_car/settings/positions"

POSITION_LABELS = [
    "ผู้จัดรถ",
    "หัวหน้าหน่วยยานพาหนะ",
    "หัวหน้างานยุทธศาสตร์และบริการกลาง",
    "ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
    "รองอธิการบดีวิทยาเขตหาดใหญ่",
    "อธิการบดี",
]


@pytest.fixture
def snor_setup(app, create_org, create_user, assign_user_to_org, login_as):
    """องค์กร snor + ผู้ดูแลที่ล็อกอินแล้ว"""
    org = create_org("Snor Org")
    org.enabled_modules = ["snor_car"]
    org.save()
    admin = create_user("Admin", "Snor")
    assign_user_to_org(admin, org, roles=["admin"])
    client = login_as(app.test_client(), admin)

    class Setup:
        pass

    setup = Setup()
    setup.org, setup.admin, setup.client = org, admin, client
    setup.url = f"{POSITIONS_PATH}?organization_id={org.id}"
    return setup


def test_org_admin_saves_position_holders_and_delegates(
    snor_setup, create_user, assign_user_to_org
):
    org = snor_setup.org
    dispatcher = create_user("Dispatch", "Er")
    president = create_user("Presi", "Dent")
    deputy = create_user("Deputy", "One")
    for member in (dispatcher, president, deputy):
        assign_user_to_org(member, org, roles=["staff"])

    response = snor_setup.client.post(
        snor_setup.url,
        data={
            "dispatcher_user": str(dispatcher.id),
            "president_user": str(president.id),
            "president_delegates": [str(deputy.id)],
        },
    )

    assert response.status_code == 302
    assert models.CarFlowPosition.holder(org, "dispatcher") == dispatcher
    assert models.CarFlowPosition.can_act(org, "president", president)
    assert models.CarFlowPosition.can_act(org, "president", deputy)
    assert not models.CarFlowPosition.can_act(org, "dispatcher", deputy)


def test_driver_cannot_be_holder_or_delegate(snor_setup, create_user, assign_user_to_org):
    org = snor_setup.org
    driver = create_user("Driver", "Dan")
    assign_user_to_org(driver, org, roles=["driver"])
    colleague = create_user("Col", "League")
    assign_user_to_org(colleague, org, roles=["staff"])

    as_holder = snor_setup.client.post(
        snor_setup.url, data={"dispatcher_user": str(driver.id)}
    )
    as_delegate = snor_setup.client.post(
        snor_setup.url,
        data={"president_user": str(colleague.id), "president_delegates": [str(driver.id)]},
    )

    assert as_holder.status_code == 200
    assert as_delegate.status_code == 200
    assert "พนักงานขับรถเป็นผู้อนุมัติไม่ได้" in as_holder.get_data(as_text=True)
    assert "พนักงานขับรถเป็นผู้อนุมัติไม่ได้" in as_delegate.get_data(as_text=True)
    assert models.CarFlowPosition.holder(org, "dispatcher") is None
    assert models.CarFlowPosition.holder(org, "president") is None


@pytest.mark.parametrize("membership", ["other_org", "removed", "pending"])
def test_user_who_is_not_an_active_member_is_rejected(
    snor_setup, create_org, create_user, assign_user_to_org, membership
):
    org = snor_setup.org
    outsider = create_user("Out", "Sider")
    if membership == "other_org":
        assign_user_to_org(outsider, create_org("Elsewhere Org"), roles=["staff"])
    else:
        status = "disactive" if membership == "removed" else "pending"
        assign_user_to_org(outsider, org, roles=["staff"], status=status)

    response = snor_setup.client.post(
        snor_setup.url,
        data={"dispatcher_user": str(outsider.id), "dispatcher_delegates": [str(outsider.id)]},
    )

    assert response.status_code == 200
    assert models.CarFlowPosition.holder(org, "dispatcher") is None
    assert not models.CarFlowPosition.can_act(org, "dispatcher", outsider)


def test_non_admin_staff_cannot_open_positions_page(
    app, snor_setup, create_user, assign_user_to_org, login_as
):
    staff = create_user("Plain", "Staff")
    assign_user_to_org(staff, snor_setup.org, roles=["staff"])
    client = login_as(app.test_client(), staff)

    response = client.get(snor_setup.url)

    assert response.status_code in (302, 403)


def test_positions_page_lists_the_six_positions(snor_setup):
    response = snor_setup.client.get(snor_setup.url)

    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for label in POSITION_LABELS:
        assert label in html


def test_positions_page_shows_saved_holder(snor_setup, create_user, assign_user_to_org):
    holder = create_user("Holder", "Hank")
    assign_user_to_org(holder, snor_setup.org, roles=["staff"])
    snor_setup.client.post(snor_setup.url, data={"strategy_head_user": str(holder.id)})

    response = snor_setup.client.get(snor_setup.url)

    assert f'<option selected value="{holder.id}">Holder Hank</option>' in response.get_data(as_text=True)


def test_organization_without_the_snor_car_module_gets_404_on_positions_page(
    snor_setup,
):
    snor_setup.org.enabled_modules = ["car"]
    snor_setup.org.save()

    response = snor_setup.client.get(snor_setup.url)

    assert response.status_code == 404


def test_snor_sidebar_links_to_positions_only_for_org_admin(
    app, snor_setup, create_user, assign_user_to_org, login_as
):
    staff = create_user("Plain", "Staff")
    assign_user_to_org(staff, snor_setup.org, roles=["staff"])
    staff_client = login_as(app.test_client(), staff)
    home = f"/snor_car/requests/?organization_id={snor_setup.org.id}"

    admin_html = snor_setup.client.get(home).get_data(as_text=True)
    staff_html = staff_client.get(home).get_data(as_text=True)

    assert "ตั้งค่าผู้อนุมัติ" in admin_html
    assert "ตั้งค่าผู้อนุมัติ" not in staff_html


def test_diis_sidebar_has_no_approver_settings_link(snor_setup):
    snor_setup.org.enabled_modules = ["car", "snor_car"]
    snor_setup.org.save()
    calendar = f"/vehicle_lending/car_applications/calendar?organization_id={snor_setup.org.id}"

    html = snor_setup.client.get(calendar).get_data(as_text=True)

    assert "ตั้งค่าผู้อนุมัติ" not in html

