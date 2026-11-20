import datetime
import re

MONTHS_TH = [
    "",
    "มกราคม",
    "กุมภาพันธ์",
    "มีนาคม",
    "เมษายน",
    "พฤษภาคม",
    "มิถุนายน",
    "กรกฎาคม",
    "สิงหาคม",
    "กันยายน",
    "ตุลาคม",
    "พฤศจิกายน",
    "ธันวาคม",
]


def format_date_th(date_str):
    """
    Receives date string in 'YYYY-MM-DD' format
    and returns 'D Month YYYY' in Thai (Buddhist Era).
    Example: '2024-03-08' -> '8 มีนาคม 2567'
    """
    if not date_str:
        return "-"

    try:
        # Parse the input string
        if isinstance(date_str, str):
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        else:
            dt = date_str

        day = dt.day
        month = MONTHS_TH[dt.month]
        year_be = dt.year + 543

        return f"{day} {month} {year_be}"
    except Exception as e:
        print(f"Error formatting Thai date: {e}")
        return date_str


BUDDHIST_YEAR_OFFSET = 543
_THAI_DATE_PATTERN = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")


def parse_thai_date(text: str) -> datetime.date:
    """แปลงข้อความ ``D/M/YYYY`` หรือ ``DD/MM/YYYY`` ปี พ.ศ. เป็น ``datetime.date`` (ค.ศ.)

    ปีที่น้อยกว่า 2400 ถือว่าผิดรูปแบบ (กันกรอกปี ค.ศ.) วันที่ที่ไม่มีจริง เช่น 30/02/2570 raise ValueError
    """
    match = _THAI_DATE_PATTERN.match((text or "").strip())
    if not match:
        raise ValueError("รูปแบบวันที่ต้องเป็น วว/ดด/ปปปป (พ.ศ.)")
    day, month, year = (int(part) for part in match.groups())
    if year < 2400:
        raise ValueError("กรุณากรอกปีเป็น พ.ศ.")
    try:
        return datetime.date(year - BUDDHIST_YEAR_OFFSET, month, day)
    except ValueError:
        raise ValueError("ไม่มีวันที่นี้ในปฏิทิน")


def format_thai_date_input(value) -> str:
    """วันที่เป็นข้อความ ``DD/MM/YYYY`` ปี พ.ศ. สำหรับแสดงกลับในช่องกรอก (คู่กับ parse_thai_date)"""
    if not value:
        return ""
    return f"{value.day:02d}/{value.month:02d}/{value.year + BUDDHIST_YEAR_OFFSET}"
