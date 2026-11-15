"""ตำแหน่งที่เติมข้อมูลลงแบบฟอร์มทางการ 4 แบบของระบบจองรถ (ค่าคงที่ต่อประเภทใบขอ)

พิกัดเป็น pt บนหน้า A4 (595.32 x 841.92) วัดจากมุมบนซ้าย (เหมือนผล `pdftotext -bbox`)
- `y` ของ Field/Sign คือขอบล่างของบรรทัดที่พิมพ์ในแบบฟอร์ม (bbox yMax) ข้อความจะนั่งเหนือเส้นจุดเล็กน้อย
- ชื่อตัวแปรอ้างค่าใน context ที่ `car_reservation_paper.build_context` สร้างให้
"""

import pathlib
from typing import NamedTuple, Optional, Tuple

PAPERS_DIR = pathlib.Path(__file__).resolve().parent.parent / "web/static/car_papers"
PAGE_W, PAGE_H = 595.32, 841.92


class Field(NamedTuple):
    """ข้อความหนึ่งช่องบนเส้นจุด: x0..x1 คือความกว้างของช่อง"""

    var: str
    x0: float
    x1: float
    y: float
    align: str = "center"
    size: float = 15


class Check(NamedTuple):
    """เครื่องหมายถูกที่วงกลม/วงเล็บ (cx, cy คือจุดกึ่งกลาง) เมื่อค่าของ var ตรงกับ match"""

    var: str
    match: str
    cx: float
    cy: float


class Sign(NamedTuple):
    """พื้นที่ลงนามของหนึ่งขั้นอนุมัติ: ภาพลายเซ็น, ชื่อ, ตำแหน่ง, วันที่ และเครื่องหมายถูก (ถ้ามี)

    image = (x0, x1, y_bottom, height) วางภาพเหนือเส้นลงชื่อ
    name/position/date = (x0, x1, y, align, size)
    """

    image: Optional[Tuple[float, float, float, float]] = None
    name: Optional[Tuple[float, float, float, str, float]] = None
    position: Optional[Tuple[float, float, float, str, float]] = None
    date: Optional[Tuple[float, float, float, str, float]] = None
    date_prefix: bool = False  # ใส่คำว่า "วันที่ " นำหน้าเมื่อแบบฟอร์มไม่มีป้ายวันที่
    date_short: bool = False  # ใช้เดือนแบบย่อเมื่อที่แคบ
    check: Optional[Tuple[float, float]] = None  # (cx, cy) ติ๊กเมื่อขั้นนี้อนุมัติ


class Stamp(NamedTuple):
    """ช่องตราตรวจทานสำหรับขั้นที่แบบฟอร์มไม่มีช่องลงนามให้ (มุมบนซ้ายของตรา และความกว้าง)"""

    x: float
    y: float
    w: float


class Layout(NamedTuple):
    filename: str
    fields: tuple
    checks: tuple
    signs: dict  # step_key -> Sign
    stamps: tuple  # ช่อง Stamp เรียงตามลำดับขั้นของเส้นทางที่ไม่มีช่องลงนาม
    requester_image: Optional[Tuple[float, float, float, float]] = None  # ลายเซ็นผู้ขอใช้รถ


def _check_circle(var, match, x0, x1, y_max):
    """วงกลมของแบบฟอร์ม (กว้าง ~10pt สูง ~17pt) วัดจาก bbox: กึ่งกลางสูงจาก yMax ลงมา 8.6pt"""
    return Check(var, match, (x0 + x1) / 2, y_max - 8.6)


def _check_paren(var, match, left_x, right_x, y_max):
    """วงเล็บ "( )" ของแบบฟอร์ม: กึ่งกลางระหว่างวงเล็บซ้ายและขวา"""
    return Check(var, match, (left_x + right_x) / 2, y_max - 7.2)


# ---------------------------------------------------------------- ในประเทศ

DOMESTIC = Layout(
    filename="domestic.pdf",
    fields=(
        Field("created_day", 372, 402, 117.2),
        Field("created_month", 421, 475, 117.2),
        Field("created_year", 497, 537, 117.2),
        Field("unit", 172, 403, 173.4, "left"),
        Field("phone", 480, 537, 173.4, "left"),
        Field("vehicle_count", 161, 187, 206.9),
        Field("passengers", 247, 278, 206.9),
        Field("location", 372, 537, 206.9, "left"),
        Field("district", 88, 160, 222.7, "left"),
        Field("province", 200, 280, 222.7, "left"),
        Field("request_reason", 322, 537, 222.7, "left"),
        Field("dep_day", 84, 100, 238.5),
        Field("dep_month", 103, 150, 238.5),
        Field("dep_year", 153, 183, 238.5),
        Field("pickup_place", 275, 453, 238.5, "left"),
        Field("pickup_time", 477, 525, 238.5),
        Field("ret_day", 225, 245, 254.4),
        Field("ret_month", 247, 297, 254.4),
        Field("ret_year", 299, 326, 254.4),
        Field("ret_time", 383, 440, 254.4),
        Field("requester_name", 290, 404, 361.2),
        Field("car_plate", 388, 531, 467.9, "left"),
        Field("driver_name", 153, 459, 486.2, "left"),
        Field("extra_travelers", 163, 369, 520.2, "left"),
        Field("km_out", 113, 195, 805.5),
        Field("km_in", 257, 338, 805.5),
        Field("km_total", 393, 430, 805.5),
        Field("trip_cost", 485, 521, 805.5),
    ),
    checks=(
        _check_circle("vehicle_kind", "บัส", 191.0, 201.1, 190.5),
        _check_circle("vehicle_kind", "ตู้", 231.9, 242.0, 190.5),
        _check_circle("vehicle_kind", "เก๋ง", 266.8, 276.9, 190.5),
        _check_circle("vehicle_kind", "มินิบัส", 305.7, 315.8, 190.5),
        _check_circle("cost", "ค่าน้ำมันเชื้อเพลิง", 170.4, 180.6, 312.6),
        _check_circle("cost", "เบี้ยเลี้ยง", 253.5, 263.6, 312.6),
        _check_circle("cost", "ค่าที่พักของพนักงานขับรถ", 304.4, 314.5, 312.6),
        _check_circle("cost", "ไม่รับผิดชอบ", 425.3, 435.4, 312.6),
        _check_circle("car_type", "บัส", 183.2, 193.3, 467.4),
        _check_circle("car_type", "ตู้", 213.7, 223.8, 467.4),
        _check_circle("car_type", "เก๋ง", 241.2, 251.4, 467.4),
        _check_circle("car_type", "มินิบัส", 275.8, 286.0, 467.4),
        _check_circle("route_to_physical_director", "yes", 92.7, 102.8, 670.1),
    ),
    signs={
        "supervisor": Sign(
            image=(300, 420, 385, 22),
            name=(290, 404, 402.7, "center", 15),
            position=(307, 409, 418.5, "center", 14),
            date=(412, 540, 402.7, "left", 12),
            date_prefix=True,
        ),
        "dispatcher": Sign(
            image=(300, 410, 566, 22),
            name=(297, 402, 589.7, "center", 15),
            date=(412, 540, 589.7, "left", 12),
            date_prefix=True,
        ),
        "strategy_head": Sign(
            image=(300, 410, 619, 22),
            name=(298, 403, 637.2, "center", 15),
            date=(412, 540, 637.2, "left", 12),
            date_prefix=True,
        ),
        "physical_director": Sign(
            image=(300, 410, 726, 24),
            date=(402, 540, 749.8, "left", 12),
            date_prefix=True,
            check=(277.8, 685.0),
        ),
    },
    stamps=(Stamp(62, 566, 205),),
    requester_image=(300, 410, 343, 22),
)

# ---------------------------------------------------------------- สนามบิน

AIRPORT = Layout(
    filename="airport.pdf",
    fields=(
        Field("unit", 227, 364, 129.1, "left"),
        Field("phone", 437, 517, 129.1, "left"),
        Field("passengers", 219, 267, 213.9),
        Field("flight_number", 196, 263, 238.9),
        Field("flight_day", 289, 327, 238.9),
        Field("flight_month", 356, 440, 238.9),
        Field("flight_year", 459, 512, 238.9),
        Field("arrival_time", 404, 456, 256.4),
        Field("departure_time", 405, 457, 273.9),
        Field("pickup_place", 205, 411, 305.6, "left"),
        Field("pickup_time", 434, 487, 305.6),
        Field("p1_name", 237, 385, 330.4, "left"),
        Field("p1_phone", 411, 511, 330.4, "left"),
        Field("p2_name", 237, 385, 346.3, "left"),
        Field("p2_phone", 411, 511, 346.3, "left"),
        Field("p3_name", 237, 385, 362.1, "left"),
        Field("p3_phone", 411, 511, 362.1, "left"),
        Field("p4_name", 237, 385, 378.0, "left"),
        Field("p4_phone", 411, 511, 378.0, "left"),
        Field("p5_name", 237, 385, 393.8, "left"),
        Field("p5_phone", 411, 511, 393.8, "left"),
        Field("requester_name", 356, 462, 531.8),
        Field("requester_position", 357, 466, 547.7, "left"),
        Field("created", 369, 467, 563.5),
        Field("car_type_other", 330, 367, 595.6),
        Field("car_plate", 480, 524, 595.6, "left"),
        Field("driver_name", 100, 186, 609.9, "left"),
        Field("km_out", 132, 211, 780.8),
        Field("km_in", 268, 342, 780.8),
        Field("km_total", 397, 421, 780.8),
        Field("trip_cost", 469, 505, 780.8),
    ),
    checks=(
        Check("transfer", "pickup", 256, 163.1),
        Check("transfer", "dropoff", 256, 180.8),
        Check("flight_leg", "arrival", 256, 247.3),
        Check("flight_leg", "departure", 256, 264.8),
        _check_circle("cost", "ค่าน้ำมันเชื้อเพลิง", 225.1, 235.2, 455.3),
        _check_circle("cost", "เบี้ยเลี้ยง", 314.7, 324.8, 455.3),
        _check_circle("cost", "ไม่รับผิดชอบ", 373.6, 383.8, 455.3),
        _check_circle("car_type", "เก๋ง", 195.5, 205.7, 595.1),
        _check_circle("car_type", "ตู้", 237.1, 247.2, 595.1),
        _check_circle("car_type_is_other", "other", 280.8, 290.9, 595.1),
    ),
    signs={
        "dispatcher": Sign(
            image=(350, 460, 648, 24),
            name=(344, 458, 666.7, "center", 15),
            date=(342, 465, 681.0, "center", 15),
        ),
        "strategy_head": Sign(
            image=(350, 460, 719, 24),
            name=(347, 463, 738.0, "center", 15),
            date=(342, 467, 752.2, "center", 15),
        ),
    },
    stamps=(Stamp(80, 650, 220), Stamp(80, 700, 220)),
    requester_image=(355, 457, 514, 22),
)

# ---------------------------------------------------------------- สวัสดิการ

WELFARE = Layout(
    filename="welfare.pdf",
    fields=(
        Field("created", 410, 552, 99.9),
        Field("requester_name", 129, 277, 156.3, "left"),
        Field("unit", 69, 280, 180.1, "left"),
        Field("phone", 302, 386, 180.1, "left"),
        Field("host_name", 305, 552, 203.8, "left"),
        Field("house", 106, 232, 227.4, "left"),
        Field("subdistrict", 262, 336, 227.4, "left"),
        Field("district", 369, 439, 227.4, "left"),
        Field("province", 477, 552, 227.4, "left"),
        Field("pickup_place", 140, 264, 251.2, "left"),
        Field("dep_day", 288, 310, 251.2),
        Field("dep_month", 312, 368, 251.2),
        Field("dep_year", 370, 402, 251.2),
        Field("dep_time", 427, 473, 251.2),
        Field("ret_day", 160, 185, 275.0),
        Field("ret_month", 188, 245, 275.0),
        Field("ret_year", 247, 272, 275.0),
        Field("ret_time", 297, 347, 275.0),
        Field("requester_name", 291, 421, 352.8),
        Field("car_plate", 118, 210, 501.0, "left"),
        Field("driver_name", 258, 415, 501.0, "left"),
        Field("driver_name", 131, 257, 613.8, "left"),
        Field("km_out", 220, 322, 638.0),
        Field("trip_start_time", 388, 438, 638.0),
        Field("km_in", 220, 322, 662.2),
        Field("trip_end_time", 380, 438, 662.2),
        Field("km_total", 168, 227, 686.4),
        Field("trip_hours", 310, 368, 686.4),
        Field("trip_minutes", 398, 440, 686.4),
        Field("trip_cost", 322, 382, 710.5),
    ),
    checks=(
        _check_paren("employee_type", "พนักงานมหาวิทยาลัย", 300.7, 312.0, 156.3),
        _check_paren("employee_type", "ลูกจ้างประจำ", 397.1, 408.4, 156.3),
        _check_paren("employee_type", "พนักงานเงินรายได้", 469.9, 481.3, 156.3),
        _check_paren("vehicle_kind", "บัส", 499.0, 510.6, 180.1),
        _check_paren("vehicle_kind", "ตู้", 531.8, 543.6, 180.1),
        _check_paren("event_type", "อุปสมบท", 91.9, 103.4, 203.8),
        _check_paren("event_type", "มงคลสมรส", 151.2, 162.7, 203.8),
        _check_paren("event_type", "ฌาปนกิจศพ", 217.7, 232.3, 203.8),
        _check_paren("car_type", "บัส", 469.4, 486.9, 482.9),
        _check_paren("car_type", "ตู้", 517.4, 534.7, 482.9),
        Check("route_to_physical_director", "yes", 75.2, 441.2),
    ),
    signs={
        "supervisor": Sign(
            image=(335, 430, 394, 22),
            name=(291, 421, 412.5, "center", 15),
            position=(303, 428, 428.4, "center", 14),
            date=(430, 552, 412.5, "left", 12),
            date_prefix=True,
        ),
        "dispatcher": Sign(
            image=(302, 362, 527, 22),
            name=(365, 430, 529.2, "center", 14),
            date=(495, 552, 529.2, "left", 12),
            date_short=True,
        ),
        "physical_director": Sign(
            image=(302, 362, 555, 22),
            name=(365, 430, 557.4, "center", 14),
            date=(512, 552, 557.4, "left", 12),
            date_short=True,
        ),
    },
    stamps=(Stamp(50, 505, 205), Stamp(50, 537, 205)),
    requester_image=(300, 415, 335, 22),
)

# ---------------------------------------------------------------- ต่างประเทศ

ABROAD = Layout(
    filename="abroad.pdf",
    fields=(
        Field("section", 111, 300, 99.7, "left"),
        Field("document_number", 82, 290, 117.8, "left"),
        Field("created", 322, 450, 117.8),
        Field("unit", 228, 414, 193.7, "left"),
        Field("vehicle_kind", 104, 163, 209.6),
        Field("vehicle_count", 270, 297, 209.6),
        Field("passengers", 374, 402, 209.6),
        Field("city_state", 116, 199, 225.4, "left"),
        Field("country", 239, 320, 225.4, "left"),
        Field("dep_day", 355, 379, 225.4),
        Field("dep_month", 405, 468, 225.4),
        Field("dep_year", 490, 529, 225.4),
        Field("request_reason", 111, 350, 241.3, "left"),
        Field("pickup_place", 438, 528, 241.3, "left"),
        Field("dep_time", 91, 129, 257.1),
        Field("ret_day", 318, 357, 257.1),
        Field("ret_month", 382, 466, 257.1),
        Field("ret_year", 488, 529, 257.1),
        Field("ret_time", 128, 162, 272.8),
        Field("coordinator_name", 202, 353, 272.8, "left"),
        Field("coordinator_phone", 375, 463, 272.8, "left"),
        Field("requester_name", 276, 411, 352.0),
        Field("requester_position", 293, 416, 370.0, "left"),
        Field("car_type", 358, 393, 498.9),
        Field("car_plate", 470, 529, 498.9, "left"),
        Field("driver_name", 150, 337, 514.8, "left"),
        Field("car_plate", 240, 314, 616.5),
        Field("country", 455, 521, 616.5),
        Field("extra_travelers", 153, 296, 632.3, "left"),
        Field("country", 423, 521, 632.3),
    ),
    checks=(),
    signs={
        "supervisor": Sign(
            image=(285, 405, 404, 22),
            name=(276, 413, 424.3, "center", 15),
            position=(287, 415, 442.4, "center", 14),
            date=(422, 540, 424.3, "left", 12),
            date_prefix=True,
        ),
        "dispatcher": Sign(
            image=(285, 405, 573, 22),
            name=(249, 418, 590.0, "center", 14),
            date=(422, 540, 590.0, "left", 12),
            date_prefix=True,
        ),
        "physical_director": Sign(
            image=(285, 385, 680, 24),
            name=(271, 391, 696.5, "center", 14),
            date=(396, 540, 696.5, "left", 12),
            date_prefix=True,
        ),
        "president": Sign(
            image=(275, 385, 744, 24),
            name=(392, 540, 747.6, "left", 13),
            date=(392, 540, 763.0, "left", 12),
            date_prefix=True,
            check=(274.0, 707.6),
        ),
    },
    stamps=(Stamp(72, 322, 172), Stamp(72, 364, 172), Stamp(72, 406, 172)),
    requester_image=(285, 405, 332, 22),
)

LAYOUTS = {
    "domestic": DOMESTIC,
    "airport": AIRPORT,
    "welfare": WELFARE,
    "abroad": ABROAD,
}
