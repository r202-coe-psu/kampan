from flask_wtf import FlaskForm


class PostActionForm(FlaskForm):
    """ฟอร์มว่างสำหรับปุ่มที่เปลี่ยนสถานะ/ลบข้อมูล: บังคับ POST + CSRF"""
