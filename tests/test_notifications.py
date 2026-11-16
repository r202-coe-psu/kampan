"""แจ้งเตือนในระบบ (กระดิ่ง): เหตุการณ์ของคำขอใช้รถส่งถึงผู้เกี่ยวข้องในองค์กรเดียวกัน"""

from kampan.utils import notifications
from tests.test_car_reservation import (  # noqa: F401
    approve_url,
    mock_redis_queue,
    request_at_dispatcher,
    step_data,
    world,
)


def events_of(user, org):
    return [n.event for n in notifications.inbox(user, org)]


def test_submitting_a_request_notifies_the_division_head_but_not_the_requester(world):
    world.submit_request()

    assert events_of(world.supervisor, world.org) == ["submitted"]
    assert events_of(world.requester, world.org) == []
