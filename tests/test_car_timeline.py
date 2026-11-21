"""ตารางรถ: data builder (kampan/utils/car_timeline.py) ตำแหน่งแท่ง ตัวกรอง และการจัดกลุ่ม"""

import datetime

import pytest
from werkzeug.datastructures import MultiDict

from kampan import models
from kampan.utils import car_reservation_flow as flow
from kampan.utils import car_timeline

DAY = datetime.date(2031, 1, 10)
NOW = datetime.datetime(2031, 1, 10, 6, 0)


def at(day, hour=0, minute=0):
    return datetime.datetime(2031, 1, day, hour, minute)


@pytest.fixture
def world(app, create_org, create_user, create_car):
    org = create_org("Timeline Util Org")
    other_org = create_org("Other Timeline Org")

    class Setup:
        pass

    s = Setup()
    s.org = org
    s.other_org = other_org
    s.requester = create_user("Requester", "Timeline")
    s.driver = create_user("Driver", "Timeline")
    s.driver2 = create_user("Driver2", "Timeline")
    s.car = create_car(org, "กก 1111", vehicle_type="เก๋ง")
    s.car2 = create_car(org, "ขข 2222", vehicle_type="ตู้")

    def reservation(
        departure,
        return_,
        car=None,
        driver=None,
        status="active",
        assignments=None,
        organization=org,
        location="เชียงใหม่",
    ):
        if assignments is None:
            assignments = [models.CarAssignment(car=car or s.car, driver=driver or s.driver)]
        return models.CarReservation(
            organization=organization,
            creator=s.requester,
            request_type="domestic",
            province_scope="in_province",
            location=location,
            request_reason="ประชุม",
            departure_datetime=departure,
            return_datetime=return_,
            status=status,
            passenger_number=3,
            assignments=assignments,
        ).save()

    s.reservation = reservation

    def build(start=DAY, days=1, filters=None, now=NOW, organization=org):
        return car_timeline.build_timeline(organization, start, days, filters, now=now)

    s.build = build

    def bars_of(timeline, plate):
        [row] = [row for row in timeline.rows if row.car.license_plate == plate]
        return row.bars

    s.bars_of = bars_of

    def plates(timeline):
        return [row.car.license_plate for row in timeline.rows]

    s.plates = plates
    return s


# ------------------------------------------------------------ geometry


def test_a_four_hour_trip_sits_between_12_and_16_of_its_day(world):
    world.reservation(at(10, 12), at(10, 16))

    [bar] = world.bars_of(world.build(days=1), "กก 1111")

    assert bar.left_pct == pytest.approx(50.0)
    assert bar.width_pct == pytest.approx(4 / 24 * 100, abs=1e-3)
    assert not bar.clipped_left and not bar.clipped_right
    assert bar.lane == 0


def test_the_bar_is_positioned_over_the_whole_range_not_just_its_day(world):
    world.reservation(at(12, 12), at(12, 16))

    [bar] = world.bars_of(world.build(start=DAY, days=7), "กก 1111")

    # วันที่ 12 คือวันที่ 3 ของช่วง 7 วัน: (2 วัน + 12 ชม.) / 7 วัน
    assert bar.left_pct == pytest.approx((2 * 24 + 12) / (7 * 24) * 100, abs=1e-3)
    assert bar.width_pct == pytest.approx(4 / (7 * 24) * 100, abs=1e-3)


def test_a_multi_day_trip_is_one_continuous_bar(world):
    world.reservation(at(11, 12), at(13, 12))

    bars = world.bars_of(world.build(start=DAY, days=7), "กก 1111")

    assert len(bars) == 1
    assert bars[0].width_pct == pytest.approx(48 / (7 * 24) * 100, abs=1e-3)


def test_a_trip_is_clipped_at_both_edges_of_the_range(world):
    world.reservation(at(9, 12), at(12, 12))

    [bar] = world.bars_of(world.build(start=DAY, days=1), "กก 1111")

    assert bar.clipped_left and bar.clipped_right
    assert bar.left_pct == 0
    assert bar.width_pct == pytest.approx(100.0)


def test_a_trip_clipped_only_on_the_left_or_the_right(world):
    world.reservation(at(9, 12), at(10, 6), car=world.car)
    world.reservation(at(10, 18), at(11, 12), car=world.car2, driver=world.driver2)

    timeline = world.build(start=DAY, days=1)
    [left] = world.bars_of(timeline, "กก 1111")
    [right] = world.bars_of(timeline, "ขข 2222")

    assert (left.clipped_left, left.clipped_right) == (True, False)
    assert left.left_pct == 0 and left.width_pct == pytest.approx(25.0)
    assert (right.clipped_left, right.clipped_right) == (False, True)
    assert right.left_pct == pytest.approx(75.0) and right.width_pct == pytest.approx(25.0)


def test_trips_outside_the_range_are_not_drawn(world):
    world.reservation(at(9, 8), at(9, 18))
    world.reservation(at(11, 0), at(11, 6))  # เริ่มพอดีเวลาสิ้นสุดของช่วง

    assert world.bars_of(world.build(start=DAY, days=1), "กก 1111") == []


def test_two_overlapping_bars_in_one_row_get_different_lanes_and_the_row_grows(world):
    world.reservation(at(10, 8), at(10, 14), driver=world.driver)
    world.reservation(at(10, 12), at(10, 18), driver=world.driver2)
    world.reservation(at(10, 14), at(10, 16), driver=world.driver2)  # ต่อจากแท่งแรกพอดี ใช้เลนเดิมได้

    timeline = world.build(days=1)
    [row] = [row for row in timeline.rows if row.car.license_plate == "กก 1111"]

    lanes = {(bar.departure.hour, bar.return_.hour): bar.lane for bar in row.bars}
    assert lanes[(8, 14)] == 0
    assert lanes[(12, 18)] == 1
    assert lanes[(14, 16)] == 0
    assert row.lane_count == 2


def test_a_row_without_bars_has_one_lane(world):
    [row] = [row for row in world.build().rows if row.car.license_plate == "กก 1111"]

    assert row.bars == [] and row.lane_count == 1


def test_a_two_car_request_has_a_bar_in_each_cars_row(world):
    reservation = world.reservation(
        at(10, 8),
        at(10, 17),
        assignments=[
            models.CarAssignment(car=world.car, driver=world.driver),
            models.CarAssignment(car=world.car2, driver=world.driver2),
        ],
    )

    timeline = world.build()
    [first] = world.bars_of(timeline, "กก 1111")
    [second] = world.bars_of(timeline, "ขข 2222")

    assert first.reservation_id == second.reservation_id == str(reservation.id)
    assert first.assignment_id != second.assignment_id
    assert first.driver_name != second.driver_name


def test_a_bar_carries_the_requester_driver_destination_and_overtime(world):
    world.reservation(
        at(10, 8),
        at(10, 17),
        assignments=[models.CarAssignment(car=world.car, driver=world.driver, is_overtime=True)],
        location="หาดใหญ่",
    )

    [bar] = world.bars_of(world.build(), "กก 1111")

    assert bar.requester_name == "Requester Timeline"
    assert bar.driver_name == "Driver Timeline"
    assert bar.location == "หาดใหญ่" and bar.label == "หาดใหญ่"
    assert bar.passenger_number == 3
    assert bar.is_overtime is True
    assert bar.status_label == "อนุมัติแล้ว"


def test_a_trip_without_a_return_time_is_drawn_one_hour_long(world):
    reservation = world.reservation(at(10, 8), at(10, 9))
    models.CarReservation.objects(id=reservation.id).update(set__return_datetime=at(10, 8))

    [bar] = world.bars_of(world.build(), "กก 1111")

    assert bar.width_pct == pytest.approx(1 / 24 * 100, abs=1e-3)


def test_requests_without_assignments_are_not_drawn(world):
    world.reservation(at(10, 8), at(10, 17), assignments=[])

    assert all(row.bars == [] for row in world.build().rows)


# ------------------------------------------------------------ statuses


@pytest.mark.parametrize("status", ["pending", "active", "cancel_requested", "completed"])
def test_live_and_completed_statuses_are_shown_by_default(world, status):
    world.reservation(at(10, 8), at(10, 17), status=status)

    [bar] = world.bars_of(world.build(), "กก 1111")

    assert bar.status == status


@pytest.mark.parametrize("status", ["cancelled", "denied"])
def test_cancelled_and_denied_are_hidden_until_the_status_filter_asks(world, status):
    world.reservation(at(10, 8), at(10, 17), status=status)

    assert world.bars_of(world.build(), "กก 1111") == []
    shown = world.build(filters=car_timeline.TimelineFilters(statuses=[status]))
    [bar] = world.bars_of(shown, "กก 1111")
    assert bar.status == status


def test_the_status_filter_narrows_to_the_chosen_statuses(world):
    world.reservation(at(10, 6), at(10, 8), status="pending")
    world.reservation(at(10, 10), at(10, 12), status="active")

    timeline = world.build(filters=car_timeline.TimelineFilters(statuses=["pending"]))

    assert [bar.status for bar in world.bars_of(timeline, "กก 1111")] == ["pending"]


# ------------------------------------------------------------ scoping and filters


def test_only_active_cars_of_the_organization_are_listed(world, create_car):
    create_car(world.org, "งง 4444", status="disactive", vehicle_type="เก๋ง")
    create_car(world.other_org, "จจ 5555", vehicle_type="เก๋ง")

    assert world.plates(world.build()) == ["ขข 2222", "กก 1111"]


def test_other_organizations_reservations_are_not_drawn(world, create_car):
    foreign_car = create_car(world.other_org, "จจ 5555")
    world.reservation(
        at(10, 8),
        at(10, 17),
        organization=world.other_org,
        assignments=[models.CarAssignment(car=foreign_car, driver=world.driver)],
    )
    # คำขอขององค์กรอื่นที่ (ผิดปกติ) อ้างรถขององค์กรเรา ก็ไม่ถูกวาด
    world.reservation(at(10, 8), at(10, 17), organization=world.other_org, car=world.car)

    timeline = world.build()

    assert all(row.bars == [] for row in timeline.rows)
    assert world.plates(world.build(organization=world.other_org)) == ["จจ 5555"]


def test_the_plate_filter_is_a_case_insensitive_substring(world, create_car):
    create_car(world.org, "AB 123", vehicle_type="เก๋ง")

    assert world.plates(
        world.build(filters=car_timeline.TimelineFilters(q="ab 1"))
    ) == ["AB 123"]
    assert world.plates(
        world.build(filters=car_timeline.TimelineFilters(q="2222"))
    ) == ["ขข 2222"]
    assert world.plates(world.build(filters=car_timeline.TimelineFilters(q="zz"))) == []


def test_the_vehicle_type_filter_accepts_several_types(world, create_car):
    create_car(world.org, "คค 3333", vehicle_type="บัส")

    only_van = world.build(filters=car_timeline.TimelineFilters(vehicle_types=["ตู้"]))
    van_and_bus = world.build(
        filters=car_timeline.TimelineFilters(vehicle_types=["ตู้", "บัส"])
    )

    assert world.plates(only_van) == ["ขข 2222"]
    assert world.plates(van_and_bus) == ["คค 3333", "ขข 2222"]


def test_the_driver_filter_keeps_only_that_drivers_bars_and_cars(world):
    world.reservation(at(10, 8), at(10, 12), car=world.car, driver=world.driver)
    world.reservation(at(10, 8), at(10, 12), car=world.car2, driver=world.driver2)
    world.reservation(at(10, 13), at(10, 15), car=world.car2, driver=world.driver)

    timeline = world.build(
        filters=car_timeline.TimelineFilters(driver_id=str(world.driver.id))
    )

    assert world.plates(timeline) == ["ขข 2222", "กก 1111"]
    assert {bar.driver_name for row in timeline.rows for bar in row.bars} == {
        "Driver Timeline"
    }
    assert len(world.bars_of(timeline, "ขข 2222")) == 1

    only_second = world.build(
        filters=car_timeline.TimelineFilters(driver_id=str(world.driver2.id))
    )
    assert world.plates(only_second) == ["ขข 2222"]


def test_free_during_hides_cars_occupied_in_the_window(world):
    world.reservation(at(10, 8), at(10, 12), car=world.car)

    window = car_timeline.TimelineFilters(free_from=at(10, 11), free_to=at(10, 13))
    clear = car_timeline.TimelineFilters(free_from=at(10, 12), free_to=at(10, 14))

    assert world.plates(world.build(filters=window)) == ["ขข 2222"]
    # ชนกันเมื่อเวลาทับจริงเท่านั้น: ต่อกันพอดีไม่ชน (เหมือนที่ server บล็อก)
    assert world.plates(world.build(filters=clear)) == ["ขข 2222", "กก 1111"]


@pytest.mark.parametrize(
    "status, hides",
    [
        ("pending", True),
        ("active", True),
        ("cancel_requested", True),
        ("completed", False),
        ("cancelled", False),
        ("denied", False),
    ],
)
def test_free_during_counts_the_same_statuses_as_the_server_blocks(world, status, hides):
    world.reservation(at(10, 8), at(10, 12), car=world.car, status=status)

    free = car_timeline.TimelineFilters(
        free_from=at(10, 9),
        free_to=at(10, 10),
        # ให้เห็นรถทุกสถานะ เพื่อดูว่าตัวกรอง "ว่างช่วง" เป็นคนซ่อน ไม่ใช่ตัวกรองสถานะ
        statuses=list(car_timeline.ALL_STATUSES),
    )

    assert ("กก 1111" not in world.plates(world.build(filters=free))) is hides
    assert (status in flow.OCCUPYING_STATUSES) is hides


def test_free_during_also_hides_cars_lent_through_the_legacy_diis_system(world):
    models.vehicle_applications.CarApplication(
        organization=world.org,
        car=world.car2,
        location="สนามบิน",
        status="active",
        using_type="general",
        request_reason="ไปราชการ",
        departure_datetime=at(10, 8),
        return_datetime=at(10, 12),
    ).save()

    window = car_timeline.TimelineFilters(free_from=at(10, 9), free_to=at(10, 10))

    assert world.plates(world.build(filters=window)) == ["กก 1111"]


def test_free_during_ignores_other_organizations_bookings(world):
    world.reservation(at(10, 8), at(10, 12), car=world.car, organization=world.other_org)

    window = car_timeline.TimelineFilters(free_from=at(10, 9), free_to=at(10, 10))

    assert world.plates(world.build(filters=window)) == ["ขข 2222", "กก 1111"]


def test_an_incomplete_or_inverted_free_window_filters_nothing(world):
    world.reservation(at(10, 8), at(10, 12), car=world.car)

    half = car_timeline.TimelineFilters(free_from=at(10, 9))
    inverted = car_timeline.TimelineFilters(free_from=at(10, 10), free_to=at(10, 9))

    assert world.plates(world.build(filters=half)) == ["ขข 2222", "กก 1111"]
    assert world.plates(world.build(filters=inverted)) == ["ขข 2222", "กก 1111"]


# ------------------------------------------------------------ groups and columns


def test_groups_follow_the_fixed_type_order_with_counts_and_labels(world, create_car):
    create_car(world.org, "คค 3333", vehicle_type="บัส")
    create_car(world.org, "งง 4444", vehicle_type="มินิบัส")
    create_car(world.org, "จจ 5555", vehicle_type="เก๋ง")
    create_car(world.org, "ฉฉ 6666")  # ไม่ระบุประเภท

    timeline = world.build()

    assert [group.key for group in timeline.groups] == ["บัส", "มินิบัส", "ตู้", "เก๋ง", ""]
    assert [group.label for group in timeline.groups] == [
        "รถบัส",
        "รถมินิบัส",
        "รถตู้",
        "รถเก๋ง",
        "ไม่ระบุประเภท",
    ]
    assert [group.car_count for group in timeline.groups] == [1, 1, 1, 2, 1]
    assert timeline.car_count == 6
    assert [row.car.license_plate for row in timeline.groups[3].rows] == ["กก 1111", "จจ 5555"]


def test_an_unlisted_type_goes_after_the_known_ones_before_untyped(world, create_car):
    models.vehicles.Car.objects(id=world.car2.id).update(set__vehicle_type="รถราง")
    create_car(world.org, "ฉฉ 6666")

    assert [g.key for g in world.build().groups] == ["เก๋ง", "รถราง", ""]


def test_groups_without_cars_are_left_out(world):
    timeline = world.build(filters=car_timeline.TimelineFilters(vehicle_types=["เก๋ง"]))

    assert [group.key for group in timeline.groups] == ["เก๋ง"]


def test_day_columns_flag_weekends_holidays_and_today(world):
    # 2031-01-10 เป็นวันศุกร์ -> 11 เสาร์ 12 อาทิตย์
    models.CarHoliday(organization=world.org, date=datetime.date(2031, 1, 13), name="วันครู").save()
    models.CarHoliday(
        organization=world.other_org, date=datetime.date(2031, 1, 14), name="ของที่อื่น"
    ).save()

    timeline = world.build(start=DAY, days=7)
    columns = {c.date.day: c for c in timeline.columns}

    assert len(timeline.columns) == 7
    assert [c.weekday_label for c in timeline.columns][:3] == ["ศ.", "ส.", "อา."]
    assert (columns[11].is_weekend, columns[12].is_weekend, columns[10].is_weekend) == (
        True,
        True,
        False,
    )
    assert columns[13].is_holiday and columns[13].holiday_name == "วันครู"
    assert not columns[14].is_holiday
    assert columns[10].is_today and not columns[11].is_today
    assert columns[10].day_number == 10 and columns[10].month_label == "ม.ค. 2574"
    assert [(m.label, m.span) for m in timeline.months] == [("ม.ค. 2574", 7)]


def test_month_spans_split_when_the_range_crosses_a_month(world):
    timeline = world.build(start=datetime.date(2031, 1, 28), days=7)

    assert [(m.label, m.span) for m in timeline.months] == [("ม.ค. 2574", 4), ("ก.พ. 2574", 3)]


def test_the_now_marker_is_a_percentage_of_the_range_or_none_outside(world):
    inside = world.build(start=DAY, days=1, now=at(10, 6))
    middle = world.build(start=DAY, days=7, now=at(13, 12))
    before = world.build(start=datetime.date(2031, 1, 11), days=7, now=NOW)
    after = world.build(start=datetime.date(2031, 1, 1), days=7, now=NOW)
    edge = world.build(start=DAY, days=1, now=at(11, 0))

    assert inside.now_pct == pytest.approx(25.0)
    assert middle.now_pct == pytest.approx((3 * 24 + 12) / (7 * 24) * 100, abs=1e-3)
    assert before.now_pct is None and after.now_pct is None and edge.now_pct is None


def test_only_the_one_day_view_has_hour_ticks(world):
    assert [label for label, _ in world.build(days=1).hour_ticks][:3] == ["00:00", "03:00", "06:00"]
    assert world.build(days=7).hour_ticks == []


def test_an_invalid_days_value_falls_back_to_fourteen(world):
    assert world.build(days=5).day_count == 14
    assert world.build(days="abc").day_count == 14
    assert world.build(days=30).day_count == 30


# ------------------------------------------------------------ query parsing


def parse(**args):
    return car_timeline.parse_query(
        MultiDict({k: v for k, v in args.items() if not isinstance(v, list)})
        if not any(isinstance(v, list) for v in args.values())
        else MultiDict([(k, x) for k, v in args.items() for x in (v if isinstance(v, list) else [v])]),
        today=DAY,
    )


def test_parse_query_defaults():
    start, days, filters = parse()

    assert start == DAY and days == 14
    assert filters.statuses == list(car_timeline.DEFAULT_STATUSES)
    assert filters.vehicle_types == [] and filters.q == "" and filters.driver_id == ""
    assert filters.free_window is None and filters.free_error == ""


def test_parse_query_reads_every_filter():
    start, days, filters = parse(
        start="2031-02-01",
        days="7",
        vehicle_type=["ตู้", "บัส"],
        q=" กก ",
        driver="5f1d7f3b8f1b2c3d4e5f6a7b",
        status=["cancelled", "active"],
        free_from="2031-02-02T08:00",
        free_to="2031-02-02T17:30",
    )

    assert start == datetime.date(2031, 2, 1) and days == 7
    assert filters.vehicle_types == ["ตู้", "บัส"]
    assert filters.q == "กก"
    assert filters.driver_id == "5f1d7f3b8f1b2c3d4e5f6a7b"
    assert filters.statuses == ["cancelled", "active"]
    assert filters.free_window == (at(2, 8).replace(month=2), at(2, 17, 30).replace(month=2))


@pytest.mark.parametrize(
    "args",
    [
        {"start": "not-a-date", "days": "abc"},
        {"start": "0001-01-01", "days": "-3"},
        {"start": "9999-12-31", "days": "99"},
        {"start": "2031-13-45"},
        {"vehicle_type": "รถไฟ", "status": "bogus", "driver": "<script>"},
        {"free_from": "garbage", "free_to": "2031-01-01T10:00"},
        {"free_from": "2031-01-01T10:00"},
    ],
)
def test_parse_query_ignores_garbage(args):
    start, days, filters = parse(**args)

    assert start == DAY and days == 14
    assert filters.vehicle_types == [] and filters.driver_id == ""
    assert filters.statuses == list(car_timeline.DEFAULT_STATUSES)
    assert filters.free_window is None


def test_an_inverted_free_window_is_dropped_with_a_message():
    _, _, filters = parse(free_from="2031-01-02T10:00", free_to="2031-01-02T09:00")

    assert filters.free_window is None
    assert filters.free_error


def test_query_args_round_trip_through_parse_query():
    original = parse(
        start="2031-02-01",
        days="30",
        vehicle_type=["ตู้"],
        q="กก",
        driver="5f1d7f3b8f1b2c3d4e5f6a7b",
        status=["pending", "denied"],
        free_from="2031-02-02T08:00",
        free_to="2031-02-02T17:30",
    )

    args = car_timeline.query_args(*original, today=DAY)
    multi = MultiDict(
        [(k, x) for k, v in args.items() for x in (v if isinstance(v, list) else [v])]
    )

    assert car_timeline.parse_query(multi, today=DAY) == original


def test_query_args_skip_defaults_and_today():
    start, days, filters = parse()

    assert car_timeline.query_args(start, days, filters, today=DAY) == {}
    assert car_timeline.query_args(
        DAY + datetime.timedelta(days=14), 14, filters, today=DAY
    ) == {"start": "2031-01-24"}


# ------------------------------------------------------------ flow helpers (ใช้ร่วมกับ server)


def test_overlapping_reservations_counts_only_occupying_statuses_inside_the_window(world):
    live = world.reservation(at(10, 8), at(10, 12), status="pending")
    world.reservation(at(10, 8), at(10, 12), status="completed")
    world.reservation(at(10, 8), at(10, 12), status="denied")
    world.reservation(at(10, 8), at(10, 12), organization=world.other_org)
    world.reservation(at(10, 12), at(10, 14))  # ต่อกันพอดี ไม่ทับ

    found = flow.overlapping_reservations(world.org, at(10, 11), at(10, 12))

    assert [r.id for r in found] == [live.id]
    assert flow.OCCUPYING_STATUSES == ["pending", "active", "cancel_requested"]
    assert flow.overlapping_reservations(world.org, at(10, 11), at(10, 12), exclude_id=live.id).count() == 0


def test_overlapping_reservations_filters_by_car_and_driver_of_the_same_assignment(world):
    world.reservation(at(10, 8), at(10, 12), car=world.car, driver=world.driver)

    args = (world.org, at(10, 9), at(10, 10))

    assert flow.overlapping_reservations(*args, car=world.car).count() == 1
    assert flow.overlapping_reservations(*args, car=world.car2).count() == 0
    assert flow.overlapping_reservations(*args, driver=world.driver).count() == 1
    assert flow.overlapping_reservations(*args, car=world.car, driver=world.driver2).count() == 0
    assert flow.overlapping_reservations(*args, car=world.car, except_driver=world.driver).count() == 0


def test_diis_bookings_overlapping_is_scoped_to_org_window_and_car(world):
    models.vehicle_applications.CarApplication(
        organization=world.org,
        car=world.car,
        location="สนามบิน",
        status="active",
        using_type="general",
        request_reason="ไปราชการ",
        departure_datetime=at(10, 8),
        return_datetime=at(10, 12),
    ).save()

    assert flow.diis_bookings_overlapping(world.org, at(10, 9), at(10, 10)).count() == 1
    assert flow.diis_bookings_overlapping(world.org, at(10, 9), at(10, 10), car=world.car).count() == 1
    assert flow.diis_bookings_overlapping(world.org, at(10, 9), at(10, 10), car=world.car2).count() == 0
    assert flow.diis_bookings_overlapping(world.org, at(10, 12), at(10, 13)).count() == 0
    assert flow.diis_bookings_overlapping(world.other_org, at(10, 9), at(10, 10)).count() == 0
