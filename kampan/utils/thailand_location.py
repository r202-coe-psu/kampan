"""ข้อมูลอ้างอิง จังหวัด / อำเภอ / ตำบล ของประเทศไทย (77 / 928 / 7,426)

ข้อมูลมาจาก `thailand_location_data.json` ของโปรเจกต์ tent เก็บแบบแถวแบน
`{province, district, subdistrict, zipcode}` อ่านครั้งเดียวแล้วเก็บ index ไว้ใน memory
สงขลาและหาดใหญ่ขึ้นก่อน เพราะผู้ใช้ส่วนใหญ่อยู่ในพื้นที่ (ตรงกับ tent)
"""

import functools
import json
import pathlib
import re

DATA_PATH = pathlib.Path(__file__).parent / "data" / "thailand_location.json"

PINNED_PROVINCE = "สงขลา"
PINNED_DISTRICT = "หาดใหญ่"

# สระหน้า (เ แ โ ใ ไ) เขียนก่อนพยัญชนะแต่พจนานุกรมเรียงตามพยัญชนะ จึงสลับก่อนเทียบ
_LEADING_VOWEL = re.compile("([เแโใไ])([ก-ฮ])")
_TONE_MARKS = re.compile("[่-๋์]")


def thai_sort_key(text):
    swapped = _LEADING_VOWEL.sub(r"\2\1", text)
    return (_TONE_MARKS.sub("", swapped), swapped)


def _pin_first(values, pinned):
    return sorted(values, key=lambda value: value != pinned)


@functools.cache
def _index():
    rows = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    index = {}
    for row in rows:
        districts = index.setdefault(row["province"], {})
        districts.setdefault(row["district"], []).append(
            {"subdistrict": row["subdistrict"], "zipcode": row["zipcode"]}
        )
    return index


def list_provinces():
    return _pin_first(sorted(_index(), key=thai_sort_key), PINNED_PROVINCE)


def list_districts(province):
    districts = sorted(_index().get(province, {}), key=thai_sort_key)
    if province == PINNED_PROVINCE:
        return _pin_first(districts, PINNED_DISTRICT)
    return districts


def list_subdistricts(province, district):
    rows = _index().get(province, {}).get(district, [])
    return sorted(rows, key=lambda row: thai_sort_key(row["subdistrict"]))


def is_valid(province, district=None, subdistrict=None):
    districts = _index().get(province)
    if districts is None:
        return False
    if district is None:
        return True
    rows = districts.get(district)
    if rows is None:
        return False
    if subdistrict is None:
        return True
    return any(row["subdistrict"] == subdistrict for row in rows)


def options(level, province="", district="", current=""):
    """ตัวเลือกของ dropdown ระดับ `level` เป็นคู่ (value, label)

    ถ้าค่าที่บันทึกไว้เดิม (`current`) ไม่อยู่ในชุดข้อมูล (คำขอเก่าที่พิมพ์เอง)
    ใส่ไว้บนสุดพร้อมป้าย "(ค่าเดิม)" เพื่อให้ผู้ใช้เห็นว่าต้องเลือกใหม่
    """
    if level == "province":
        names = list_provinces()
    elif level == "district":
        names = list_districts(province) if province else []
    else:
        names = [row["subdistrict"] for row in list_subdistricts(province, district)]
    choices = [(name, name) for name in names]
    if current and current not in names:
        choices.insert(0, (current, f"{current} (ค่าเดิม)"))
    return choices
