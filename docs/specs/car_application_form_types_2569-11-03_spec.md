# Refactor ระบบขอใช้รถ: รองรับฟอร์มหลายประเภทและ template ต่อ organization

## Context

ตอนนี้ระบบขอใช้รถ (`CarApplication`) ผูกอยู่กับฟอร์มเดียวคือ **"ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ"** (DIIS)
- หัวกระดาษเขียนตายตัวไว้ใน `kampan/web/templates/vehicle_lending/car_applications/paper.html:326`
- ประเภทการใช้มีแค่ `USING_TYPE` = general / airport transfer / out of town (`kampan/models/vehicle_applications.py`)
- ฟิลด์เฉพาะ (flight_*, passenger_location) เป็นคอลัมน์ตรงๆ บน model

กองกายภาพและสิ่งแวดล้อมจะเป็น **organization แยกในระบบ** และใช้ฟอร์มของตัวเอง 4 แบบ (ต้นฉบับอยู่ใน `~/Documents/ขอใช้รถ/`) ซึ่งฟิลด์ ข้อความ ผู้ลงนาม และหน้ากระดาษต่างจาก DIIS ทั้งหมด

**เป้าหมาย:** แต่ละ organization เปิดใช้ชุด "ประเภทฟอร์ม" (form type) ของตัวเองได้ ใบพิมพ์ต้องตรงกับต้นฉบับ และปฏิทิน การเช็กรถชน เลขไมล์ ประวัติ และ export ต้องทำงานได้กับทุกฟอร์มโดยไม่ต้องเขียนซ้ำ

---

## 1. ฟอร์มทั้งหมดที่ต้องรองรับ

| key | ฟอร์ม | org | ฟิลด์เฉพาะ (ไปเก็บใน `details`) | ผู้ลงนามบนกระดาษ |
|---|---|---|---|---|
| `diis_general` | DIIS ไปปฏิบัติงานทั่วไป | DIIS | – | ผู้ขอ, หัวหน้าฝ่าย, ผู้ควบคุมยานพาหนะ |
| `diis_airport` | DIIS รับส่งสนามบิน | DIIS | airport_transfer_type, flight_number(s), flight_datetime(s), passenger_location | เหมือนด้านบน |
| `diis_out_of_town` | DIIS ไปต่างจังหวัด | DIIS | – | เหมือนด้านบน + ผอ.สำนักฯ |
| `physical_domestic` | ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ | กองกายภาพ | vehicle_kind (บัส/ตู้/เก๋ง/มินิบัส), vehicle_count, district, province, cost_responsibility[] (น้ำมัน/เบี้ยเลี้ยง/ที่พักคนขับ/ไม่รับผิดชอบ), extra_traveler_approval | ผู้ขอ, ผู้บังคับบัญชา, ผู้จัดรถ, ผู้อนุมัติ, ผอ.กอง |
| `physical_abroad` | บันทึกข้อความ ขอใช้รถยนต์ไปต่างประเทศ | กองกายภาพ | vehicle_kind, vehicle_count, city_state, country, coordinator_name, coordinator_phone, ส่วนงาน/ที่ (เลขหนังสือ) | ผู้ขอ, ผู้บังคับบัญชา, ผู้จัดรถ, ผอ.กอง, **อธิการบดี** |
| `physical_airport` | ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่ | กองกายภาพ | airport_transfer_type, flight_number, flight_date, arrival_time, departure_time, passengers[] {name, phone}, cost_responsibility[] | ผู้ขอ, ผู้จัดรถ, ผู้อนุมัติ |
| `physical_welfare` | ใบขอใช้รถประเภทสวัสดิการบุคลากร | กองกายภาพ | employee_type, vehicle_kind (บัส/ตู้), event_type (อุปสมบท/มงคลสมรส/ฌาปนกิจ), event_owner, house/subdistrict/district/province | ผู้ขอ, ผู้บังคับบัญชา, ผู้จัดรถ, ผู้อนุมัติ, คนขับ (ส่วนรายงาน) |

**ไม่ต้องนับเป็น form type:** `บันทึกการใช้รถยนต์.pdf` เป็นรายงานรายเดือนแยกตามรถ ซึ่งมีอยู่แล้วใน `kampan/repositories/history_car_lending.py` ใช้ต่อได้ตามเดิม

**ทุกฟอร์มของกองกายภาพมีบรรทัดท้ายใบ:** เลข กม. ออก/กลับ, รวมระยะทาง, เป็นเงิน → ดึงจากรายงานคนขับ (ข้อ 5)

---

## 2. สถาปัตยกรรม: ประเภทฟอร์มอยู่ในโค้ด + การตั้งค่าต่อ org อยู่ใน DB

### 2.1 Model (`kampan/models/vehicle_applications.py`)

`CarApplication` ยังอยู่ใน collection เดิม เพิ่มฟิลด์ดังนี้

```python
form_type = me.StringField(required=True, default="diis_general")  # key ใน registry
details   = me.DictField(default=dict)                              # ฟิลด์เฉพาะของแต่ละฟอร์ม
trip_report = me.EmbeddedDocumentField(CarTripReport)               # รายงานคนขับ (ข้อ 5)
```

**ฟิลด์กลางที่ยังเป็นคอลัมน์จริง** (ระบบส่วนอื่นอ่านอยู่): organization, division, creator, phone, location, request_reason, departure_datetime, return_datetime, travel_type, passenger_number, car, driver, status, approvals, last_mileage*

ฟิลด์ `using_type`, `airport_transfer_type`, `flight_*` และ `passenger_location` ยังไม่ลบในรอบนี้ แต่ให้ถือว่า deprecated โค้ดใหม่ต้องอ่านผ่าน `form_type` หรือ `details` เท่านั้น ส่วนการลบจริงทำใน commit สุดท้ายหลังรัน migration แล้ว

### 2.2 Form type registry (package ใหม่ `kampan/vehicle_forms/`)

```
kampan/vehicle_forms/
├─ __init__.py        # REGISTRY: dict[key, FormType], get(key), choices_for(org)
├─ base.py            # @dataclass FormType
├─ diis.py             # diis_general, diis_airport, diis_out_of_town
└─ physical.py        # physical_domestic, physical_abroad, physical_airport, physical_welfare
```

```python
@dataclass(frozen=True)
class FormType:
    key: str
    label: str                      # ชื่อที่แสดงตอนให้ผู้ใช้เลือก
    details_form: type[FlaskForm]   # WTForm ของฟิลด์เฉพาะ (ใช้เป็น FormField/ซ้อน)
    create_partial: str             # template ส่วนกรอกฟิลด์เฉพาะ
    paper_template: str             # template ใบพิมพ์
    requires_director: bool = False # ใช้กับ workflow เดิมไปก่อน (ดูข้อ 4)
    advance_days: int = 0           # เช่น abroad = 10 วันทำการ
```

- ฟิลด์เฉพาะแต่ละชุดเขียนเป็น WTForm class แยก เช่น `AbroadDetailsForm` และ `AirportDetailsForm` ที่ใช้ `FieldList(FormField(PassengerForm))` สำหรับรายชื่อผู้โดยสาร
- ตอนบันทึก: `car_application.details = details_form.data` (ต้องแปลง date/time เป็น ISO string ก่อน)
- ตอนแก้ไข: `details_form = cls(data=car_application.details)`

### 2.3 การตั้งค่าต่อ organization (model ใหม่ `CarFormSetting`)

```python
class CarFormSetting(me.Document):
    meta = {"collection": "car_form_settings", "indexes": ["organization"]}
    organization = me.ReferenceField("Organization", required=True, unique=True)
    enabled_form_types = me.ListField(me.StringField())   # ต้องเป็น key ใน REGISTRY
    default_form_type  = me.StringField()
    signers = me.DictField()   # {"director": {"name": "นายนิติธร ชำนาญเมือง", "position": "ผู้อำนวยการกองกายภาพฯ"}, ...}
    header_text = me.StringField()   # เช่น "งานยุทธศาสตร์และบริการกลาง กองกายภาพและสิ่งแวดล้อม"
    footer_note = me.StringField()
```

- ถ้า org ยังไม่มี setting ให้ fallback เป็น DIIS ทั้ง 3 แบบ ข้อมูลเดิมจึงทำงานได้ทันทีโดยไม่ต้องตั้งค่าอะไร
- เพิ่มหน้าตั้งค่าให้ role `admin` ของ org เลือกเปิดฟอร์มและกรอกชื่อผู้ลงนาม (ใช้ ACL decorator เดิม `acl.organization_roles_required("admin")`)

### 2.4 หน้ากรอก (create_or_edit)

`kampan/web/views/vehicle_lending/car_applications.py:create_or_edit`
1. ถ้ามี `form_type` ใน query string ให้ใช้ค่านั้น ถ้าไม่มีให้ใช้ default ของ org ถ้า org เปิดหลายฟอร์ม ให้แสดงตัวเลือก (radio หรือการ์ด) ก่อนกรอก
2. ฟอร์มหลักใช้ `CarApplicationForm` ตัวเดิม (ฟิลด์กลาง) แล้ว render `form_type.create_partial` ต่อด้านล่างสำหรับฟิลด์เฉพาะ
3. ตรวจว่า `form_type` อยู่ใน `enabled_form_types` ของ org ถ้าไม่อยู่ให้ abort(403) เพื่อกันผู้ใช้ยิงฟอร์มของ org อื่นเข้ามา
4. ถ้า `advance_days` > 0 ให้ validate ว่าวันออกเดินทางต้องห่างจากวันยื่นอย่างน้อยเท่านั้น (ใช้วันทำการหรือวันปฏิทิน: ดู Q4)
5. ดึง logic แปลงฟอร์มเป็น model ออกมาเป็นฟังก์ชัน `apply_form(car_application, form, details_form, form_type)` เพื่อให้ view สั้นลงและเขียน test ได้

### 2.5 ใบพิมพ์ (paper)

- แยก `paper.html` ออกเป็น `car_applications/papers/_base.html` (ปุ่มพิมพ์, CSS A4, ป้ายถูกปฏิเสธ, การตั้ง title ตอนพิมพ์) กับ `papers/diis.html` (ย้ายเนื้อหาเดิม) และ `papers/physical_domestic.html`, `papers/physical_abroad.html`, `papers/physical_airport.html`, `papers/physical_welfare.html`
- `paper()` และ `combine_paper()` ใช้ `{% include form_type.paper_template %}` ทีละใบ ทำให้พิมพ์รวมหลายประเภทในชุดเดียวได้
- ชื่อผู้ลงนาม หัวกระดาษ และหมายเหตุ อ่านจาก `CarFormSetting` ไม่เขียนลงใน template ตายตัว

---

## 3. Migration ข้อมูลเดิม

สคริปต์ `scripts/migrate_car_applications_form_type.py` (ใช้รูปแบบเดียวกับ `scripts/migrate_car_applications_out_of_town.py`) ต้องรันซ้ำได้โดยไม่เพี้ยน (idempotent) และมี `--dry-run`

| using_type เดิม | form_type ใหม่ | ย้ายเข้า details |
|---|---|---|
| general / "" | diis_general | – |
| airport transfer | diis_airport | airport_transfer_type, flight_number, flight_return_number, flight_datetime, flight_return_datetime, passenger_location |
| out of town | diis_out_of_town | – |

---

## 4. Approval workflow (⚠️ ยังไม่ได้ตัดสินใจ: ผู้ใช้ขอแจ้งภายหลัง)

**สถานะปัจจุบัน** (`kampan/web/views/vehicle_lending/car_permissions.py`)
`pending on header` → header_approve → `pending on admin` → admin_approve → ถ้า `using_type == "out of town"` ไป `pending on director` แล้วเป็น `active` ถ้าไม่ใช่ก็เป็น `active` เลย

**ขั้นตอนของกองกายภาพตามกระดาษ:** ผู้บังคับบัญชา → ผู้จัดรถ (เลือกรถและคนขับ) → ผอ.กอง → (เฉพาะต่างประเทศ) อธิการบดี

**ทางเลือกที่รอคำตอบ**
- **4A (เสี่ยงน้อย):** ใช้ 3 สถานะเดิม และ map ชื่อ role ให้ตรงกับกองกายภาพ (header = ผู้บังคับบัญชา, admin = ผู้จัดรถ, director = ผอ.กอง) เปลี่ยนเงื่อนไข `using_type == "out of town"` ที่ `car_permissions.py:470` เป็น `form_type.requires_director` ส่วนขั้นอธิการบดีให้ลงนามบนกระดาษ ไม่ทำในระบบ
- **4B (เต็มรูปแบบ):** ให้แต่ละ form type มี `approval_steps` ของตัวเอง เปลี่ยน status เป็น `pending` + `current_step` และเก็บ `approvals` เป็น ListField งานนี้แตะ `car_permissions.py`, หน้า permission 3 หน้า, `status_badge.html`, `email_utils.py` และ `tests/test_car_applications_workflow.py` (56 จุด)

**ถึงจะยังไม่ได้ตัดสินใจ ก็ทำข้อ 1–3, 5–6 ได้ก่อน** เพราะขั้นที่ 1–7 ด้านล่างไม่เปลี่ยน workflow ยกเว้นการแทน `using_type` ด้วย `requires_director`

---

## 5. รายงานคนขับหลังจบงาน (รวมเข้า car_tasks)

```python
class CarTripReport(me.EmbeddedDocument):
    mileage_out = me.IntField(min_value=0)      # = last_mileage_before ที่มีอยู่
    mileage_in  = me.IntField(min_value=0)      # = last_mileage ที่มีอยู่
    departed_at = me.DateTimeField()
    returned_at = me.DateTimeField()
    expense     = me.DecimalField(precision=2)  # ค่าน้ำมัน + ค่าเสียหายอื่น (เป็นเงิน ใช้ Decimal)
    reported_by = me.ReferenceField("User")
    reported_at = me.DateTimeField()
```

- เพิ่มช่องเวลาออก/กลับและค่าใช้จ่ายในหน้าคนขับ `car_tasks/submit_task_modal.html` และ view `car_tasks.py` ส่วน logic เลขไมล์เดิม (`get_oldest_active_ids` / `get_latest_completed_ids`) ไม่แตะ
- ใบพิมพ์ของกองกายภาพแสดง "เลข กม. ออก/กลับ / รวมระยะทาง / เป็นเงิน" จากข้อมูลนี้ ถ้ายังไม่มีข้อมูลให้เว้นว่างไว้เขียนมือ
- ต้องตัดสินใจว่าจะย้าย `last_mileage` / `last_mileage_before` เข้า `trip_report` เลยหรือไม่ (ดู Q5) ข้อเสนอคือยังไม่ย้ายในรอบนี้ ให้ `trip_report` อ่านค่าผ่าน property ไปก่อน

---

## 6. ไฟล์ที่ต้องแก้หรือสร้าง (ตัวหลัก)

| ไฟล์ | การเปลี่ยนแปลง |
|---|---|
| `kampan/models/vehicle_applications.py` | form_type, details, trip_report, `get_form_type()` |
| `kampan/models/car_form_settings.py` (ใหม่) + `kampan/models/__init__.py` | CarFormSetting |
| `kampan/vehicle_forms/*` (ใหม่) | registry + WTForm ของฟิลด์เฉพาะ |
| `kampan/web/forms/vehicle_applications.py` | ตัดฟิลด์ flight/airport ออกจากฟอร์มหลัก |
| `kampan/web/views/vehicle_lending/car_applications.py` | เลือก form type, apply_form, paper ใช้ registry |
| `kampan/web/views/vehicle_lending/car_permissions.py` | `using_type` → `form_type.requires_director` |
| `kampan/web/views/vehicle_lending/car_tasks.py` + `car_tasks/*.html` | trip report |
| `kampan/web/views/vehicle_lending/car_form_settings.py` (ใหม่) + template | หน้าตั้งค่าของ org |
| `templates/vehicle_lending/car_applications/create_or_edit.html` + `partials/*` | ตัวเลือกฟอร์ม + ส่วนกรอกฟิลด์เฉพาะ |
| `templates/vehicle_lending/car_applications/papers/*` | แยกใบพิมพ์ |
| `event_modal.html`, `index.html`, `history_car_lending/*`, `utils/email_utils.py` | แสดงชื่อ form type แทน using_type |
| `scripts/migrate_car_applications_form_type.py` (ใหม่) | migration |

---

## 7. ลำดับการทำ (micro commits, ไม่มี Co-Authored-By)

1. `feat(vehicle_forms)`: สร้าง registry + FormType + DIIS 3 ตัว (ยังไม่มีโค้ดส่วนไหนเรียกใช้) พร้อม unit test
2. `feat(car_applications)`: เพิ่ม `form_type`/`details` บน model + migration script + test
3. `refactor(car_applications)`: สลับโค้ดที่อ่าน `using_type` (views, permissions, email, templates) ไปอ่าน form_type โดยพฤติกรรมเดิมต้องไม่เปลี่ยน และ test workflow ต้องผ่าน
4. `refactor(car_applications)`: แยก paper.html เป็น `_base` + `diis` (ใบพิมพ์ต้องเหมือนเดิมทุก pixel)
5. `feat(car_form_settings)`: model + หน้าตั้งค่า + fallback เป็น DIIS
6. `feat(car_applications)`: หน้าเลือก form type + partial ของฟิลด์เฉพาะ + ตรวจว่า org เปิดใช้ฟอร์มนั้น
7. `feat(vehicle_forms)`: ฟอร์มกองกายภาพทีละตัว (domestic → airport → welfare → abroad) แต่ละตัวมี details form, partial, paper และ test
8. `feat(car_tasks)`: trip report + แสดงท้ายใบพิมพ์
9. (รอคำตอบข้อ 4) workflow
10. `chore`: ลบฟิลด์ deprecated หลังรัน migration บน production แล้ว

---

## 8. Verification

- **Tests** (`pytest tests/`): ต้องผ่านทั้ง `test_car_applications_workflow.py` และ `test_car_application_email.py` ที่มีอยู่ และเพิ่ม test ดังนี้
  - registry: ทุก key มี template ที่มีไฟล์อยู่จริง และ details_form ต้อง instantiate ได้
  - create: org A ส่ง form_type ที่ไม่ได้เปิดใช้ ต้องได้ 403 และสร้างคำขอข้าม org ไม่ได้ (multi-tenancy)
  - details roundtrip: บันทึกแล้วเปิดแก้ไข ต้องได้ค่าเดิมกลับมา รวมถึงรายชื่อผู้โดยสารที่เป็น list
  - migration: dry-run ไม่แก้ข้อมูล และรันซ้ำแล้วผลเท่าเดิม
  - advance_days: ยื่นต่างประเทศล่วงหน้าน้อยกว่า 10 วัน ต้อง validate ไม่ผ่าน
  - trip report: expense เป็น Decimal และระยะทางรวม = mileage_in − mileage_out
- **Manual** (ใช้ skill `run`): สร้างคำขอทุก form type แล้วเปิด `/paper` เทียบกับ PDF ต้นฉบับใน `~/Documents/ขอใช้รถ/` ด้วย print preview ขนาด A4 ทดสอบ `combine_paper` ที่มีหลายประเภทปนกัน และเช็กว่าปฏิทินกับประวัติยังแสดงคำขอเดิมหลัง migration
- **Migration:** รัน `--dry-run` บน staging ก่อน แล้วเทียบจำนวนเอกสารแยกตาม using_type → form_type

---

## 9. คำถามที่ยังค้าง

- **Q1 (Workflow):** เลือก 4A หรือ 4B? ถ้าเลือก 4B ขั้นอธิการบดีของฟอร์มต่างประเทศต้องอนุมัติในระบบด้วยไหม หรือให้ลงนามบนกระดาษ?
- **Q2:** role ในกองกายภาพตรงกับ role เดิมไหม (head = ผู้บังคับบัญชา, supervisor supplier/admin = ผู้จัดรถ, endorser = ผอ.กอง)? หรือต้องเพิ่ม role ใหม่?
- **Q3:** ผู้บังคับบัญชาของผู้ขอในกองกายภาพเป็นคนในระบบ (มี account) หรือเป็นแค่ชื่อที่ลงนามบนกระดาษ? (ผู้ขออาจมาจากคณะอื่นที่ไม่ได้อยู่ใน org)
- **Q4:** "ล่วงหน้า 10 วันทำการ" ของฟอร์มต่างประเทศ ให้ระบบบล็อกการยื่น หรือแค่แสดงคำเตือน? และต้องนับวันหยุดราชการด้วยไหม (ระบบยังไม่มีปฏิทินวันหยุด)?
- **Q5:** ย้าย `last_mileage` / `last_mileage_before` เข้า `trip_report` ในรอบนี้ หรือเก็บไว้ที่เดิม?
- **Q6:** ฟอร์มกองกายภาพมีประเภทรถ (บัส/ตู้/เก๋ง/มินิบัส) จะเพิ่มฟิลด์ `kind` ให้ model `Car` เพื่อกรองรถตอนจัดรถด้วยไหม?
- **Q7:** ผู้ขอจากคณะอื่น (คนนอก org) ต้องยื่นผ่านระบบได้ไหม? ถ้าได้ จะต้องมี flow รับคำขอสาธารณะหรือ guest account ซึ่งเป็นงานใหญ่แยกต่างหาก
