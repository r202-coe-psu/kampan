"""ส่งไฟล์ที่ผู้ใช้อัปโหลดกลับไปให้เบราว์เซอร์ โดยดู mimetype จากเนื้อไฟล์ ไม่เชื่อ content_type ที่ client ส่งมาตอนอัปโหลด

ไฟล์ที่ไม่ใช่ PNG / JPEG / PDF จะถูกส่งเป็น attachment แบบ application/octet-stream
เบราว์เซอร์จึงไม่ render ไฟล์ HTML ที่แอบอ้างเป็นไฟล์ PDF หรือรูปภาพบน origin ของแอป
"""

import io

from flask import send_file

FILE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"%PDF-", "application/pdf"),
)


def sniff_mimetype(data: bytes) -> str | None:
    for magic, mimetype in FILE_SIGNATURES:
        if data.startswith(magic):
            return mimetype
    return None


def send_uploaded_file(stored, download_name: str):
    """stored คือ GridFS proxy ของ FileField / ImageField ที่มีไฟล์อยู่แล้ว"""
    gridout = stored.get()
    gridout.seek(0)
    data = gridout.read()
    mimetype = sniff_mimetype(data)
    response = send_file(
        io.BytesIO(data),
        mimetype=mimetype or "application/octet-stream",
        download_name=download_name,
        as_attachment=mimetype is None,
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
