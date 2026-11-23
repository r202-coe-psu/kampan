"""ข้อความ error ภาษาไทยของ WTForms (WTForms ไม่มีคำแปลภาษาไทยมาให้ และโปรเจกต์ไม่ได้ใช้ Babel)

ใช้กับฟอร์มด้วย `ThaiFlaskForm` / `ThaiForm` แทน `FlaskForm` / `Form`
"""

from flask_wtf import FlaskForm
from wtforms import Form

MESSAGES = {
    "This field is required.": "กรุณากรอกข้อมูล",
    "Invalid input.": "ข้อมูลไม่ถูกต้อง",
    "Invalid email address.": "รูปแบบอีเมลไม่ถูกต้อง",
    "Number must be at least %(min)s.": "ต้องเป็นตัวเลขตั้งแต่ %(min)s ขึ้นไป",
    "Number must be at most %(max)s.": "ต้องเป็นตัวเลขไม่เกิน %(max)s",
    "Number must be between %(min)s and %(max)s.": "ต้องเป็นตัวเลข %(min)s ถึง %(max)s",
    "Field must be between %(min)d and %(max)d characters long.": (
        "ต้องยาว %(min)d ถึง %(max)d ตัวอักษร"
    ),
    "Not a valid choice.": "กรุณาเลือกจากรายการ",
    "Invalid Choice: could not coerce.": "กรุณาเลือกจากรายการ",
    "Invalid choice(s): one or more data inputs could not be coerced.": "กรุณาเลือกจากรายการ",
    "Not a valid datetime value.": "วันที่และเวลาไม่ถูกต้อง",
    "Not a valid date value.": "วันที่ไม่ถูกต้อง",
    "Not a valid time value.": "เวลาไม่ถูกต้อง",
    "Not a valid integer value.": "กรุณากรอกเป็นจำนวนเต็ม",
    "Not a valid decimal value.": "กรุณากรอกเป็นตัวเลข",
    "Not a valid float value.": "กรุณากรอกเป็นตัวเลข",
}
# ข้อความที่มีรูปพหูพจน์ ภาษาไทยใช้รูปเดียว: key คือรูปเอกพจน์
PLURAL_MESSAGES = {
    "Field must be at least %(min)d character long.": "ต้องยาวอย่างน้อย %(min)d ตัวอักษร",
    "Field cannot be longer than %(max)d character.": "ยาวได้ไม่เกิน %(max)d ตัวอักษร",
    "Field must be exactly %(max)d character long.": "ต้องยาว %(max)d ตัวอักษรพอดี",
    "'%(value)s' is not a valid choice for this field.": "'%(value)s' ไม่อยู่ในรายการที่เลือกได้",
}


class ThaiTranslations:
    def gettext(self, string):
        return MESSAGES.get(string, string)

    def ngettext(self, singular, plural, n):
        return PLURAL_MESSAGES.get(singular, singular if n == 1 else plural)


TRANSLATIONS = ThaiTranslations()


class ThaiMeta:
    def get_translations(self, form):
        return TRANSLATIONS


class ThaiFlaskForm(FlaskForm):
    class Meta(ThaiMeta):
        pass


class ThaiForm(Form):
    class Meta(ThaiMeta):
        pass
