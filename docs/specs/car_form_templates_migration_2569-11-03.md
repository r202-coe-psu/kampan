# Migration log: ระบบขอใช้รถ → Car Form Templates

> อ้างอิง: `docs/specs/car_form_templates_poc_2569-11-03_spec.md` (ข้อ 11 migration plan, ข้อ 13 PDF overlay)
> Branch: `poc-car-application` (เริ่มจาก `0c04b743`)
> สถานะ ณ 2569-11-03: POC ใช้คู่กับ flow เดิมได้ ยังไม่ได้ลบ flow เดิม (ผู้ใช้ตัดสินใจว่า "ค่อยแก้")

ไฟล์นี้บันทึก **ทุกส่วนที่ต้อง migrate** ก่อนเลิกใช้ flow เดิมของ DIIS (`car_applications` + `car_permissions` + `paper.html`) และสิ่งที่ทำไปแล้วกับ DB local

---

## 1. สรุปสั้น

| เฟส | สถานะ | งาน |
|---|---|---|
| M0 deploy POC (เพิ่มฟิลด์และ collection ใหม่) | ✅ โค้ดพร้อม (ยังไม่ deploy) | ไม่แตะข้อมูลเดิม |
| M1 seed template | ✅ มีสคริปต์ 8 แบบ / ✅ seed ลง DB local แล้ว | ข้อ 4 |
| M2 index | ⬜ ยังไม่ทำ | ข้อ 3.4 |
| M3 ใช้คู่กัน (pilot) | 🟡 กำลังทดสอบใน DB local | — |
| M4 ย้ายข้อมูลคำขอเดิม | ⬜ ยังไม่ทำ (ต้องเขียนสคริปต์) | ข้อ 3.3 |
| M5 ลบโค้ดและฟิลด์เดิม | ⬜ ยังไม่ทำ | ข้อ 5 |
| Backfill ประเภทรถ (`Car.vehicle_type`) | ⬜ ต้องทำก่อนเปิดใช้ | ข้อ 3.2 |

---

## 2. Schema ที่เปลี่ยนแล้วในโค้ด (เพิ่มอย่างเดียว ไม่ต้อง migrate ก่อน deploy)

### 2.1 Collection ใหม่
| collection | model | หมายเหตุ |
|---|---|---|
| `car_form_templates` | `CarFormTemplate` (`kampan/models/car_form_templates.py`) | fields / steps / placements (embedded), `paper_file` ref |
| `car_form_paper_files` | `CarFormPaperFile` | เก็บ PDF เป็น BinaryField, ไม่ลบไฟล์เก่าเมื่ออัปโหลดใหม่ (snapshot ของคำขอเก่าชี้ไฟล์เดิม) |

### 2.2 ฟิลด์ใหม่ใน `car_applications` (`CarApplication`)
| ฟิลด์ | default | ใช้ทำอะไร |
|---|---|---|
| `form_template` | `None` | `None` = คำขอแบบเดิม |
| `template_snapshot` | `{}` | สำเนา fields / steps / paper_file_id / placements ตอนยื่น |
| `details` | `{}` | ค่าฟิลด์ catalog (`details.<key>`) และ custom (`details.custom_<key>`) |
| `current_step` | `0` | ขั้นอนุมัติปัจจุบัน |
| `step_approvals` | `[]` | `StepApproval{step_key, label, decision, decided_by, decided_at, comment}` |
| `assigned_vehicle_type` | `None` | ประเภทรถที่จัดจริง (เทียบกับ `details.vehicle_kind`) |

- **สถานะใหม่:** `pending` และ `denied` (ของเดิม `pending on header/admin/director` และ `denied by header/admin/director` ยังอยู่)
- **`using_type`:** เปิดให้ว่างได้ (`USING_TYPE + [("", "-")]`) สำหรับคำขอจาก template

### 2.3 ฟิลด์ใหม่ใน `cars` (`Car`)
| ฟิลด์ | หมายเหตุ |
|---|---|
| `vehicle_type` | choices จาก `VEHICLE_TYPES` (บัส/ตู้/เก๋ง/มินิบัส) และเป็นแหล่งเดียวของ catalog `vehicle_kind` |

---

## 3. ส่วนที่ต้อง migrate ข้อมูล

### 3.1 ก่อนเริ่ม (ทุก environment)
- [ ] `mongodump --db <db> --collection car_applications --collection cars --collection organization_user_roles`
- [ ] รันบน staging ก่อน production (ระวังนาฬิกา staging ไม่ตรง: ไม่มี NTP)

### 3.2 Backfill ประเภทรถ (`cars.vehicle_type`)
- **ทำไม:** ผู้ขอเลือกได้เฉพาะประเภทที่ org มีรถ active ถ้า org ยังไม่ใส่ประเภทให้รถเลย ระบบจะใช้ตัวเลือกจาก catalog แทน (ไม่ค้าง แต่กรองไม่ได้) และการกรองรถตอนจัดรถต้องใช้ฟิลด์นี้
- **ทำอย่างไร:** admin ของแต่ละ org แก้ในหน้ารถทีละคัน หรือเขียนสคริปต์ map ตามป้ายทะเบียน
- **ตัวอย่าง DIIS:** `กษ-9318` (INNOVA), `บล-5746` (WULING) ต้องยืนยันประเภทกับผู้ใช้ก่อน
- **ไม่บังคับ:** รถที่ไม่มีประเภทยังจัดได้ผ่าน "แสดงรถทุกประเภท"

### 3.3 ย้ายคำขอเดิมไปใช้ template (M4) — สคริปต์ `scripts/migrate_car_applications_to_templates.py` (ยังไม่เขียน)
ต้องมี `--dry-run`, ทำทีละ org, idempotent (ข้ามเอกสารที่มี `form_template` แล้ว)

**map `using_type` → template ของ org (seed key):**
| using_type เดิม | template |
|---|---|
| `general` / `""` | `diis_general` |
| `airport transfer` | `diis_airport` |
| `out of town` | `diis_out_of_town` |

**ย้ายฟิลด์เข้า `details`:**
| ฟิลด์เดิม | `details` |
|---|---|
| `airport_transfer_type` (`dropoff`/`pickup`) | `custom_transfer` (`ส่ง`/`รับ`) |
| `flight_number` / `flight_return_number` | `custom_flight_no` (เลือกตาม transfer) |
| `flight_datetime` / `flight_return_datetime` | `custom_flight_time` (`HH:MM`) |
| `passenger_location` | `custom_pickup` |

**map สถานะ:**
| status เดิม | status ใหม่ | current_step | step_approvals สร้างจาก |
|---|---|---|---|
| `pending on header` | `pending` | 0 | — |
| `pending on admin` | `pending` | 1 | `header_approval` → `head` |
| `pending on director` | `pending` | 2 | `header_approval`, `admin_approval` |
| `active` / `completed` | คงเดิม | `len(steps)` | approvals เดิมที่มี |
| `disactive` | คงเดิม | คงเดิม | approvals เดิมที่มี |
| `denied by header` | `denied` | 0 | `head` = denied, comment = `denied_reason` |
| `denied by admin` | `denied` | 1 | `head` approved + `admin` denied |
| `denied by director` | `denied` | 2 | `head`, `admin` approved + `director` denied |

**อื่นๆ ต่อเอกสาร:**
- `template_snapshot` = snapshot ของ template DIIS ใน org นั้น ณ เวลาที่ migrate
- `assigned_vehicle_type` = `car.vehicle_type` ถ้ามีรถ

**ตรวจหลัง migrate:**
- จำนวนเอกสารแยกตามสถานะ ก่อน/หลังต้องตรงกัน (pending* รวมกัน, denied* รวมกัน)
- สุ่ม `/car_form_requests/<id>/paper` 10 ใบเทียบกับ `/car_applications/<id>/paper` เดิม
- ปฏิทินและ car_tasks ยังแสดงคำขอเดิมครบ

### 3.4 Index (M2)
- [ ] `car_form_templates: {organization: 1, status: 1}`
- [ ] `car_applications: {organization: 1, form_template: 1, status: 1, current_step: 1}` (หน้า inbox)
- [ ] `car_form_paper_files: {organization: 1}`

### 3.5 ตั้งค่า org (ทำครั้งเดียวต่อ org)
- [ ] seed template ด้วย PDF (ข้อ 4)
- [ ] มีผู้ใช้ role **`director`** ถ้า template มีขั้น director (ไม่มี = คำขอค้าง)
- [ ] ขั้น "ผู้อนุมัติ" ตอนนี้ใช้ role `endorser` (ยังเป็นคำถามค้าง) หรือแก้เป็นระบุตัวคนในหน้า template
- [ ] สมาชิกต้องมี `division` เพราะขั้น head แบบ `same_division` ต้องใช้ฝ่ายตรงกัน
- [ ] ผู้ใช้ทุกคนที่ต้องอนุมัติต้องมี role ใน org นั้น (`can_act` ไม่ให้ global admin ข้าม)

---

## 4. Seed ที่มี (คำสั่ง)

```bash
.venv/bin/python scripts/seed_car_form_templates_poc.py \
  --organization <org_id> --template <key> --pdf "<path pdf>" [--approver-user <user_id>] [--config <cfg>]
```

| key | template | PDF ต้นฉบับ (`~/Documents/ขอใช้รถ/`) | กล่อง |
|---|---|---|---|
| `diis_general` | ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลฯ (ทั่วไป) | `ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ.pdf` (export จาก paper.html เดิม) | ✅ |
| `diis_airport` | … (รับ-ส่งสนามบิน) | ไฟล์เดียวกัน | ✅ (แถว "รับ" ยังไม่วาง) |
| `diis_out_of_town` | … (ไปต่างจังหวัด) | ไฟล์เดียวกัน | ✅ |
| `physical_domestic` | ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ | `ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ.pdf` | 34 |
| `physical_abroad` | ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ | `ขอใช้รถยนต์พร้อมพนักงานขับรถไปปฏิบัติงานต่างประเทศ.pdf` | 36 |
| `physical_airport` | ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่ | `ใบขอใช้รถ รับ-ส่ง สนามบินหาดใหญ่.pdf` | 39 |
| `physical_welfare` | ใบขอใช้รถประเภทสวัสดิการบุคลากร | `แบบฟอร์มขอใช้รถหน่วยยานพาหนะ.pdf` | 38 |

- Seed เป็น idempotent: ถ้าชื่อซ้ำใน org นั้นแล้ว จะคืนตัวเดิมโดยไม่เปลี่ยนอะไร
- PDF ทางการไม่ได้อยู่ใน repo ต้องส่ง path เข้า `--pdf` เอง

---

## 5. โค้ดเดิมที่ต้องแก้หรือลบใน M5 (หลังย้ายข้อมูลแล้ว)

> **ซ่อนไว้แล้วชั่วคราว (ยังไม่ลบ):** หน้า `car_permissions` ทั้งหมด (หัวหน้าฝ่าย / ผอ. / พัสดุอนุมัติ) และหน้ายื่น/แก้/ลบ/พิมพ์คำขอแบบเดิมใน `car_applications` (`index`, `create_or_edit`, `delete`, `paper`, `combine_paper`) ตอบ 404 ส่วนปฏิทินยังใช้ได้และปุ่ม "เพิ่มคำขอ" ในปฏิทินพาไป `/car_form_requests/new` และเมนูใน sidebar กับปุ่มในคู่มือถูกซ่อน เมื่อ `CAR_LEGACY_FLOW_ENABLED` ไม่ได้ตั้งเป็น `True` (ค่าเริ่มต้นคือปิด) ถ้าต้องการเปิดกลับมา ให้ใส่ `CAR_LEGACY_FLOW_ENABLED = True` ในไฟล์ cfg แล้ว restart โดย test ของ flow เดิมเปิด flag นี้ใน `tests/conftest.py`
> **ข้อควรระวัง:** คำขอเดิมที่ค้าง `pending on header/admin/director` จะไม่มีใครอนุมัติต่อได้จนกว่าจะเปิด flag หรือ migrate (M4)

| ไฟล์ | ใช้ของเดิมอะไรอยู่ | ทำอะไร |
|---|---|---|
| `kampan/web/views/vehicle_lending/car_permissions.py` + `car_permissions/{header,admin,director}_page.html` | flow 3 ขั้นแบบตายตัว | ลบ แทนด้วย `/car_form_requests/inbox` |
| `kampan/web/views/vehicle_lending/car_applications.py` (`create_or_edit`, `paper`, `combine_paper`) | ฟอร์มเดิม + `paper.html` | redirect ไป `/car_form_requests/new` และ `/car_form_requests/<id>/paper`; `combine_paper` ต้องทำใหม่ด้วยการรวม PDF |
| `car_applications.py: get_car_applications` (ปฏิทิน) | `status__in` มีแต่ `pending on *` | **ต้องเพิ่ม `pending`** ไม่อย่างนั้นคำขอจาก template ที่รออนุมัติไม่ขึ้นปฏิทิน (ปัญหาที่รู้แล้ว) |
| `car_applications/index.html`, `components/event_modal.html` | `using_type`, สถานะเดิม | แสดงชื่อ template แทน `using_type` |
| `car_applications/create_or_edit.html`, `paper.html` | ฟอร์มและใบพิมพ์เดิม | ลบ |
| `kampan/web/forms/vehicle_applications.py` (`CarApplicationForm`) | `using_type`, airport fields | ลบส่วน airport/using_type |
| `kampan/utils/email_utils.py` | แยกข้อความตาม `pending on header/admin/director` | ทำอีเมลรายขั้นตาม `template_snapshot.steps` (ตอนนี้ template flow ยังไม่ส่งอีเมล) |
| `car_tasks/index.html` | อ่าน `using_type` | อ่านจาก template |
| `history_car_lending/detail.html`, `kampan/repositories/history_car_lending.py` | `using_type`, approvals เดิม | อ่าน `step_approvals` |
| `components/status_badge.html` | สถานะทั้งสองชุด | ลบชุดเก่า |
| `car_manuals/index.html` | อธิบาย flow เดิม | เขียนคู่มือใหม่ |
| `kampan/models/vehicle_applications.py` | `using_type`, `travel_type`, `airport_transfer_type`, `flight_*`, `passenger_location`, `header/admin/director_approval`, สถานะเดิม | ลบหลัง M4 + มี backup |
| `scripts/migrate_car_applications_out_of_town.py` | สคริปต์ migrate รอบก่อน | เก็บไว้หรือลบ |
| `tests/test_car_applications_workflow.py`, `tests/test_car_application_email.py` | flow เดิม | เขียนใหม่บน template flow |

> `approve_orders.py`, `item_orders.py`, `inventories/manual.html`, `procurement/...` ก็ match คำค้น `pending on`/`denied by` แต่เป็นระบบเบิกของ ไม่เกี่ยวกับระบบขอใช้รถ ห้ามแตะ

---

## 6. ที่ยังไม่ได้ทำและต้องทำก่อนใช้จริง

- [ ] **ปฏิทิน:** เพิ่ม `pending` ใน `get_car_applications`
- [ ] **อีเมล:** แจ้งเตือนรายขั้นและตอน active (ตอนนี้ template flow ยังไม่ส่งอีเมล)
- [ ] **หน้า "คำขอของฉัน":** หลังยื่นคำขอระบบพาไปหน้า inbox ซึ่งไม่แสดงคำขอของตัวเอง
- [ ] **CSRF:** approve/deny ยังไม่ตรวจ CSRF ฝั่ง server (ไม่มี CSRFProtect แบบ global)
- [ ] **ตัวแปรเลขไมล์และค่าใช้จ่าย:** เลข กม. ออก/กลับ, ระยะทาง และค่าใช้จ่ายท้ายใบยังไม่มีตัวแปร (มีข้อมูลอยู่แล้วใน car_tasks)
- [ ] **ตัวแปรวันที่อนุมัติแยกส่วน:** `approvals.<step>.date` เป็นข้อความเดียว ยังไม่มีตัวแปรแยก วัน/เดือน/ปี
- [ ] **ฟอร์ม DIIS สนามบิน แถว "ไปรับ":** placement ยังเลือกแสดงตามเงื่อนไขไม่ได้
- [ ] **ช่องติ๊กรถของ DIIS (INNOVA/WULING):** match ป้ายทะเบียนแบบตรงตัว
- [ ] **ชื่อไฟล์ PDF จาก seed:** template กองกายภาพบางตัวยังเก็บชื่อไฟล์เป็น `form.pdf`
- [ ] **ฟิลด์กลางแบบปรับได้ต่อ template:** เบอร์โทร, เหตุผล และจำนวนผู้โดยสาร ให้เลือก "บังคับ/ไม่บังคับ/ซ่อน" ได้ (รอตัดสินใจ)
- [ ] **catalog เพิ่ม:** `country`, `city_state`, `coordinator`, `passengers[]`, `flight` (ตอนนี้ใช้ custom)
- [ ] **email template เดิม:** render ด้วย `jinja2.Template` แบบไม่มี sandbox (ความเสี่ยง SSTI เดิม แยก ticket)
- [ ] **test ที่ fail อยู่ก่อนแล้ว 2 ตัว** (ไม่เกี่ยวกับงานนี้): `test_inventory_manual_cross_tenant_isolation`, `test_procurement_manual_unauthorized_org`

---

## 7. Log การเปลี่ยนแปลงใน DB local (`kampandb`, 2569-11-03)

| เวลา | ทำอะไร | id / ผล | ย้อนกลับ |
|---|---|---|---|
| 16:5x | template ต่างประเทศ `6ae9a83c499c7c2b1ac71815` (org องค์กรทดสอบ): เปลี่ยน PDF จากภายในประเทศเป็นต่างประเทศ (`CarFormPaperFile` ใหม่) + วาง 36 กล่อง แทน 1 กล่องเดิม | PDF เดิม `6ae9ac8693d38beeb5e15195` ยังอยู่ | backup: `/tmp/claude-1000/-home-saktanuthpeak-kampan/4194d205-2156-4cb1-bf07-cd026255c87b/scratchpad/live/backup_6ae9a83c.json` |
| 17:0x | seed `physical_domestic`, `physical_airport`, `physical_welfare` ลง org องค์กรทดสอบ (`6adeb31c4d4c9988f84258bc`) | `6ae9b249dc623d495b29d185`, `6ae9b24b45b8c293c0b607fc`, `6ae9b24c9f0259f70304feb3` | ลบ 3 template + paper file ของแต่ละตัว |
| 17:2x | สร้าง org **สำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ** + ฝ่าย "ฝ่ายพัฒนาระบบ" + สมาชิก Kontuch (role เดิม + **director**), Saktanuth (admin, head, staff) | org `6ae9b5d337dc21a615d8c49e` | ลบ org, division และ organization_user_roles ของ org นี้ |
| 17:2x | seed `diis_general`, `diis_airport`, `diis_out_of_town` ลง org DIIS | `6ae9b5d516bf83a7359bf7b2`, `6ae9b5d863971a7596d619dc`, `6ae9b5da9c413ea08fa3c61e` | ลบ 3 template + paper file |

**สิ่งที่ยังไม่ได้ทำใน DB local:**
- org DIIS ยังไม่มีรถ ต้องเพิ่มรถก่อน เพราะขั้นจัดรถต้องเลือกรถของ org
- org องค์กรทดสอบยังไม่มีใครมี role `director`
- คำขอแบบเดิม 1 รายการในองค์กรทดสอบยังอยู่ ไม่ได้ลบตามที่ผู้ใช้สั่ง ("ค่อยแก้")
