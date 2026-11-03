# ซ่อน key ในหน้าสร้าง Car Form Template (user เห็นแค่ชื่อภาษาไทย)

## Context

หน้า `vehicle_lending/car_form_templates/create` ตอนนี้บังคับให้ admin ของ org กรอก **key** (a-z, 0-9, _) ให้ทุกฟิลด์ custom และทุกขั้นอนุมัติ ในหน้าลากวาง PDF ก็แสดงชื่อตัวแปรดิบ เช่น `approvals.head.date` และ `details.custom_purpose` ซึ่งคนทั่วไปไม่เข้าใจ และพิมพ์ภาษาไทยลงไปไม่ได้

เป้าหมายคือ **user ไม่ต้องเห็นหรือกรอก key เลย** กรอกแค่ชื่อฟิลด์และชื่อขั้นเป็นภาษาไทย ส่วน key ให้ระบบจัดการหลังบ้าน

## ทำไมยังต้องมี key ที่คงที่

key ถูกใช้อ้างอิงอยู่ 3 ที่ และ**ห้ามเปลี่ยนหลังสร้าง**
1. ค่าที่ user กรอกในคำขอ เก็บใน `details.<key>` หรือ `details.custom_<key>` (`FormFieldDef.details_key()`)
2. การอนุมัติของแต่ละขั้น เก็บด้วย `step_key` (`kampan/models/vehicle_applications.py:72`)
3. กล่องบน PDF (`PaperPlacement.variable`) อ้างอิงเป็นข้อความ เช่น `details.custom_xxx` และ `approvals.<key>.name`

## การตัดสินใจ

**ใช้ id สุ่มที่สร้างครั้งเดียวตอนเพิ่มฟิลด์หรือขั้น แล้วไม่เปลี่ยนอีก** แยกออกจากชื่อที่แสดง (label) ทั้งหมด

| ทางเลือก | ผล | เหตุผล |
|---|---|---|
| index (0, 1, 2…) | ❌ | ลบหรือสลับลำดับแล้ว index เลื่อน กล่องบน PDF จะไปแสดงค่าของฟิลด์อื่นโดยไม่มี error |
| hash จาก label | ❌ | แก้ชื่อแล้ว key เปลี่ยน กล่องที่วางไว้หลุดหมด |
| ใช้ label ภาษาไทยเป็น key | ❌ | แก้ชื่อแล้วหลุดเหมือนกัน และถ้ามี `.` จะทำให้ path อย่าง `details.x` / `approvals.x.name` พัง |
| **id สุ่ม คงที่** | ✅ | แก้ชื่อหรือย้ายลำดับได้อิสระ ผ่าน regex `^[a-z][a-z0-9_]*$` เดิม จึงไม่ต้องแก้ model |

รูปแบบ id:
- ฟิลด์ custom: `f_` + 6 ตัวอักษรสุ่ม `[a-z0-9]` เช่น `f_k3x9a2` (เก็บใน details เป็น `custom_f_k3x9a2`)
- ขั้นอนุมัติ: `s_` + 6 ตัวอักษรสุ่ม เช่น `s_8h2mq1`
- ฟิลด์ catalog: ใช้ key ของ catalog ตามเดิม (user เลือกจาก dropdown อยู่แล้ว แค่ซ่อน key ไม่ให้เห็น)

**template เดิมจะถูก migrate ให้เป็น key รูปแบบใหม่ด้วย** เพื่อให้ทุก template ใช้รูปแบบเดียวกัน (ดูข้อ 4) ส่วน**คำขอเดิมไม่ต้องแตะ** เพราะทุกจุดที่อ่านคำขอใช้ `template_snapshot` ของคำขอเอง ไม่ได้อ่าน key จาก template ปัจจุบัน

---

## 1. หน้าสร้างและแก้ template (`car_form_templates/create_or_edit.html`)

### 1.1 สร้าง id อัตโนมัติ
- เพิ่ม helper `newKey(prefix)` คืนค่า `prefix + "_" + 6 ตัวอักษรสุ่ม [a-z0-9]` ถ้าสุ่มได้ซ้ำกับ key ที่มีในหน้าแล้วให้สุ่มใหม่
- ปุ่ม "เพิ่มฟิลด์" (บรรทัด ~245): ฟิลด์ใหม่ยังเป็น `source: "catalog"` และ `key: ""` เหมือนเดิม
- เมื่อเปลี่ยน source ของฟิลด์เป็น `custom` และ key ยังว่างหรือเป็น key ของ catalog ให้ตั้ง `f.key = newKey("f")`
- เมื่อเปลี่ยนกลับเป็น `catalog` ให้ล้าง key (`""`) เพื่อให้เลือกจาก dropdown ใหม่
- ปุ่ม "เพิ่มขั้น" (บรรทัด ~249): ตั้ง `key: newKey("s")` ทันที
- **ห้ามสร้าง key ใหม่ให้ฟิลด์หรือขั้นที่มี key อยู่แล้ว** (โหลดจาก template เดิม)

### 1.2 ลบช่องกรอก key ออกจาก UI
- ลบ `textInput("key (a-z, 0-9, _)", ...)` ของฟิลด์ custom (บรรทัด ~176) และของขั้นอนุมัติ (บรรทัด ~211)
- dropdown catalog (บรรทัด ~174) แสดงแค่ `c.label` ไม่ต้องต่อท้าย `(c.key)`
- ช่องชื่อฟิลด์และชื่อขั้นใช้ placeholder ภาษาไทย เช่น "ชื่อฟิลด์ เช่น วัตถุประสงค์" และ "ชื่อขั้น เช่น หัวหน้างานอนุมัติ"

### 1.3 Validation ฝั่ง client (บรรทัด ~253–290)
- ลบการตรวจ `KEY_RE` / `KEY_RULE` ที่แสดงให้ user เห็น
- ฟิลด์ custom: **ต้องกรอกชื่อ** (ตอนนี้เว้นว่างได้ แล้วระบบเอา key มาแสดงแทน)
- เช็คซ้ำด้วย**ชื่อ**แทน key:
  - ฟิลด์: "ฟิลด์ที่ 3: ชื่อ “วัตถุประสงค์” ซ้ำกับฟิลด์ที่ 1" (เทียบแบบ trim แล้ว ใช้ชื่อที่แสดงจริง คือ label หรือ default_label ของ catalog)
  - ขั้น: "ขั้นที่ 2: ชื่อ “หัวหน้างาน” ซ้ำกับขั้นที่ 1"
  - ฟิลด์ catalog ตัวเดียวกันเลือกซ้ำ 2 ครั้ง: "ฟิลด์ที่ 3: เลือก “จำนวนรถ” ซ้ำกับฟิลด์ที่ 1"

### 1.4 ตัวแปรในหน้านี้ (`renderVariables`, บรรทัด ~236)
- แสดงแค่ label ไม่แสดง `details.xxx` / `approvals.xxx`

## 2. ฝั่ง server

### 2.1 `kampan/web/views/vehicle_lending/car_form_templates.py`
- `parse_fields_payload`: ถ้า `source == "custom"` และ key ที่ส่งมาว่าง ให้สร้างด้วย `new_key("f", taken)` ฝั่ง Python (ใช้ `secrets.choice`) กันกรณี request ที่ไม่ผ่านหน้าเว็บ
- `parse_steps_payload`: เหมือนกัน ถ้า key ว่างให้สร้าง `new_key("s", taken)`
- `taken` คือ key ที่มีอยู่แล้วใน payload เดียวกัน เพื่อไม่ให้ชนกัน
- ยังคงเชื่อ key ที่ส่งมาถ้าไม่ว่าง เพราะ template เดิมต้องรักษา key เดิมไว้

### 2.2 `kampan/models/car_form_templates.py`
- คง regex และการเช็ค key ซ้ำไว้เป็น safety net แต่ข้อความ error เปลี่ยนเป็นภาษาที่ user เข้าใจ ไม่พูดถึง key
  - key ผิดรูปแบบ → "ฟิลด์ที่ 2: ข้อมูลภายในไม่ถูกต้อง กรุณาลบแล้วเพิ่มใหม่" (ปกติไม่ควรเกิด เพราะระบบสร้าง key เอง)
- `_field_problems`: ฟิลด์ custom ต้องมี label ("ฟิลด์ที่ 2: ต้องกรอกชื่อฟิลด์")
- เพิ่มการเช็คชื่อซ้ำ (ฟิลด์ด้วยฟิลด์ และขั้นด้วยขั้น) ให้ตรงกับข้อ 1.3
- `KEY_RULE` ไม่ต้องแสดงให้ user อีกต่อไป

## 3. หน้าลากวาง PDF (`car_form_templates/paper_editor.html`)

ทุกจุดที่ตอนนี้แสดงชื่อตัวแปรดิบ ให้เปลี่ยนเป็น label

| จุด | บรรทัด | ตอนนี้ | หลังแก้ |
|---|---|---|---|
| palette ตัวแปร | ~166–169 | label + `v.name` (font-mono) | label อย่างเดียว ลบ `title: v.name` |
| ค้นหาตัวแปร | ~162 | ค้นทั้ง name และ label | ค้นจาก label อย่างเดียว |
| tag บนกล่อง | ~240 | `placement.variable` | `info.label` (+ " = " + ค่าที่ติ๊ก) |
| ข้อความในกล่องตอนปิดตัวอย่าง | ~200 | `placement.variable` | `info.label` |
| panel คุณสมบัติ | ~359 | `label (variable)` | label อย่างเดียว |

- ตัวเลือกของ `approvals.*.decision` ตอนนี้เป็น `approved` / `denied` ให้แสดงเป็น "อนุมัติ" / "ไม่อนุมัติ" ใน dropdown "ติ๊กเมื่อค่าเท่ากับ" (ค่าที่เก็บยังเป็น `approved` / `denied`) ทำได้โดยส่ง choices เป็นคู่ `[value, label]` จาก `paper_variables` ในไฟล์ view (บรรทัด ~382)
- ถ้า label ของตัวแปรสองตัวซ้ำกัน (เช่นฟิลด์ catalog กับ custom ชื่อเดียวกันจาก template เก่า) ให้ต่อท้ายด้วยกลุ่ม เช่น "(ฟิลด์เพิ่มเติม)" แทนการโชว์ key

## 4. Migrate template เดิม

### 4.1 ขอบเขต
| ข้อมูล | migrate ไหม | เหตุผล |
|---|---|---|
| `car_form_templates.fields[].key` (เฉพาะ `source == "custom"`) | ✅ | เช่น `project_no` → `f_k3x9a2` |
| `car_form_templates.steps[].key` | ✅ | เช่น `head` → `s_8h2mq1` |
| `car_form_templates.placements[].variable` | ✅ | ต้องเปลี่ยนตาม key ใหม่ ไม่งั้นกล่องบน PDF หลุด |
| ฟิลด์ catalog (`vehicle_kind`, `province`, …) | ❌ | key มาตรฐานกลางที่ใช้ทำรายงานข้าม org |
| `car_applications` (ทั้ง `template_snapshot`, `details`, `step_approvals.step_key`, `audit_logs.step_key`) | ❌ | ทุกจุดที่อ่าน (`car_form_flow.py`, `car_form_paper.py:253`, `car_form_requests.py:217`) ใช้ snapshot ของคำขอเอง ซึ่ง key ภายใน snapshot สอดคล้องกันอยู่แล้ว คำขอที่ค้างอยู่กลางทางจึงเดินต่อได้ตามปกติ |

### 4.2 ฟังก์ชันกลาง `rekey_template(template)`
วางใน `kampan/models/car_form_templates.py` (หรือ `kampan/utils/car_form_keys.py` คู่กับ `new_key`) และใช้ร่วมกันทั้งสคริปต์ migrate และ seed
1. สร้าง mapping ของฟิลด์ custom และขั้นที่ key **ยังไม่ใช่**รูปแบบใหม่ (`^f_[a-z0-9]{6}$` / `^s_[a-z0-9]{6}$`)
   - ฟิลด์: `old` → `new_key("f", taken)`
   - ขั้น: `old` → `new_key("s", taken)`
2. เปลี่ยน key ใน `fields` และ `steps` ตาม mapping
3. เปลี่ยน `placements[].variable`
   - `details.custom_<old>` → `details.custom_<new>`
   - `approvals.<old>.<part>` → `approvals.<new>.<part>`
   - ตัวแปรอื่น (`app.*`, `org.*`, `details.<catalog>`) ไม่แตะ
4. คืน mapping กลับไป (ใช้ log ในโหมด dry-run)

เรียกซ้ำได้ (idempotent): key ที่เป็นรูปแบบใหม่แล้วจะถูกข้าม

### 4.3 สคริปต์ `scripts/migrate_car_form_template_keys.py`
- รูปแบบเดียวกับ `scripts/migrate_car_applications_out_of_town.py` (มี `--dry-run`)
- วนทุก `CarFormTemplate` (ทุก status รวม `disactive`) → `rekey_template` → `template.save()` ซึ่งจะรัน `clean()` ตรวจว่า placement ทุกกล่องยังชี้ตัวแปรที่มีอยู่
- ถ้า template ไหน validate ไม่ผ่าน ให้ log ชื่อ template กับปัญหาแล้วข้ามไป ไม่หยุดทั้งสคริปต์
- พิมพ์สรุป: จำนวน template ที่เปลี่ยน / ข้าม (เป็นรูปแบบใหม่แล้ว) / error และ mapping ของแต่ละ template
- ก่อนรันจริง: `mongodump --collection car_form_templates` (ตามข้อ 3.1 ของ `car_form_templates_migration_2569-11-03.md`)

### 4.4 Seed (`kampan/utils/car_form_seeds.py`)
- ในโค้ด seed ยังเขียน key อ่านง่าย (`head`, `admin`, `approvals.head.name`) ไว้ตามเดิม เพราะตารางพิกัดกล่องบน PDF ต้องอ่านออก
- ก่อน save template ที่ seed ให้เรียก `rekey_template` เพื่อให้ template ที่ seed ใหม่ได้ key รูปแบบใหม่เหมือนที่สร้างจากหน้าเว็บ

### 4.5 บันทึกใน migration log
เพิ่มแถวในตารางข้อ 1 ของ `docs/specs/car_form_templates_migration_2569-11-03.md`: "Rekey template (ซ่อน key)" พร้อมคำสั่งรันและสถานะ

## 5. Tests

- `rekey_template`: key custom/step เปลี่ยนเป็นรูปแบบใหม่, ฟิลด์ catalog ไม่เปลี่ยน, placement `details.custom_*` และ `approvals.*.*` เปลี่ยนตาม, `app.*` / `org.*` ไม่เปลี่ยน, template ยังผ่าน `clean()`
- `rekey_template` เรียกซ้ำรอบสอง → ไม่มีอะไรเปลี่ยน
- คำขอที่ยื่นก่อน migrate และค้างอยู่ขั้นที่ 2 → อนุมัติต่อได้ และพิมพ์ใบ PDF ได้ค่าครบ
- `parse_fields_payload` / `parse_steps_payload`: key ว่าง → ได้ key รูปแบบ `f_xxxxxx` / `s_xxxxxx` ที่ผ่าน regex และไม่ซ้ำกันใน payload
- key ที่ส่งมา (template เดิม) → คงไว้ตามเดิม
- แก้ label ของฟิลด์หรือขั้นแล้วบันทึก → key ไม่เปลี่ยน และ placement เดิมยังผ่าน `_placement_problems`
- สลับลำดับขั้นแล้วบันทึก → placement `approvals.<key>.*` ยังชี้ขั้นเดิม
- ฟิลด์ custom ไม่มีชื่อ → error "ต้องกรอกชื่อฟิลด์"
- ชื่อฟิลด์ซ้ำ หรือชื่อขั้นซ้ำ → error ภาษาไทยที่ระบุลำดับ
- seed template (`car_form_seeds.py`) ยังผ่าน validation

## 6. ทดสอบในเบราว์เซอร์

ที่ `http://127.0.0.1:8081/vehicle_lending/car_form_templates/create?organization_id=<org>`
1. เพิ่มฟิลด์ custom พิมพ์ชื่อภาษาไทย และเพิ่ม 2 ขั้นอนุมัติ → บันทึกได้โดยไม่ต้องเห็น key
2. เปิดหน้าลากวาง PDF → palette ไม่มี `details.` / `approvals.` ให้เห็น ลากวางแล้วบันทึกได้
3. กลับไปแก้ชื่อฟิลด์และสลับลำดับขั้น → บันทึก → กล่องบน PDF ยังแสดงค่าถูกตัว
4. รัน `scripts/migrate_car_form_template_keys.py --dry-run` แล้วรันจริง → เปิด template DIIS ที่ seed ไว้ → หน้าลากวาง PDF กล่องเดิมยังอยู่ครบและแสดงค่าตัวอย่างถูกตัว
5. เปิดคำขอที่ยื่นก่อน migrate → หน้ารายละเอียดและใบพิมพ์แสดงถูก อนุมัติขั้นถัดไปได้

## นอกขอบเขต
- ไม่ migrate ข้อมูลใน `car_applications`
- ไม่เปลี่ยน key ของ catalog
- ไม่เปลี่ยนโครงสร้าง `details` / `approvals` ในคำขอ
