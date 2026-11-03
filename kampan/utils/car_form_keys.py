"""key ภายในของฟิลด์ custom และขั้นอนุมัติ: สุ่มครั้งเดียวแล้วไม่เปลี่ยน user เห็นแค่ label"""

import re
import secrets
import string

ALPHABET = string.ascii_lowercase + string.digits
FIELD_PREFIX = "f"
STEP_PREFIX = "s"


def is_generated(key, prefix):
    return bool(re.fullmatch(rf"{prefix}_[a-z0-9]{{6}}", key or ""))


def new_key(prefix, taken):
    while True:
        key = f"{prefix}_" + "".join(secrets.choice(ALPHABET) for _ in range(6))
        if key not in taken:
            taken.add(key)
            return key


def rekey_template(template):
    """เปลี่ยน key ของฟิลด์ custom และขั้นที่ยังไม่ใช่รูปแบบสุ่ม พร้อมแก้ placement ให้ตามไป
    คืน (field_map, step_map) ของ key ที่เปลี่ยน"""
    taken = {f.key for f in template.fields} | {s.key for s in template.steps}

    field_map = {}
    for field in template.fields:
        if field.source == "custom" and not is_generated(field.key, FIELD_PREFIX):
            field_map[field.key] = new_key(FIELD_PREFIX, taken)
            field.key = field_map[field.key]

    step_map = {}
    for step in template.steps:
        if not is_generated(step.key, STEP_PREFIX):
            step_map[step.key] = new_key(STEP_PREFIX, taken)
            step.key = step_map[step.key]

    for placement in template.placements:
        placement.variable = _rename_variable(placement.variable, field_map, step_map)
    return field_map, step_map


def _rename_variable(variable, field_map, step_map):
    parts = variable.split(".")
    if len(parts) == 2 and parts[0] == "details" and parts[1].startswith("custom_"):
        old = parts[1][len("custom_") :]
        if old in field_map:
            return f"details.custom_{field_map[old]}"
    if len(parts) == 3 and parts[0] == "approvals" and parts[1] in step_map:
        return f"approvals.{step_map[parts[1]]}.{parts[2]}"
    return variable
