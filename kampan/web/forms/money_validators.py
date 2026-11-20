from wtforms import ValidationError

from kampan.utils.money import MONEY_PLACES_ERROR, has_money_places


class MoneyPlaces:
    """ปฏิเสธจำนวนเงินที่มีทศนิยมเกิน 2 ตำแหน่ง (ไม่ปัดค่าที่ผู้ใช้กรอกให้เอง)"""

    def __init__(self, message: str | None = None):
        self.message = message or MONEY_PLACES_ERROR

    def __call__(self, form, field):
        if not has_money_places(field.data):
            raise ValidationError(self.message)
