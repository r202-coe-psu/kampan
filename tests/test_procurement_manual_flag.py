"""หน้าคู่มือ procurement ตาม PROCUREMENT_REQUISITION_ENABLED

เมื่อปิดระบบขอซื้อขอจ้าง route ของขอซื้อขอจ้าง / timeline / MAS ตอบ 404
หน้าคู่มือจึงต้องไม่มีหัวข้อและลิงก์ของส่วนนั้น เหลือเฉพาะเนื้อหา MA และเลขโมดูลต้องรันต่อกัน
เมื่อเปิด หน้าคู่มือต้องเหมือนเดิมทุกหัวข้อ

เรียก request โดยไม่มี app_context ครอบ เพื่อไม่ให้ flask-login cache ผู้ใช้คนก่อนไว้ใน g
"""

import re

import pytest

FLAG = "PROCUREMENT_REQUISITION_ENABLED"
GATED_HREFS = (
    'href="/procurement/requisitions/renewal_requested',
    'href="/procurement/requisition_timeline',  # รวม requisition_timeline_items
    'href="/admin/mas',
)
REQUISITION_SECTION_IDS = (
    "flow-main",
    "renewal-requested",
    "mas",
    "create-requisition",
    "head-approve",
    "admin-approve",
    "manager-approve",
    "timeline",
    "timeline-items",
    "billing",
    "document",
    "status",
)
REQUISITION_HEADINGS = (
    "รายการขอซื้อขอจ้าง",
    "แหล่งเงินงบประมาณระบบ MAS",
    "สร้างและแก้ไขคำขอซื้อขอจ้าง",
    "หัวหน้าฝ่ายอนุมัติขั้นที่ 1",
    "เจ้าหน้าที่พัสดุอนุมัติและจองเงินงบประมาณ",
    "ผู้จัดการอนุมัติขั้นสุดท้าย",
    "ติดตามความคืบหน้าการดำเนินงาน 8 ขั้นตอน",
    "บันทึกการเบิกจ่ายงบประมาณ",
    "เอกสารคำขอและพิมพ์รายงาน",
    "ตารางสรุปสถานะคำขอและขั้นตอนการดำเนินงาน",
    "ขั้นตอนการทำงานภาพรวมทั้งระบบ",
)
MA_SECTION_IDS = (
    "overview",
    "upload-files",
    "products",
    "payment",
    "procurement-list",
    "non-renewal",
)


@pytest.fixture
def set_flag(app, monkeypatch):
    def _set_flag(value):
        monkeypatch.setitem(app.config, FLAG, value)

    # เริ่มจากไม่มีค่าใน config เหมือน web app ที่ไม่ได้โหลด default_settings.py (= ปิด)
    monkeypatch.delitem(app.config, FLAG, raising=False)
    return _set_flag


@pytest.fixture
def get_manual(app, create_org, create_user, assign_user_to_org):
    def _get_manual(role="admin"):
        org = create_org("[TEST] Manual Org")
        user = create_user(role.capitalize(), "Manual")
        assign_user_to_org(user, org, roles=[role])

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(user.id)
            sess["_fresh"] = True

        response = client.get(f"/procurement/manuals?organization_id={org.id}")
        return response, response.data.decode("utf-8")

    return _get_manual


def section_ids(html):
    return re.findall(r'<section id="([^"]+)"', html)


def toc_labels(html):
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        for label in re.findall(r'class="toc-link[^"]*"[^>]*>(.*?)</a>', html, re.S)
    ]


@pytest.mark.parametrize("role", ["admin", "staff", "head", "manager"])
def test_manual_hides_requisition_when_flag_off(set_flag, get_manual, role):
    response, html = get_manual(role)

    assert response.status_code == 200
    for href in GATED_HREFS:
        assert href not in html
    ids = section_ids(html)
    for anchor in REQUISITION_SECTION_IDS:
        assert anchor not in ids
        assert f'data-toc-link="{anchor}"' not in html
    for heading in REQUISITION_HEADINGS:
        assert heading not in html
    assert ids == list(MA_SECTION_IDS)


def test_manual_flag_off_title_and_numbering(set_flag, get_manual):
    _, html = get_manual("admin")

    assert "คู่มือการใช้งานระบบจัดการสัญญา (MA)" in html
    assert "ระบบขอซื้อขอจ้าง" not in html
    assert "MAS" not in html
    assert "แหล่งเงิน" not in html
    assert "(5 โมดูล)" in html
    # เลขโมดูลใน TOC และหัวข้อต้องรันต่อกัน 1..5 ตามหัวข้อที่เหลือ
    assert toc_labels(html) == [
        "ภาพรวมและบทบาทผู้ใช้งาน",
        "1. อัปโหลดไฟล์นำเข้าข้อมูลสัญญาบริการ",
        "2. รายการสินค้าและสัญญาบริการ",
        "3. บันทึกการชำระเงินสินค้า",
        "4. รายการสัญญาบริการที่ใกล้หมดอายุ",
        "5. รายการสัญญาบริการที่ไม่ต่ออายุ",
    ]
    assert re.findall(r"โมดูลที่ (\d+)", html) == ["1", "2", "3", "4", "5"]


@pytest.mark.parametrize("value", [True, "True"])
def test_manual_shows_requisition_when_flag_on(set_flag, get_manual, value):
    set_flag(value)
    response, html = get_manual("admin")

    assert response.status_code == 200
    for href in GATED_HREFS:
        assert href in html
    ids = section_ids(html)
    for anchor in REQUISITION_SECTION_IDS + MA_SECTION_IDS:
        assert anchor in ids
    for heading in REQUISITION_HEADINGS:
        assert heading in html
    assert "คู่มือการใช้งานระบบขอซื้อขอจ้างและบริหารสัญญา (MA)" in html
    assert "(15 โมดูล)" in html
    labels = toc_labels(html)
    assert len(labels) == 18
    assert labels[2] == "1. อัปโหลดไฟล์นำเข้าข้อมูลแหล่งเงินและสัญญาบริการ"
    assert labels[16] == "15. เอกสารคำขอและพิมพ์รายงาน"
    assert re.findall(r"โมดูลที่ (\d+)", html) == [str(n) for n in range(1, 16)]
