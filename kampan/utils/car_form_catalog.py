from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogField:
    key: str
    default_label: str
    field_type: str
    choices: tuple = ()


CATALOG = {
    field.key: field
    for field in (
        CatalogField(
            "vehicle_kind",
            "ชนิดรถ",
            "radio",
            ("บัส", "ตู้", "เก๋ง", "มินิบัส"),
        ),
        CatalogField("vehicle_count", "จำนวนรถ", "number"),
        CatalogField("district", "อำเภอ", "text"),
        CatalogField("province", "จังหวัด", "text"),
        CatalogField(
            "cost_responsibility",
            "ผู้รับผิดชอบค่าใช้จ่าย",
            "checkbox",
            (
                "ค่าน้ำมันเชื้อเพลิง",
                "เบี้ยเลี้ยง",
                "ค่าที่พักของพนักงานขับรถ",
                "ไม่รับผิดชอบ",
            ),
        ),
    )
}
