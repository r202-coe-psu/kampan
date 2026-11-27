"""คำขอใช้รถหลายคัน (assignments): จัดรถ ชนเวลา ลดจำนวนคัน ภาระงาน และการปิดงานแยกชุด (ระดับ flow ไม่ผ่าน view)"""

import datetime
import io
from decimal import Decimal

import pytest
from werkzeug.datastructures import FileStorage

from kampan import models
from kampan.models import car_reservations as cr
from kampan.utils import car_reservation_flow as flow

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
DAY = datetime.datetime.combine(
    datetime.date.today() + datetime.timedelta(days=20), datetime.time(8, 0)
)


@pytest.fixture
def world(app, create_org, create_user, assign_user_to_org, create_car):
    org = create_org("Fleet Org")
    org.enabled_modules = ["car_reservation"]
    org.enabled_roles = [key for key, _ in models.organizations.ORGANIZATION_ROLES]
    org.save()

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.requester = create_user("Requester", "One")
    assign_user_to_org(s.requester, org, roles=["staff"])
    s.dispatcher = create_user("Dispatcher", "Two")
    assign_user_to_org(s.dispatcher, org, roles=["dispatcher"])
    s.head = create_user("VehicleHead", "Three")
    assign_user_to_org(s.head, org, roles=["vehicle_unit_head"])
    s.drivers = []
    for name in ("Alpha", "Bravo", "Charlie"):
        driver = create_user(name, "Driver")
        assign_user_to_org(driver, org, roles=["driver"])
        s.drivers.append(driver)
    s.cars = [
        create_car(org, "กก 1111"),
        create_car(org, "กก 2222"),
        create_car(org, "กก 3333"),
    ]
    s.a, s.b, s.c = s.drivers

    def new_request(vehicle_count=2, route=("dispatcher", "vehicle_unit_head"), **fields):
        """คำขอที่ผู้บังคับบัญชาอนุมัติแล้ว กำลังรอผู้จัดรถ"""
        values = dict(
            organization=org,
            creator=s.requester,
            request_type="domestic",
            province_scope="in_province",
            location="กรุงเทพฯ",
            request_reason="ประชุม",
            departure_datetime=DAY,
            return_datetime=DAY + datetime.timedelta(hours=9),
            status="pending",
            route_snapshot=list(route),
            current_step=0,
            details=cr.DomesticDetails(
                vehicle_kind="ตู้",
                vehicle_count=vehicle_count,
                district="หาดใหญ่",
                province="สงขลา",
            ),
        )
        values.update(fields)
        return models.CarReservation(**values).save()

    s.new_request = new_request

    def active_request(pairs=None, **fields):
        """คำขอ active ที่จัดรถแล้ว pairs = [(car, driver)] (ไม่ระบุ = สองคันแรก)"""
        pairs = pairs or [(s.cars[0], s.a), (s.cars[1], s.b)]
        fields.setdefault("route", ("dispatcher",))
        fields.setdefault("status", "active")
        fields.setdefault("current_step", 1)
        request = new_request(vehicle_count=len(pairs), **fields)
        request.assignments = [
            models.CarAssignment(car=car, driver=driver) for car, driver in pairs
        ]
        return request.save()

    s.active_request = active_request
    return s


def pair(car, driver, **extra):
    return {"car": car, "driver": driver, **extra}


def photo(name="in.png"):
    return FileStorage(io.BytesIO(PNG), filename=name, content_type="image/png")


def close(app, driver, assignment, mileage_out=100, mileage_in=150, **kwargs):
    return flow.close_trip(
        app,
        driver,
        assignment,
        mileage_out,
        mileage_in,
        "fleet_card",
        fuel_liters=Decimal("10.00"),
        cost_baht=Decimal("100.00"),
        client_ip="10.0.0.9",
        photo_in=photo(),
        **kwargs,
    )


def fresh(app):
    return models.CarReservation.objects.get(id=app.id)


def mileage_files():
    return models.CarReservation._get_db()["car_reservation_mileage_photo_in.files"].count_documents({})


# --- จัดรถหลายคัน ---


def test_dispatcher_assigns_two_cars_and_two_drivers_to_a_two_car_request(world):
    app = world.new_request(vehicle_count=2)

    flow.approve(
        app,
        world.dispatcher,
        assignments=[
            pair(world.cars[0], world.a),
            pair(world.cars[1], world.b, is_overtime=True),
        ],
    )

    app = fresh(app)
    assert app.current_step == 1 and app.status == "pending"
    assert app.cars == world.cars[:2]
    assert app.drivers == [world.a, world.b]
    assert [a.is_overtime for a in app.assignments] == [False, True]
    assert len({a.assignment_id for a in app.assignments}) == 2
    log = app.audit_logs[-1]
    assert log.action == "approved"
    assert "กก 1111" in log.comment and "กก 2222" in log.comment
    labels = {change.label: change.new for change in log.changes}
    assert labels["รถ คันที่ 1"] == "กก 1111"
    assert labels["พนักงานขับรถ คันที่ 2"] == world.b.get_name()
    assert labels["งานนอกเวลา (OT) คันที่ 2"] == "ใช่"


def test_a_single_car_request_keeps_the_legacy_keywords_and_plain_labels(world):
    app = world.new_request(vehicle_count=1)

    flow.approve(app, world.dispatcher, car=world.cars[0], driver=world.a, is_overtime=True)

    app = fresh(app)
    assert len(app.assignments) == 1 and app.assignments[0].is_overtime is True
    assert {change.label for change in app.audit_logs[-1].changes} >= {"รถ", "พนักงานขับรถ"}


def test_dispatching_fewer_cars_than_asked_without_a_reason_is_refused(world):
    app = world.new_request(vehicle_count=2)

    with pytest.raises(flow.FlowError) as error:
        flow.approve(app, world.dispatcher, assignments=[pair(world.cars[0], world.a)])

    assert str(error.value) == flow.REDUCE_REASON_REQUIRED
    app = fresh(app)
    assert app.assignments == [] and app.current_step == 0
    assert app.details.vehicle_count == 2


@pytest.mark.parametrize(
    "assignments",
    [
        [],
        [{"car": None, "driver": None}],
        [{"car": "car", "driver": None}, {"car": "car2", "driver": "a"}],
    ],
    ids=["nothing", "empty row", "row without a driver"],
)
def test_an_incomplete_selection_is_refused(world, assignments):
    app = world.new_request(vehicle_count=2)
    lookup = {"car": world.cars[0], "car2": world.cars[1], "a": world.a, None: None}
    assignments = [
        {key: lookup[value] for key, value in row.items()} for row in assignments
    ]

    with pytest.raises(flow.FlowError) as error:
        flow.approve(app, world.dispatcher, assignments=assignments)

    assert str(error.value) == flow.CAR_AND_DRIVER_REQUIRED
    assert fresh(app).assignments == []


def test_the_same_car_twice_in_one_request_is_refused(world):
    app = world.new_request(vehicle_count=2)

    with pytest.raises(flow.FlowError) as error:
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[0], world.b)],
        )

    assert str(error.value) == flow.DUPLICATE_CAR
    assert fresh(app).assignments == []


def test_the_same_driver_twice_in_one_request_is_refused(world):
    app = world.new_request(vehicle_count=2)

    with pytest.raises(flow.FlowError) as error:
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.a)],
        )

    assert str(error.value) == flow.DUPLICATE_DRIVER
    assert fresh(app).assignments == []


def test_more_cars_than_asked_is_refused(world):
    app = world.new_request(vehicle_count=1)

    with pytest.raises(flow.FlowError) as error:
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
            reduce_reason="ไม่เกี่ยว",
        )

    assert str(error.value) == flow.too_many_vehicles_error(1)


def test_every_car_and_driver_must_be_assignable(world, create_user, create_car):
    app = world.new_request(vehicle_count=2)
    stranger = create_user("Stranger", "Nobody")
    inactive = create_car(world.org, "ขข 9999", status="disactive")

    for bad in (
        [pair(world.cars[0], world.a), pair(world.cars[1], stranger)],
        [pair(world.cars[0], world.a), pair(inactive, world.b)],
    ):
        with pytest.raises(flow.FlowError) as error:
            flow.approve(app, world.dispatcher, assignments=bad)
        assert str(error.value) == flow.CAR_OR_DRIVER_NOT_ASSIGNABLE
    assert fresh(app).assignments == []


def test_a_clash_on_the_second_car_refuses_the_whole_dispatch(world):
    world.active_request([(world.cars[1], world.c)], departure_datetime=DAY)
    app = world.new_request(vehicle_count=2)

    with pytest.raises(flow.CarConflictError) as error:
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        )

    assert error.value.car == world.cars[1]
    app = fresh(app)
    assert app.assignments == [] and app.current_step == 0 and app.status == "pending"
    assert app.step_approvals == [] and app.audit_logs == []


def test_a_clash_found_after_saving_undoes_every_assignment_and_the_audit_entries(
    world, monkeypatch
):
    other = world.active_request([(world.cars[2], world.c)])
    app = world.new_request(vehicle_count=2, audit_logs=[flow._new_log("submitted", world.requester)])
    real = flow._car_is_taken
    calls = []

    def racing(app_, car, except_driver=None):
        calls.append(car)
        # สองครั้งแรกคือการตรวจก่อน save (ว่าง) ครั้งหลังคือการตรวจซ้ำหลัง save: คันที่สองถูกจองไปพอดี
        if len(calls) > 2 and car == world.cars[1]:
            return other
        return real(app_, car, except_driver)

    monkeypatch.setattr(flow, "_car_is_taken", racing)

    with pytest.raises(flow.CarConflictError) as error:
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        )

    assert error.value.car == world.cars[1]
    assert error.value.conflict == other
    for loaded in (app, fresh(app)):
        assert loaded.assignments == []
        assert loaded.current_step == 0 and loaded.status == "pending"
        assert loaded.step_approvals == []
        assert [log.action for log in loaded.audit_logs] == ["submitted"]


def test_a_clash_after_saving_a_reduced_dispatch_restores_the_vehicle_count_and_the_reduce_log(
    world, monkeypatch
):
    other = world.active_request([(world.cars[2], world.c)])
    app = world.new_request(vehicle_count=2)
    real = flow._car_is_taken
    calls = []

    def racing(app_, car, except_driver=None):
        calls.append(car)
        return other if len(calls) > 1 else real(app_, car, except_driver)

    monkeypatch.setattr(flow, "_car_is_taken", racing)

    with pytest.raises(flow.CarConflictError):
        flow.approve(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a)],
            reduce_reason="รถไม่พอ",
        )

    loaded = fresh(app)
    assert loaded.details.vehicle_count == 2
    assert loaded.assignments == []
    assert loaded.audit_logs == [] and loaded.step_approvals == []
    assert loaded.current_step == 0


def test_reducing_the_vehicle_count_with_a_reason_is_audited(world):
    app = world.new_request(vehicle_count=3)

    flow.approve(
        app,
        world.dispatcher,
        assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        reduce_reason="  รถบัสอีกคันซ่อมบำรุง  ",
    )

    app = fresh(app)
    assert app.details.vehicle_count == 2
    assert models.car_reservations.required_vehicle_count(app) == 2
    reduced = [log for log in app.audit_logs if log.action == "vehicle_count_reduced"]
    assert len(reduced) == 1
    assert reduced[0].actor == world.dispatcher
    assert reduced[0].step_key == "dispatcher"
    assert reduced[0].comment == "รถบัสอีกคันซ่อมบำรุง"
    ((change,),) = [reduced[0].changes]
    assert (change.label, change.old, change.new) == (flow.REDUCE_FIELD_LABEL, "3", "2")
    assert [log.action for log in app.audit_logs] == ["vehicle_count_reduced", "approved"]


def test_a_full_dispatch_never_logs_a_reduction(world):
    app = world.new_request(vehicle_count=2)

    flow.approve(
        app,
        world.dispatcher,
        assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        reduce_reason="ไม่จำเป็น",
    )

    assert "vehicle_count_reduced" not in [log.action for log in fresh(app).audit_logs]
    assert fresh(app).details.vehicle_count == 2


def test_requests_without_a_vehicle_count_need_exactly_one_car(world):
    airport = world.new_request(request_type="airport", details=None, province_scope=None)

    assert models.car_reservations.required_vehicle_count(airport) == 1
    with pytest.raises(flow.FlowError):
        flow.approve(
            airport,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        )


# --- งานด่วน / งานแทรก ---


def test_an_urgent_request_can_dispatch_two_cars_at_once(world):
    app = models.CarReservation(
        organization=world.org,
        creator=world.dispatcher,
        request_type="domestic",
        province_scope="in_province",
        location="กรุงเทพฯ",
        request_reason="ด่วน",
        departure_datetime=DAY,
        return_datetime=DAY + datetime.timedelta(hours=9),
        details=cr.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=2, district="a", province="b"
        ),
    )

    flow.submit_urgent(
        app,
        world.dispatcher,
        assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b, is_overtime=True)],
    )

    saved = fresh(app)
    assert saved.is_urgent and saved.status == "pending" and saved.current_step == 1
    assert saved.cars == world.cars[:2]
    assert [a.is_overtime for a in saved.assignments] == [False, True]


def test_an_urgent_request_with_a_clashing_second_car_saves_nothing(world):
    world.active_request([(world.cars[1], world.c)])
    app = models.CarReservation(
        organization=world.org,
        creator=world.dispatcher,
        request_type="domestic",
        province_scope="in_province",
        location="x",
        request_reason="ด่วน",
        departure_datetime=DAY,
        return_datetime=DAY + datetime.timedelta(hours=9),
        details=cr.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=2, district="a", province="b"
        ),
    )

    with pytest.raises(flow.CarConflictError):
        flow.submit_urgent(
            app,
            world.dispatcher,
            assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
        )

    assert models.CarReservation.objects(is_urgent=True).count() == 0


def test_an_urgent_request_still_accepts_the_single_car_keywords(world):
    app = models.CarReservation(
        organization=world.org,
        creator=world.dispatcher,
        request_type="domestic",
        province_scope="in_province",
        location="x",
        request_reason="ด่วน",
        departure_datetime=DAY,
        return_datetime=DAY + datetime.timedelta(hours=9),
        details=cr.DomesticDetails(
            vehicle_kind="ตู้", vehicle_count=1, district="a", province="b"
        ),
    )

    flow.submit_urgent(app, world.dispatcher, world.cars[0], world.a, True)

    saved = fresh(app)
    assert saved.cars == [world.cars[0]] and saved.assignments[0].is_overtime is True


def make_insert(world, **fields):
    values = dict(
        organization=world.org,
        creator=world.dispatcher,
        request_type="domestic",
        province_scope="in_province",
        location="ในมหาวิทยาลัย",
        request_reason="งานแทรก",
        departure_datetime=DAY + datetime.timedelta(hours=1),
        return_datetime=DAY + datetime.timedelta(hours=2),
    )
    values.update(fields)
    return models.CarReservation(**values)


def test_an_insert_job_may_reuse_the_car_of_the_same_drivers_assignment(world):
    world.active_request(departure_datetime=DAY)  # (car1, A) และ (car2, B)
    insert = make_insert(world)

    flow.submit_insert(insert, world.dispatcher, world.cars[1], world.b)

    saved = fresh(insert)
    assert saved.status == "active" and saved.is_insert
    assert saved.cars == [world.cars[1]] and saved.drivers == [world.b]


def test_an_insert_job_cannot_take_the_car_of_another_drivers_assignment(world):
    world.active_request(departure_datetime=DAY)
    insert = make_insert(world)

    with pytest.raises(flow.CarConflictError):
        flow.submit_insert(insert, world.dispatcher, world.cars[1], world.a)


# --- ภาระงานรายชุด ---


def test_workload_counts_each_assignment_of_a_request_for_its_own_driver(world):
    now = datetime.datetime(2031, 3, 10, 12, 0)
    departure = now - datetime.timedelta(days=1)
    app = world.active_request(
        [(world.cars[0], world.a), (world.cars[1], world.b)],
        status="completed",
        departure_datetime=departure,
        return_datetime=departure + datetime.timedelta(hours=8),
    )
    first, second = app.assignments
    second.is_overtime = True
    first.started_at, first.completed_at = departure, departure + datetime.timedelta(hours=6)
    first.last_mileage_before, first.last_mileage = 100, 160
    second.started_at, second.completed_at = departure, departure + datetime.timedelta(hours=2)
    second.last_mileage_before, second.last_mileage = 500, 520
    app.save()

    rows = {
        row.driver.id: row
        for row in flow.driver_workload(
            world.org,
            now=now,
            window_start=now,
            window_end=now + datetime.timedelta(days=1),
        )
    }

    a, b, c = rows[world.a.id], rows[world.b.id], rows[world.c.id]
    assert (a.in_hours_jobs, a.ot_jobs, a.hours, a.km) == (1, 0, 6.0, 60)
    assert (b.in_hours_jobs, b.ot_jobs, b.hours, b.km) == (0, 1, 2.0, 20)
    assert (c.in_hours_jobs, c.ot_jobs, c.hours, c.km) == (0, 0, 0.0, 0)


def test_workload_upcoming_and_busy_are_per_assignment(world):
    now = datetime.datetime(2031, 3, 10, 12, 0)
    departure = now + datetime.timedelta(days=2)
    world.active_request(
        [(world.cars[0], world.a), (world.cars[1], world.b)],
        departure_datetime=departure,
        return_datetime=departure + datetime.timedelta(hours=5),
    )

    rows = {
        row.driver.id: row
        for row in flow.driver_workload(
            world.org,
            now=now,
            window_start=departure,
            window_end=departure + datetime.timedelta(days=1),
        )
    }

    assert rows[world.a.id].upcoming == 1 and rows[world.a.id].upcoming_hours == 5.0
    assert rows[world.b.id].upcoming == 1 and rows[world.b.id].busy is True
    assert rows[world.c.id].upcoming == 0 and rows[world.c.id].busy is False


def test_driver_jobs_returns_one_view_model_per_assignment_of_that_driver(world):
    now = datetime.datetime(2031, 3, 10, 12, 0)
    departure = now - datetime.timedelta(days=1)
    app = world.active_request(
        status="completed",
        departure_datetime=departure,
        return_datetime=departure + datetime.timedelta(hours=8),
        location="ที่ทดสอบ",
    )
    app.assignments[1].is_overtime = True
    app.assignments[1].last_mileage_before, app.assignments[1].last_mileage = 10, 40
    app.assignments[1].started_at = departure
    app.assignments[1].completed_at = departure + datetime.timedelta(hours=3)
    app.save()
    future = world.active_request(
        [(world.cars[2], world.b)],
        departure_datetime=now + datetime.timedelta(days=1),
        return_datetime=now + datetime.timedelta(days=1, hours=4),
    )

    done, upcoming = flow.driver_jobs(
        world.org, world.b, now=now, since=now - datetime.timedelta(days=30)
    )

    (job,) = done
    assert isinstance(job, flow.DriverJob)
    assert job.assignment.driver == world.b and job.reservation.id == app.id
    assert (job.id, job.car, job.driver) == (app.id, world.cars[1], world.b)
    assert job.is_overtime is True and job.distance_km == 30
    assert job.started_at == departure and job.completed_at == departure + datetime.timedelta(hours=3)
    assert job.location == "ที่ทดสอบ"  # ช่องของคำขออ่านผ่าน __getattr__
    assert flow.worked_hours(job) == 3.0
    (coming,) = upcoming
    assert coming.id == future.id and flow.booked_hours(coming) == 4.0
    with pytest.raises(AttributeError):
        job.no_such_field


# --- สิทธิ์และการปิดงานรายชุด ---


def test_each_driver_starts_and_closes_only_their_own_assignment(world):
    app = world.active_request()
    first, second = app.assignments

    assert flow.can_start(app, world.a, first) and flow.can_close(app, world.a, first)
    assert not flow.can_close(app, world.a, second)
    assert not flow.can_start(app, world.b, first)
    assert not flow.can_close(app, world.c, first)
    with pytest.raises(flow.FlowError):
        flow.start_trip(app, world.a, second)
    with pytest.raises(flow.FlowError):
        close(app, world.b, first)
    assert fresh(app).status == "active"
    assert fresh(app).assignments[0].completed_at is None


def test_closing_a_foreign_assignment_object_is_refused(world):
    app = world.active_request()
    other = world.active_request([(world.cars[2], world.a)])

    assert not flow.can_close(app, world.a, other.assignments[0])


def test_the_request_completes_only_after_the_last_assignment_is_closed(world):
    app = world.active_request()

    first_done = close(app, world.a, app.assignments[0])

    assert first_done is False
    assert app.status == "active" and app.assignments[0].is_closed
    assert not app.all_closed
    assert not flow.can_close(app, world.a, app.assignments[0])  # ปิดซ้ำไม่ได้
    assert flow.can_close(app, world.b, app.assignments[1])

    last_done = close(app, world.b, app.assignments[1], mileage_out=500, mileage_in=530)

    assert last_done is True
    saved = fresh(app)
    assert saved.status == "completed" and saved.all_closed
    first, second = saved.assignments
    assert (first.last_mileage_before, first.last_mileage, first.distance_km) == (100, 150, 50)
    assert (second.last_mileage_before, second.last_mileage, second.distance_km) == (500, 530, 30)
    assert first.fuel_liters == Decimal("10.00") and first.expense_case == "fleet_card"
    assert first.closed_ip == "10.0.0.9" and first.mileage_photo_in.read() == PNG
    assert second.mileage_photo_in.read() == PNG
    assert first.mileage_photos_at == first.completed_at
    assert [log.action for log in saved.audit_logs] == ["completed", "completed"]
    assert "กก 1111" in saved.audit_logs[0].comment
    assert all(change.label.endswith(")") for change in saved.audit_logs[0].changes)
    assert "กก 1111" in saved.audit_logs[0].changes[0].label


def test_closing_logs_the_trip_report_with_the_plate_of_the_assignment(world):
    app = world.active_request()

    close(app, world.b, app.assignments[1], mileage_out=500, mileage_in=530)

    log = fresh(app).audit_logs[-1]
    assert {change.label: (change.old, change.new) for change in log.changes} == {
        "เลข กม. ออก (กก 2222)": ("-", "500"),
        "เลข กม. กลับ (กก 2222)": ("-", "530"),
        "น้ำมัน (ลิตร) (กก 2222)": ("-", "10"),
        "กรณีค่าใช้จ่าย (กก 2222)": ("-", "เติมฟลีตการ์ดน้ำมัน"),
        "เป็นเงิน (บาท) (กก 2222)": ("-", "100"),
    }
    assert log.actor == world.b


def test_a_single_assignment_closing_log_keeps_the_plain_labels(world):
    app = world.active_request([(world.cars[0], world.a)])

    assert close(app, world.a, app.assignments[0]) is True

    log = fresh(app).audit_logs[-1]
    assert [change.label for change in log.changes][:2] == ["เลข กม. ออก", "เลข กม. กลับ"]
    assert fresh(app).status == "completed"


def test_closing_updates_the_mileage_of_that_assignments_car_only(world):
    app = world.active_request()

    close(app, world.b, app.assignments[1], mileage_in=777)

    assert models.vehicles.Car.objects.get(id=world.cars[1].id).last_mileage == 777
    assert models.vehicles.Car.objects.get(id=world.cars[0].id).last_mileage in (None, 0)


def test_the_mileage_check_applies_per_assignment(world):
    app = world.active_request()

    with pytest.raises(flow.MileageError):
        close(app, world.a, app.assignments[0], mileage_out=200, mileage_in=100)

    assert not fresh(app).assignments[0].is_closed
    assert mileage_files() == 0


def test_two_drivers_closing_back_to_back_through_separate_copies_do_not_overwrite_each_other(world):
    app = world.active_request()
    copy_a, copy_b = fresh(app), fresh(app)

    done_a = close(copy_a, world.a, copy_a.assignments[0], mileage_out=100, mileage_in=150)
    # copy_b ยังเห็นชุดแรกเป็นยังไม่ปิด (ข้อมูลเก่า) ต้องไม่เขียนทับชุดของ พขร. คนแรก
    assert copy_b.assignments[0].completed_at is None
    done_b = close(copy_b, world.b, copy_b.assignments[1], mileage_out=500, mileage_in=530)

    assert (done_a, done_b) == (False, True)
    saved = fresh(app)
    assert saved.status == "completed"
    assert [a.last_mileage for a in saved.assignments] == [150, 530]
    assert all(a.completed_at for a in saved.assignments)
    assert all(a.mileage_photo_in.read() == PNG for a in saved.assignments)
    assert [log.action for log in saved.audit_logs] == ["completed", "completed"]


def test_starts_through_separate_copies_keep_each_drivers_own_start_time(world):
    app = world.active_request()
    copy_a, copy_b = fresh(app), fresh(app)

    flow.start_trip(copy_a, world.a, copy_a.assignments[0])
    flow.start_trip(copy_b, world.b, copy_b.assignments[1])

    saved = fresh(app)
    assert saved.assignments[0].started_at is not None
    assert saved.assignments[1].started_at is not None
    assert [log.action for log in saved.audit_logs] == ["started", "started"]


def test_starting_twice_keeps_the_first_time_and_logs_once(world):
    app = world.active_request()
    stale = fresh(app)

    flow.start_trip(app, world.a, app.assignments[0])
    first_time = app.assignments[0].started_at
    flow.start_trip(app, world.a, app.assignments[0])
    flow.start_trip(stale, world.a, stale.assignments[0])  # แท็บเก่ากดซ้ำ ไม่ error

    saved = fresh(app)
    assert saved.assignments[0].started_at == first_time
    assert [log.action for log in saved.audit_logs] == ["started"]


def test_closing_the_same_assignment_twice_is_refused_and_leaves_the_first_report(world):
    app = world.active_request()
    stale_one, stale_two = fresh(app), fresh(app)

    close(stale_one, world.a, stale_one.assignments[0], mileage_in=150)
    with pytest.raises(flow.ConcurrentChangeError):
        close(stale_two, world.a, stale_two.assignments[0], mileage_in=999)

    saved = fresh(app)
    assert saved.assignments[0].last_mileage == 150
    assert [log.action for log in saved.audit_logs] == ["completed"]
    assert mileage_files() == 1  # รูปของการปิดซ้ำที่ถูกปฏิเสธไม่ค้างใน GridFS
    assert saved.status == "active"


def test_a_request_that_is_not_active_cannot_be_closed(world):
    app = world.active_request(status="cancel_requested")

    assert not flow.can_close(app, world.a, app.assignments[0])


# --- OT รายชุด ---


def test_overtime_is_set_per_assignment_and_audited_with_the_plate(world):
    app = world.new_request(vehicle_count=2)
    flow.approve(
        app,
        world.dispatcher,
        assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
    )
    app = fresh(app)
    second = app.assignments[1]
    assert flow.can_set_overtime(app, world.dispatcher, second)

    flow.set_overtime(app, world.dispatcher, second, True)

    saved = fresh(app)
    assert [a.is_overtime for a in saved.assignments] == [False, True]
    log = saved.audit_logs[-1]
    assert log.action == "overtime_changed"
    (change,) = log.changes
    assert (change.old, change.new) == ("ไม่ใช่", "ใช่")
    assert "กก 2222" in change.label and "กก 2222" in log.comment
    # ชุดแรกไม่ถูกแตะ และตั้งกลับได้
    flow.set_overtime(saved, world.dispatcher, saved.assignments[1], False)
    assert [a.is_overtime for a in fresh(app).assignments] == [False, False]


def test_a_single_assignment_overtime_log_keeps_the_plain_label(world):
    app = world.new_request(vehicle_count=1)
    flow.approve(app, world.dispatcher, car=world.cars[0], driver=world.a)
    app = fresh(app)

    flow.set_overtime(app, world.dispatcher, app.assignments[0], True)

    (change,) = fresh(app).audit_logs[-1].changes
    assert change.label == "งานนอกเวลา (OT)"


def test_overtime_is_locked_for_every_assignment_once_the_request_is_approved(world):
    app = world.active_request()

    for assignment in app.assignments:
        assert not flow.can_set_overtime(app, world.dispatcher, assignment)
        with pytest.raises(flow.FlowError):
            flow.set_overtime(app, world.dispatcher, assignment, True)
    assert not any(a.is_overtime for a in fresh(app).assignments)


def test_only_a_dispatcher_sets_overtime(world):
    app = world.new_request(vehicle_count=1)
    flow.approve(app, world.dispatcher, car=world.cars[0], driver=world.a)
    app = fresh(app)

    assert not flow.can_set_overtime(app, world.requester, app.assignments[0])
    assert not flow.can_set_overtime(app, world.dispatcher, None)


def test_overtime_changes_on_separate_assignments_do_not_overwrite_each_other(world):
    app = world.new_request(vehicle_count=2)
    flow.approve(
        app,
        world.dispatcher,
        assignments=[pair(world.cars[0], world.a), pair(world.cars[1], world.b)],
    )
    copy_one, copy_two = fresh(app), fresh(app)

    flow.set_overtime(copy_one, world.dispatcher, copy_one.assignments[0], True)
    flow.set_overtime(copy_two, world.dispatcher, copy_two.assignments[1], True)

    assert [a.is_overtime for a in fresh(app).assignments] == [True, True]


# --- ยกเลิก ---


def test_cancelling_a_request_without_assignments_cancels_it_at_once(world):
    app = world.new_request(vehicle_count=2)

    flow.cancel(app, world.requester, "เปลี่ยนแผน")

    assert fresh(app).status == "cancelled"


def test_cancelling_a_dispatched_request_asks_the_dispatcher_to_confirm(world):
    app = world.active_request()

    flow.cancel(app, world.requester, "เปลี่ยนแผน")

    assert fresh(app).status == "cancel_requested"
    app = fresh(app)
    flow.confirm_cancel(app, world.dispatcher)
    assert fresh(app).status == "cancelled"


# --- ผู้ขอยืนยันเวลาปิดงานรายชุด ---


def set_completed_at(app, index, completed_at):
    models.CarReservation._get_collection().update_one(
        {"_id": app.id}, {"$set": {f"assignments.{index}.completed_at": completed_at}}
    )


def test_each_assignment_has_its_own_three_day_confirmation_window(world):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    close(app, world.b, app.assignments[1])
    set_completed_at(app, 0, datetime.datetime.now() - datetime.timedelta(days=4))
    app = fresh(app)
    first, second = app.assignments

    assert first.close_confirmation_status() == "auto_confirmed"
    assert not flow.can_confirm_close(app, world.requester, first)
    assert flow.can_confirm_close(app, world.requester, second)
    with pytest.raises(flow.FlowError):
        flow.confirm_close(app, world.requester, first, True)


def test_confirming_one_assignment_leaves_the_other_pending(world):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    close(app, world.b, app.assignments[1])
    app = fresh(app)

    flow.confirm_close(app, world.requester, app.assignments[1], True)

    saved = fresh(app)
    first, second = saved.assignments
    assert second.close_confirmation == "confirmed"
    assert second.close_confirmed_by == world.requester and second.close_confirmed_at
    assert first.close_confirmation is None
    assert flow.can_confirm_close(saved, world.requester, first)
    assert not flow.can_confirm_close(saved, world.requester, second)  # ตอบได้ครั้งเดียว
    log = saved.audit_logs[-1]
    assert log.action == "close_confirmed" and "กก 2222" in log.comment


def test_a_disputed_assignment_needs_the_reported_end_and_keeps_the_note(world):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    app = fresh(app)
    first = app.assignments[0]

    with pytest.raises(flow.FlowError) as error:
        flow.confirm_close(app, world.requester, first, False)
    assert str(error.value) == flow.CLOSE_REPORTED_END_REQUIRED

    reported = datetime.datetime.now().replace(microsecond=0)
    flow.confirm_close(app, world.requester, first, False, reported_end=reported, note=" กลับช้า ")

    saved = fresh(app).assignments[0]
    assert saved.close_confirmation == "disputed"
    assert saved.close_dispute_note == "กลับช้า"
    assert saved.close_reported_end == reported


def test_a_closed_assignment_can_be_confirmed_while_the_request_is_still_active(world):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    app = fresh(app)

    assert app.status == "active"
    assert flow.can_confirm_close(app, world.requester, app.assignments[0])
    assert not flow.can_confirm_close(app, world.requester, app.assignments[1])  # ยังไม่ปิด


def test_two_confirmations_of_the_same_assignment_through_stale_copies_are_refused(world):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    stale_one, stale_two = fresh(app), fresh(app)

    flow.confirm_close(stale_one, world.requester, stale_one.assignments[0], True)
    with pytest.raises(flow.ConcurrentChangeError):
        flow.confirm_close(
            stale_two,
            world.requester,
            stale_two.assignments[0],
            False,
            reported_end=datetime.datetime.now(),
        )

    assert fresh(app).assignments[0].close_confirmation == "confirmed"


def test_only_the_requester_or_an_admin_confirms(world, create_user, assign_user_to_org):
    app = world.active_request()
    close(app, world.a, app.assignments[0])
    app = fresh(app)
    first = app.assignments[0]

    assert not flow.can_confirm_close(app, world.b, first)
    assert not flow.can_confirm_close(app, None, first)
    assert flow.can_confirm_close(app, world.requester, first)


# --- รูปเลขไมล์ ---


def test_any_assignments_driver_may_view_the_mileage_photos(world, create_user):
    app = world.active_request()
    stranger = create_user("Stranger", "Nobody")

    assert flow.can_view_mileage_photos(app, world.a)
    assert flow.can_view_mileage_photos(app, world.b)
    assert flow.can_view_mileage_photos(app, world.requester)
    assert flow.can_view_mileage_photos(app, world.dispatcher)  # ผู้อนุมัติ
    assert not flow.can_view_mileage_photos(app, world.c)
    assert not flow.can_view_mileage_photos(app, stranger)
    assert not flow.can_view_mileage_photos(app, None)


# --- ตรวจชนเวลารายชุด ---


def test_overlapping_bookings_match_a_car_or_driver_of_any_assignment(world):
    other = world.active_request()
    app = world.new_request(vehicle_count=1)

    assert flow._overlapping_bookings(app, car=world.cars[1]).first() == other
    assert flow._overlapping_bookings(app, driver=world.b).first() == other
    assert flow._overlapping_bookings(app, car=world.cars[2]).first() is None
    assert flow._overlapping_bookings(app, driver=world.c).first() is None
    # รถของชุดหนึ่งกับ พขร. ของอีกชุดหนึ่งไม่ใช่ชุดเดียวกัน
    assert flow._overlapping_bookings(app, car=world.cars[0], driver=world.b).first() is None
    assert flow._overlapping_bookings(app, car=world.cars[0], except_driver=world.a).first() is None
    assert flow._overlapping_bookings(app, car=world.cars[0], except_driver=world.b).first() == other


def test_a_driver_double_booked_in_time_is_not_blocked_but_a_car_is(world):
    world.active_request([(world.cars[0], world.a)])
    app = world.new_request(vehicle_count=1)

    # พขร. มีงานอยู่แล้วแค่เตือน (ไม่บล็อก) รถคันเดียวกันเวลาทับบล็อก
    flow.approve(app, world.dispatcher, car=world.cars[1], driver=world.a)
    assert fresh(app).drivers == [world.a]
    other = world.new_request(vehicle_count=1)
    with pytest.raises(flow.CarConflictError):
        flow.approve(other, world.dispatcher, car=world.cars[0], driver=world.b)
