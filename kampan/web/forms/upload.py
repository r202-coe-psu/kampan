from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import SelectField, StringField, validators


class UploadExcelForm(FlaskForm):
    excel_file = FileField(
        "Excel File",
        validators=[
            FileRequired("กรุณาเลือกไฟล์"),
            FileAllowed(["xlsx"], "อนุญาตเฉพาะไฟล์ .xlsx เท่านั้น"),
        ],
    )

    file_type = SelectField(
        "File Type",
        choices=[("mas", "MAS (แหล่งเงิน)"), ("procurement", "Procurement (จัดซื้อจัดจ้าง)")],
        validators=[validators.DataRequired("กรุณาเลือกประเภทไฟล์")],
    )

    description = StringField("คำอธิบาย")
