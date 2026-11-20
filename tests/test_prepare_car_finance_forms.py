"""สคริปต์เตรียมแบบฟอร์มเปล่าของเอกสารเบิก: ลบค่าตัวอย่างและคำที่ต้นฉบับพิมพ์เกิน"""

import importlib.util
import pathlib
import zipfile

from lxml import etree

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "prepare_car_finance_forms", ROOT / "scripts/prepare_car_finance_forms.py"
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)
W = prepare.W


def check_paragraph_text(name):
    with zipfile.ZipFile(prepare.FINANCE_DIR / f"source/{name}.docx") as docx:
        root = etree.fromstring(docx.read("word/document.xml"))
    prepare.blank_samples(root)
    return [
        prepare.paragraph_text(p).strip()
        for p in root.iter(W + "p")
        if "ตรวจสอบหลักฐาน" in prepare.paragraph_text(p)
    ]


def test_the_stray_word_before_the_finance_check_paragraph_is_removed_from_both_forms():
    for name in ("travel_expense", "allowance"):
        assert check_paragraph_text(name) == ["ได้ตรวจสอบหลักฐานการเบิกจ่ายเงินที่แนบ"]
