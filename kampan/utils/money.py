"""Helper กลางสำหรับคำนวณเงินด้วย Decimal

กติกา: ค่าที่ระบบคำนวณเองปัดเป็นทศนิยม 2 ตำแหน่งแบบ banker's rounding
(ROUND_HALF_EVEN) ให้ตรงกับ DecimalField ของ model ส่วน input ของผู้ใช้
ต้องผ่าน validator ที่ปฏิเสธทศนิยมเกิน 2 ตำแหน่ง ไม่ใช้ helper นี้ปัดเงียบ ๆ
"""

import decimal
from collections.abc import Iterable
from decimal import Decimal

MONEY_PLACES = Decimal("0.01")
MONEY_ROUNDING = decimal.ROUND_HALF_EVEN
MONEY_PLACES_ERROR = "จำนวนเงินต้องมีทศนิยมไม่เกิน 2 ตำแหน่ง"


def to_money(value) -> Decimal:
    """แปลงค่าเป็น Decimal ทศนิยม 2 ตำแหน่ง (None/ค่าว่าง เป็น 0)

    แปลงผ่าน str เพื่อไม่ให้ binary noise ของ float ติดมา
    """
    if value is None or value == "":
        return Decimal("0").quantize(MONEY_PLACES)
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(MONEY_PLACES, rounding=MONEY_ROUNDING)


def has_money_places(value) -> bool:
    """True ถ้าค่ามีทศนิยมไม่เกิน 2 ตำแหน่ง (None ถือว่าผ่าน, "1.230" ถือว่า 2 ตำแหน่ง)

    ใช้ตรวจ input ของผู้ใช้ก่อนบันทึก ค่าที่ไม่ผ่านต้องปฏิเสธ ห้ามปัดให้เอง
    """
    if value is None:
        return True
    try:
        if not isinstance(value, Decimal):
            value = Decimal(str(value).strip())
        if not value.is_finite():
            return False
        return value == value.quantize(MONEY_PLACES)
    except decimal.InvalidOperation:
        return False


def money_sum(values: Iterable) -> Decimal:
    """รวมยอดเงินโดยเริ่มจาก Decimal("0") แปลงทุกค่าผ่าน to_money"""
    total = Decimal("0").quantize(MONEY_PLACES)
    for value in values:
        total += to_money(value)
    return total
