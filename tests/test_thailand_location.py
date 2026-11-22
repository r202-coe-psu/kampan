"""ข้อมูลอ้างอิง จังหวัด / อำเภอ / ตำบล และ API ที่ dropdown ต่อกันในฟอร์มใช้"""

import pytest

from kampan.utils import thailand_location

API = "/api/thailand-location"

# fixture autouse ของ conftest ต่อฐานข้อมูล จึงต้องมี app แม้เทสต์จะไม่เรียก view
pytestmark = pytest.mark.usefixtures("app")


def test_all_77_provinces_with_songkhla_first():
    provinces = thailand_location.list_provinces()

    assert len(provinces) == 77
    assert provinces[0] == "สงขลา"
    assert provinces.index("กระบี่") < provinces.index("กรุงเทพมหานคร")


def test_hat_yai_leads_the_districts_of_songkhla():
    districts = thailand_location.list_districts("สงขลา")

    assert districts[0] == "หาดใหญ่"
    assert "จะนะ" in districts
    assert "เมืองปัตตานี" not in districts


def test_leading_vowels_sort_by_their_consonant():
    districts = thailand_location.list_districts("ปัตตานี")

    # เมือง (ม) มาก่อน ยะรัง (ย) แม้ "เ" จะมีรหัสหลัง "ย"
    assert districts.index("เมืองปัตตานี") < districts.index("ยะรัง")


def test_subdistricts_come_with_their_zipcode():
    rows = thailand_location.list_subdistricts("สงขลา", "หาดใหญ่")

    assert {"subdistrict": "คอหงส์", "zipcode": 90110} in rows


def test_unknown_names_give_empty_lists():
    assert thailand_location.list_districts("ไม่มีจังหวัดนี้") == []
    assert thailand_location.list_subdistricts("สงขลา", "เมืองปัตตานี") == []


@pytest.mark.parametrize(
    "args, expected",
    [
        (("สงขลา",), True),
        (("สงขลา", "หาดใหญ่"), True),
        (("สงขลา", "หาดใหญ่", "คอหงส์"), True),
        (("สงขลา", "เมืองปัตตานี"), False),
        (("สงขลา", "หาดใหญ่", "รูสะมิแล"), False),
        (("หาดใหญ่",), False),
    ],
)
def test_is_valid_checks_the_whole_chain(args, expected):
    assert thailand_location.is_valid(*args) is expected


def test_options_keep_an_old_free_text_value_marked_as_old():
    choices = thailand_location.options("district", province="สงขลา", current="อ.หาดใหญ่")

    assert choices[0] == ("อ.หาดใหญ่", "อ.หาดใหญ่ (ค่าเดิม)")
    assert ("หาดใหญ่", "หาดใหญ่") in choices


def test_district_options_are_empty_until_a_province_is_chosen():
    assert thailand_location.options("district") == []


@pytest.fixture
def client(app, create_user, login_as):
    return login_as(app.test_client(), create_user("Location", "Reader"))


def test_api_needs_login(app):
    response = app.test_client().get(f"{API}/provinces")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_lists_provinces(client):
    response = client.get(f"{API}/provinces")

    assert response.status_code == 200
    assert response.get_json()[0] == "สงขลา"
    assert "max-age" in response.headers["Cache-Control"]


def test_api_lists_districts_of_a_province(client):
    response = client.get(f"{API}/districts", query_string={"province": "สงขลา"})

    assert response.get_json()[0] == "หาดใหญ่"


def test_api_lists_subdistricts_of_a_district(client):
    response = client.get(
        f"{API}/subdistricts", query_string={"province": "สงขลา", "district": "หาดใหญ่"}
    )

    assert {"subdistrict": "คอหงส์", "zipcode": 90110} in response.get_json()


@pytest.mark.parametrize(
    "path, query",
    [
        ("districts", {}),
        ("subdistricts", {"province": "สงขลา"}),
        ("subdistricts", {"district": "หาดใหญ่"}),
    ],
)
def test_api_rejects_a_missing_parent(client, path, query):
    response = client.get(f"{API}/{path}", query_string=query)

    assert response.status_code == 400


def test_api_returns_empty_for_an_unknown_province(client):
    response = client.get(f"{API}/districts", query_string={"province": "ไม่มี"})

    assert response.status_code == 200
    assert response.get_json() == []


def test_changing_a_returned_subdistrict_does_not_touch_the_cached_data():
    rows = thailand_location.list_subdistricts("สงขลา", "หาดใหญ่")
    rows[0]["subdistrict"] = "แก้แล้ว"

    again = thailand_location.list_subdistricts("สงขลา", "หาดใหญ่")
    assert "แก้แล้ว" not in {row["subdistrict"] for row in again}


def test_options_reject_an_unknown_level():
    with pytest.raises(ValueError):
        thailand_location.options("village", province="สงขลา")


def test_changing_the_returned_provinces_does_not_touch_the_cached_list():
    provinces = thailand_location.list_provinces()
    provinces.clear()

    assert len(thailand_location.list_provinces()) == 77
