"""สร้างแบบฟอร์มเปล่า (PDF) ของเอกสารเบิกค่าใช้จ่าย พขร. จากไฟล์ .docx ต้นฉบับของกองกายภาพ

ใช้ครั้งเดียวตอนเตรียมฟอร์ม (ผลลัพธ์ commit ไว้ใน repo แล้ว): ลบค่าตัวอย่างที่พิมพ์ไว้ในต้นฉบับ
(ชื่อ จำนวนเงิน ตัวอักษร ฯลฯ) ติ๊กช่องทั้งหมดให้ว่าง แล้วแปลงเป็น PDF ด้วย LibreOffice
ข้อมูลจริงถูกพิมพ์ทับตอนใช้งานโดย kampan/utils/car_reservation_finance.py

    python scripts/prepare_car_finance_forms.py

ต้องมี `soffice` และฟอนต์ "TH Sarabun New" (ต้นฉบับใช้ TH SarabunPSK ซึ่งหน้าตาเดียวกัน แต่ถ้าไม่มีฟอนต์นั้น
LibreOffice จะใช้ฟอนต์อื่นที่กว้างกว่าจนหน้าล้น) สคริปต์จึงสั่ง fontconfig ให้ใช้ TH Sarabun New แทน
"""

import os
import pathlib
import shutil
import subprocess
import tempfile
import zipfile

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FINANCE_DIR = (
    pathlib.Path(__file__).resolve().parent.parent
    / "kampan/web/static/data/car_reservation_finance"
)

FONTCONFIG = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <include ignore_missing="yes">/etc/fonts/fonts.conf</include>
  <match target="pattern">
    <test qual="any" name="family"><string>TH SarabunPSK</string></test>
    <edit name="family" mode="assign" binding="same"><string>TH Sarabun New</string></edit>
  </match>
</fontconfig>
"""

# ข้อความของ paragraph (รวมทุก run) ที่เป็นค่าตัวอย่างและต้องลบทิ้งให้เหลือช่องว่าง
SAMPLE_PARAGRAPHS = {
    "ชื่อ-สกุล พนักงานขับรถ",
    "นายจิรชัย  ชวดชุม",
    "(บาทถ้วน)",
    "หนึ่งร้อยห้าสิบบาทถ้วน",
    "(หนึ่งร้อยห้าสิบบาทถ้วน)",
    "0.0",
    "0.5",
    "150",
    "380",
    "450",
    "830",
    "ประเภท ก",
    "-",
}
# ค่าตัวอย่างที่แทรกอยู่ในบรรทัดที่มีจุดไข่ปลา (ลบเฉพาะ run นั้น เก็บจุดไว้)
SAMPLE_RUNS = {"แปดร้อยสามสิบบาทถ้วน"}
# ต้นฉบับพิมพ์ "ได้" เกินมาหนึ่ง run หน้าย่อหน้า "ได้ตรวจสอบหลักฐาน..." (หน้า 2) ย่อหน้านี้เยื้องเข้า
# คำที่เกินจึงไปโผล่นอกกรอบตาราง: ลบ run แรกของย่อหน้าที่ขึ้นต้นด้วยข้อความเหล่านี้
STRAY_LEADING_RUNS = {"ได้ตรวจสอบหลักฐานการเบิกจ่ายเงินที่แนบ": "ได้"}
# แถวรายการในใบสำคัญรับเงิน (ลบทิ้ง ระบบพิมพ์ใหม่ตามอัตรา x จำนวนวัน)
SAMPLE_PREFIXES = ("เงินช่วยเหลือค่าอาหาร พขร. (",)

# ต้นฉบับไม่ได้ขึ้นหน้าใหม่ตรงๆ (พึ่งการไหลของข้อความ) บังคับขึ้นหน้าใหม่ที่ "-2-" และ "ใบสำคัญรับเงิน"
# ให้ตำแหน่งที่พิมพ์ทับคงที่ และลดขอบกระดาษเล็กน้อยเพราะคำชี้แจงท้ายหน้า 2 ล้นเมื่อเรนเดอร์ด้วย LibreOffice
WORDS_EXTRA_DOTS = 55
PAGE_BREAK_BEFORE = {"-2-", "ใบสำคัญรับเงิน"}
PAGE_MARGIN_TOP = "700"
PAGE_MARGIN_BOTTOM = "400"

CHECKED_BOX = "F052"  # Wingdings 2
EMPTY_BOX = ("Wingdings", "F0A8")


def paragraph_text(paragraph):
    return "".join(t.text or "" for t in paragraph.iter(W + "t"))


def blank_samples(root):
    for paragraph in root.iter(W + "p"):
        text = paragraph_text(paragraph).strip()
        if text in PAGE_BREAK_BEFORE:
            properties = paragraph.find(W + "pPr")
            properties.insert(0, etree.Element(W + "pageBreakBefore"))
        for rest, stray in STRAY_LEADING_RUNS.items():
            first = next(paragraph.iter(W + "t"), None)
            if first is not None and first.text == stray and text[len(stray):].strip() == rest:
                first.text = ""
        if text in SAMPLE_PARAGRAPHS or text.startswith(SAMPLE_PREFIXES):
            for t in paragraph.iter(W + "t"):
                t.text = ""
    for t in root.iter(W + "t"):
        if (t.text or "").strip() in SAMPLE_RUNS:
            t.text = ""
        elif t.text and t.text.strip().endswith(")") and "..." in t.text:
            # จำนวนเงิน (......) ในใบสำคัญรับเงิน: ต่อจุดไข่ปลาให้ยาวพอใส่จำนวนเงินตัวอักษรที่ยาว
            t.text = "." * WORDS_EXTRA_DOTS + t.text
    for sym in root.iter(W + "sym"):
        if sym.get(W + "char") == CHECKED_BOX:
            sym.set(W + "font", EMPTY_BOX[0])
            sym.set(W + "char", EMPTY_BOX[1])
    for margin in root.iter(W + "pgMar"):
        margin.set(W + "top", PAGE_MARGIN_TOP)
        margin.set(W + "bottom", PAGE_MARGIN_BOTTOM)


def blank_docx(source, target):
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(
        target, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                root = etree.fromstring(data)
                blank_samples(root)
                data = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone=True
                )
            zout.writestr(item, data)


def main():
    sources = {
        "travel_expense": FINANCE_DIR / "source/travel_expense.docx",
        "allowance": FINANCE_DIR / "source/allowance.docx",
    }
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        fontconfig = tmp / "fonts.conf"
        fontconfig.write_text(FONTCONFIG)
        env = {
            **os.environ,
            "FONTCONFIG_FILE": str(fontconfig),
            # โปรไฟล์ LibreOffice แยกต่างหาก กันชนกับ soffice ที่เปิดอยู่
        }
        for name, source in sources.items():
            blank = tmp / f"{name}.docx"
            blank_docx(source, blank)
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp), str(blank)],
                check=True,
                env=env,
                capture_output=True,
            )
            shutil.copy(tmp / f"{name}.pdf", FINANCE_DIR / f"{name}.pdf")
            print("wrote", FINANCE_DIR / f"{name}.pdf")


if __name__ == "__main__":
    main()
