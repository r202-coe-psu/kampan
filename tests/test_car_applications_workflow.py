import datetime
from unittest.mock import MagicMock, patch
import pytest

from kampan import models
from kampan.web import redis_rq


@pytest.fixture(autouse=True)
def mock_redis_queue():
    """Mock redis queue to prevent actual Redis connections in tests."""
    mock_q = MagicMock()
    with patch.object(redis_rq.redis_queue, "queue", mock_q, create=True):
        yield mock_q


@pytest.fixture
def workflow_setup(create_org, create_user, assign_user_to_org, create_car):
    """Setup an organization with division, staff, head, admin, director, driver, and car."""
    org = create_org(name="Faculty of Science")

    division = models.Division(name="ภาควิชาคอมพิวเตอร์", organization=org)
    division.save()

    # Users
    staff = create_user("Staff", "User")
    head = create_user("Head", "User")
    admin = create_user("Admin", "User")
    director = create_user("Director", "User")
    driver_user = create_user("Driver", "User")

    # Roles
    staff_role = assign_user_to_org(staff, org, roles=["staff"])
    staff_role.division = division
    staff_role.save()

    head_role = assign_user_to_org(head, org, roles=["head"])
    head_role.division = division
    head_role.save()

    assign_user_to_org(admin, org, roles=["admin"])
    assign_user_to_org(director, org, roles=["director"])
    assign_user_to_org(driver_user, org, roles=["driver"])

    car = create_car(org, license_plate="กข-9999")

    return {
        "org": org,
        "division": division,
        "staff": staff,
        "head": head,
        "admin": admin,
        "director": director,
        "driver": driver_user,
        "car": car,
    }


def test_create_general_car_application_starts_at_pending_on_header(app, workflow_setup, login_as):
    """คำขอใช้รถทั่วไปต้องเริ่มต้นที่ pending on header"""
    client = app.test_client()
    login_as(client, workflow_setup["staff"])

    with client.session_transaction() as sess:
        sess["organization_id"] = str(workflow_setup["org"].id)

    res = client.post(
        f"/vehicle_lending/car_applications/create?organization_id={workflow_setup['org'].id}",
        data={
            "phone": "0812345678",
            "using_type": "general",
            "travel_type": "one way",
            "location": "มหาวิทยาลัยสงขลานครินทร์",
            "request_reason": "ไปประชุมวิชาการ",
            "passenger_number": "2",
            "passenger_location": "หน้าตึก",
            "departure_date": "2026-03-10",
            "departure_time": "08:30",
            "return_date": "2026-03-10",
            "return_time": "16:30",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    app_doc = models.vehicle_applications.CarApplication.objects(
        organization=workflow_setup["org"]
    ).first()
    assert app_doc is not None
    assert app_doc.using_type == "general"
    assert app_doc.status == "pending on header"


def test_create_out_of_town_car_application_starts_at_pending_on_header(app, workflow_setup, login_as):
    """คำขอไปต่างจังหวัด ต้องเริ่มต้นที่ pending on header (ไม่ข้ามไป ผอ. ทันที)"""
    client = app.test_client()
    login_as(client, workflow_setup["staff"])

    with client.session_transaction() as sess:
        sess["organization_id"] = str(workflow_setup["org"].id)

    res = client.post(
        f"/vehicle_lending/car_applications/create?organization_id={workflow_setup['org'].id}",
        data={
            "phone": "0812345678",
            "using_type": "out of town",
            "travel_type": "round trip",
            "location": "จ.กระบี่",
            "request_reason": "เข้าร่วมสัมมนาต่างจังหวัด",
            "passenger_number": "4",
            "passenger_location": "หน้าตึกวิจัย",
            "departure_date": "2026-03-15",
            "departure_time": "07:00",
            "return_date": "2026-03-16",
            "return_time": "18:00",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    app_doc = models.vehicle_applications.CarApplication.objects(
        organization=workflow_setup["org"],
        using_type="out of town",
    ).first()
    assert app_doc is not None
    assert app_doc.status == "pending on header"


def test_header_approve_sets_status_to_pending_on_admin(app, workflow_setup, login_as):
    """หัวหน้าฝ่ายอนุมัติ -> สถานะเปลี่ยนเป็น pending on admin"""
    car_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        using_type="out of town",
        location="จ.ตรัง",
        request_reason="ไปนิเทศนักศึกษา",
        status="pending on header",
    )
    car_app.save()

    client = app.test_client()
    login_as(client, workflow_setup["head"])

    res = client.post(
        "/vehicle_lending/car_permissions/header_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    car_app.reload()
    assert car_app.status == "pending on admin"
    assert car_app.header_approval is not None
    assert car_app.header_approval.approved_by == workflow_setup["head"]


def test_admin_approve_general_sets_status_to_active(app, workflow_setup, login_as):
    """กรณีทั่วไป: พัสดุอนุมัติพร้อมเลือกรถและคนขับ -> สถานะกลายเป็น active ทันที"""
    car_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        using_type="general",
        location="หาดใหญ่",
        request_reason="ไปส่งเอกสาร",
        status="pending on admin",
    )
    car_app.save()

    client = app.test_client()
    login_as(client, workflow_setup["admin"])

    res = client.post(
        "/vehicle_lending/car_permissions/admin_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
            "car": str(workflow_setup["car"].id),
            "driver": str(workflow_setup["driver"].id),
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    car_app.reload()
    assert car_app.status == "active"
    assert car_app.car == workflow_setup["car"]
    assert car_app.driver == workflow_setup["driver"]
    assert car_app.admin_approval is not None
    assert car_app.admin_approval.approved_by == workflow_setup["admin"]


def test_admin_approve_out_of_town_forwards_to_director(app, workflow_setup, login_as):
    """กรณีไปต่างจังหวัด: พัสดุอนุมัติพร้อมเลือกรถและคนขับ -> สถานะเปลี่ยนเป็น pending on director เพื่อรอ ผอ. อนุมัติ"""
    car_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        using_type="out of town",
        location="จ.ภูเก็ต",
        request_reason="ประชุมสัญจร",
        status="pending on admin",
    )
    car_app.save()

    client = app.test_client()
    login_as(client, workflow_setup["admin"])

    res = client.post(
        "/vehicle_lending/car_permissions/admin_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
            "car": str(workflow_setup["car"].id),
            "driver": str(workflow_setup["driver"].id),
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    car_app.reload()
    assert car_app.status == "pending on director"
    assert car_app.car == workflow_setup["car"]
    assert car_app.driver == workflow_setup["driver"]
    assert car_app.admin_approval is not None
    assert car_app.admin_approval.approved_by == workflow_setup["admin"]


def test_director_approve_out_of_town_sets_status_to_active(app, workflow_setup, login_as):
    """กรณีไปต่างจังหวัด: ผอ. อนุมัติ -> สถานะเปลี่ยนเป็น active สำเร็จ"""
    car_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        car=workflow_setup["car"],
        driver=workflow_setup["driver"],
        using_type="out of town",
        location="จ.ภูเก็ต",
        request_reason="ประชุมสัญจร",
        status="pending on director",
    )
    car_app.save()

    client = app.test_client()
    login_as(client, workflow_setup["director"])

    res = client.post(
        "/vehicle_lending/car_permissions/director_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    car_app.reload()
    assert car_app.status == "active"
    assert car_app.director_approval is not None
    assert car_app.director_approval.approved_by == workflow_setup["director"]


def test_director_denied_out_of_town_sets_status_to_denied(app, workflow_setup, login_as):
    """กรณีไปต่างจังหวัด: ผอ. ไม่อนุมัติ -> สถานะเปลี่ยนเป็น denied by director พร้อมเหตุผล"""
    car_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        car=workflow_setup["car"],
        driver=workflow_setup["driver"],
        using_type="out of town",
        location="จ.พัทลุง",
        request_reason="ไปราชการ",
        status="pending on director",
    )
    car_app.save()

    client = app.test_client()
    login_as(client, workflow_setup["director"])

    res = client.post(
        "/vehicle_lending/car_permissions/director_denied",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
            "denied_reason": "ไม่อนุญาตเนื่องจากมีภารกิจด่วนภายใน",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    car_app.reload()
    assert car_app.status == "denied by director"
    assert car_app.denied_reason == "ไม่อนุญาตเนื่องจากมีภารกิจด่วนภายใน"
    assert car_app.director_approval is not None
    assert car_app.director_approval.approved_by == workflow_setup["director"]


def test_full_out_of_town_workflow_end_to_end(app, workflow_setup, login_as):
    """ทดสอบ Full Flow ไปต่างจังหวัด:
    ผู้ขอยื่น -> หัวหน้าฝ่ายอนุมัติ -> พัสดุจัดสรรรถ/คนขับ -> ผอ. อนุมัติ -> active
    """
    client = app.test_client()

    # Step 1: Creator creates application
    login_as(client, workflow_setup["staff"])
    with client.session_transaction() as sess:
        sess["organization_id"] = str(workflow_setup["org"].id)

    client.post(
        f"/vehicle_lending/car_applications/create?organization_id={workflow_setup['org'].id}",
        data={
            "phone": "0899999999",
            "using_type": "out of town",
            "travel_type": "round trip",
            "location": "จ.สตูล",
            "request_reason": "จัดกิจกรรมค่ายเยาวชน",
            "passenger_number": "5",
            "passenger_location": "หน้าอาคารเรียน",
            "departure_date": "2026-04-01",
            "departure_time": "08:00",
            "return_date": "2026-04-03",
            "return_time": "17:00",
        },
        follow_redirects=True,
    )

    car_app = models.vehicle_applications.CarApplication.objects(
        organization=workflow_setup["org"],
        using_type="out of town",
        location="จ.สตูล",
    ).first()
    assert car_app is not None
    assert car_app.status == "pending on header"

    # Step 2: Head of Division approves
    login_as(client, workflow_setup["head"])
    client.post(
        "/vehicle_lending/car_permissions/header_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
        },
        follow_redirects=True,
    )
    car_app.reload()
    assert car_app.status == "pending on admin"

    # Step 3: Admin allocates car & driver and approves
    login_as(client, workflow_setup["admin"])
    client.post(
        "/vehicle_lending/car_permissions/admin_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
            "car": str(workflow_setup["car"].id),
            "driver": str(workflow_setup["driver"].id),
        },
        follow_redirects=True,
    )
    car_app.reload()
    assert car_app.status == "pending on director"
    assert car_app.car == workflow_setup["car"]
    assert car_app.driver == workflow_setup["driver"]

    # Step 4: Director reviews and approves
    login_as(client, workflow_setup["director"])
    client.post(
        "/vehicle_lending/car_permissions/director_approve",
        data={
            "organization_id": str(workflow_setup["org"].id),
            "car_application_id": str(car_app.id),
        },
        follow_redirects=True,
    )
    car_app.reload()
    assert car_app.status == "active"
    assert car_app.header_approval is not None
    assert car_app.admin_approval is not None
    assert car_app.director_approval is not None


def test_migration_script_updates_legacy_out_of_town_records(workflow_setup):
    """ทดสอบว่าสคริปต์ migrate แปลงคำขอเดิมที่ค้างอยู่ pending on director กลับมาเป็น pending on header"""
    from scripts.migrate_car_applications_out_of_town import migrate_car_applications

    # 1. Legacy out-of-town record (created in old system, no header/admin approval)
    legacy_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        using_type="out of town",
        location="จ.พังงา",
        request_reason="อบรมวิชาการ",
        status="pending on director",
    )
    legacy_app.save()

    # 2. Modern record that already has admin approval (waiting for director)
    modern_app = models.vehicle_applications.CarApplication(
        organization=workflow_setup["org"],
        division=workflow_setup["division"],
        creator=workflow_setup["staff"],
        using_type="out of town",
        location="จ.ยะลา",
        request_reason="ศึกษาดูงาน",
        status="pending on director",
        admin_approval=models.vehicle_applications.CarApplicationApproval(
            approved_by=workflow_setup["admin"],
            approved_at=datetime.datetime.now(),
        ),
    )
    modern_app.save()

    # Test Dry Run
    migrated, skipped = migrate_car_applications(dry_run=True)
    assert migrated == 1
    assert skipped == 1
    legacy_app.reload()
    assert legacy_app.status == "pending on director"  # unchanged in dry-run

    # Test Actual Run
    migrated, skipped = migrate_car_applications(dry_run=False)
    assert migrated == 1
    assert skipped == 1

    legacy_app.reload()
    assert legacy_app.status == "pending on header"  # updated!

    modern_app.reload()
    assert modern_app.status == "pending on director"  # kept as is!

