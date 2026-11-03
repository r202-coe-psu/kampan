# Changelog: branch `poc-car-application`

> เทียบกับ `main` (merge-base `0c04b743`) · 68 commits (2569-11-03 ถึง 2569-11-04) + งานที่ยังไม่ commit
> 64 ไฟล์, +10,505 / −449 บรรทัด
> เอกสารที่เกี่ยวข้อง:
> - `docs/specs/car_form_templates_poc_2569-11-03_spec.md`: spec หลักของ POC
> - `docs/specs/car_form_templates_migration_2569-11-03.md`: migration log แบบละเอียด (map ฟิลด์/สถานะ, log DB local)
> - `docs/specs/car_form_template_hidden_keys_2569-11-03_spec.md`: ซ่อน internal key
> - `docs/specs/car_application_form_types_2569-11-03_spec.md`: ประเภทฟอร์มและ template ต่อ org

---

## สรุปสั้น

ระบบขอใช้รถเปลี่ยนจาก **flow ตายตัวของ DIIS** (หัวหน้าฝ่าย → พัสดุ → ผอ. + ใบพิมพ์ `paper.html`) เป็น **Car Form Templates**: แต่ละ org สร้างแบบฟอร์มเองได้ (ฟิลด์, ขั้นอนุมัติ, PDF ใบขอใช้รถจริงพร้อมตำแหน่งวางข้อความ) ผู้ใช้ยื่นคำขอผ่าน template และอนุมัติตามขั้นที่ template กำหนด

flow เดิม **ยังไม่ถูกลบ** แต่ซ่อนไว้หลัง flag `CAR_LEGACY_FLOW_ENABLED` (ค่าเริ่มต้น `False`)

---

## 1. ของใหม่ (Added)

### 1.1 Car Form Templates (`/car_form_templates`)
- CRUD template พร้อมตัวสร้างฟิลด์และขั้นอนุมัติ (`car_form_templates.py`, `create_or_edit.html`)
- ฟิลด์มี 2 แบบ: **catalog** (ฟิลด์กลางที่ระบบรู้จัก เช่น `vehicle_kind`) และ **custom** (org กำหนดเอง)
- ตรวจสอบ template: ฟิลด์ catalog, ขั้นอนุมัติ, error เป็นภาษาไทยตามชื่อฟิลด์/ขั้น
- **ซ่อน internal key:** key ของ custom field และขั้นอนุมัติสุ่มเป็น `f_xxxxxx` / `s_xxxxxx` ผู้ใช้เห็นแต่ชื่อไทย (`car_form_keys.py`)
- **คนขับเป็นผู้อนุมัติไม่ได้** ทั้งแบบระบุ role และระบุตัวคน
- **Paper editor:** อัปโหลด PDF ใบขอใช้รถจริง แล้วลากวางกล่องตัวแปรบน PDF, ดูตัวอย่างข้อความขนาดจริง, ปรับขนาดฟอนต์ (`paper_editor.html`)
- อัปโหลด PDF ใหม่ไม่ลบไฟล์เก่า (คำขอเก่าอ้าง snapshot ไฟล์เดิม)

### 1.2 คำขอใช้รถแบบ template (`/car_form_requests`)
| route | ใช้ทำอะไร |
|---|---|
| `/new` | เลือก template |
| `/new/<template_id>` | กรอกคำขอ (WTForms + CSRF, ช่องบังคับมีดอกจันแดง, เหตุผลจำกัด 60 ตัวอักษรให้พอดีบรรทัดในใบ) |
| `/` | รายการคำขอ แยกตาม role, มีช่องค้นหาและจำนวนรวม |
| `/inbox` | **รายการที่ต้องอนุมัติ** (ตาราง + ปุ่มดู), ซ่อนจากคนขับที่มี role อื่นแค่ staff |
| `/<id>` | หน้ารายละเอียด: stepper ขั้นอนุมัติ, audit log, modal อนุมัติ/ไม่อนุมัติ |
| `/<id>/edit` | ผู้ยื่นแก้คำขอได้จนกว่าผู้อนุมัติขั้นแรกจะตัดสิน (บันทึกเป็น audit `edited`) |
| `/<id>/approve`, `/<id>/deny` | อนุมัติ/ไม่อนุมัติขั้นปัจจุบัน |
| `/<id>/paper` | พิมพ์ใบ: เติมค่าลงบน PDF ต้นฉบับตามตำแหน่งที่วางไว้ (`car_form_paper.py`) |

- **จัดรถตามประเภทรถที่ขอ:** ผู้ขอเลือกประเภทรถ (เฉพาะประเภทที่ org มีรถ active) ขั้นจัดรถกรองรถตามประเภท และมีป้ายเตือนเมื่อประเภทที่จัดไม่ตรงกับที่ขอ
- **Audit log** ทุกการยื่น/แก้/อนุมัติ/ปฏิเสธ แสดงเป็นประโยคภาษาไทย (เช่น "เปลี่ยนจาก … เป็น …")
- ยอมรับเฉพาะคนขับที่อยู่ใน org

### 1.3 Seed template (`car_form_seeds.py`, `scripts/seed_car_form_templates_poc.py`)
7 template พร้อมตำแหน่งวางบน PDF ทางการ:
`diis_general`, `diis_airport`, `diis_out_of_town`, `physical_domestic`, `physical_abroad`, `physical_airport`, `physical_welfare`

### 1.4 อื่นๆ
- `Car.vehicle_type` (บัส/ตู้/เก๋ง/มินิบัส) ในฟอร์มและหน้ารายการรถ
- `User.can_approve_car_forms()` สำหรับแสดงเมนู/inbox
- เมนู sidebar ระบบรถลิงก์ไป template, คำขอ, รายการที่ต้องอนุมัติ

---

## 2. เปลี่ยนแปลง (Changed)

- **Car tasks:** ออกแบบใหม่ให้เข้าชุดกับหน้าคำขอ, มีช่องค้นหา, รองรับคำขอจาก template
  - คนขับที่ไม่ใช่ admin เห็นและปิดงานได้เฉพาะงานของตัวเอง
  - งานที่รองานเก่าของรถคันเดียวกัน แสดงวันออกเดินทางและคนขับของงานนั้น แทนการซ่อนปุ่มปิดงาน
- **Refactor:** `CarApplication.get_first_per_car()` คืน trip แรกต่อรถ และ `get_oldest_active_per_car()` สร้างต่อจากมัน
- **UI ให้เข้าชุดกัน (DaisyUI):** ป้ายสถานะแบบสีอ่อน, ตาราง + การ์ดบนมือถือ + `EmptyState` + จำนวนรวม ในหน้า template, car feedback, ประวัติการใช้รถ (ตัวกรองพับได้บนมือถือ)
- **`html-renderer.html`:** แสดง error จาก server, ดอกจันใน textarea, select ทรงมนแบบ DaisyUI, ตัดข้อความยาวใน select

---

## 3. ซ่อนชั่วคราว (Deprecated, ยังไม่ลบ)

เมื่อ `CAR_LEGACY_FLOW_ENABLED` ไม่ใช่ `True`:
- `car_permissions` ทั้ง blueprint (หน้าอนุมัติหัวหน้าฝ่าย / พัสดุ / ผอ.) ตอบ **404**
- `car_applications`: `index`, `create_or_edit`, `delete`, `paper`, `combine_paper` ตอบ **404**
- **ปฏิทินยังใช้ได้** ปุ่ม "เพิ่มคำขอ" พาไป `/car_form_requests/new`
- เมนูใน sidebar และปุ่มในคู่มือของ flow เดิมถูกซ่อน
- test ของ flow เดิมเปิด flag ใน `tests/conftest.py`

เปิดกลับ: ใส่ `CAR_LEGACY_FLOW_ENABLED = True` ในไฟล์ cfg แล้ว restart

---

## 4. Schema (เพิ่มอย่างเดียว deploy ได้โดยไม่ต้อง migrate ก่อน)

| ที่ | สิ่งที่เพิ่ม |
|---|---|
| collection ใหม่ `car_form_templates` | `CarFormTemplate`: fields / steps / placements, ref ไป `paper_file` |
| collection ใหม่ `car_form_paper_files` | `CarFormPaperFile`: PDF เก็บเป็น BinaryField |
| `car_applications` | `form_template` (`None` = คำขอเดิม), `template_snapshot`, `details`, `current_step`, `step_approvals[StepApproval]`, `audit_logs[CarApplicationAuditLog]`, `assigned_vehicle_type` |
| `car_applications.status` | สถานะใหม่ `pending`, `denied` (สถานะเดิมยังอยู่) |
| `car_applications.using_type` | ว่างได้ (คำขอจาก template) |
| `cars` | `vehicle_type` |

---

## 5. งานที่ยังไม่ commit (working tree, 2569-11-04)

- **ปฏิทิน:** `get_car_applications` รวมสถานะ `pending` แล้ว (คำขอจาก template ที่รออนุมัติขึ้นปฏิทิน), สี event ใช้ class `event-success/warning/neutral`
- **Event modal ในปฏิทิน:** แสดง stepper ทั้งคำขอ template และคำขอเดิม (`_legacy_step_progress`: หัวหน้าฝ่าย → พัสดุ → ผอ. เฉพาะไปต่างจังหวัด), ลิงก์ไปหน้ารายละเอียดถ้าเป็นคำขอ template, ตอบ 404 ถ้าไม่พบคำขอ
- **Flash เป็น toast:** component `base/components/flash_messages.html` ใช้ร่วมระหว่างระบบองค์กรกับระบบรถ, เพิ่ม flash ใน cars, car_form_requests, car_form_templates, car_feedback, car_tasks, history_car_lending
- test ใหม่: `tests/test_car_calendar.py`, `tests/test_car_flash_messages.py`

---

## 6. Migration จากระบบรถเดิม (legacy)

รายละเอียดเต็ม (ตาราง map ทุกฟิลด์, log DB local พร้อมวิธีย้อนกลับ) อยู่ใน `docs/specs/car_form_templates_migration_2569-11-03.md` ส่วนนี้เป็นภาพรวมและสถานะล่าสุด

### 6.1 สถานะแต่ละเฟส

| เฟส | สถานะ | หมายเหตุ |
|---|---|---|
| M0 deploy โค้ด POC | ✅ โค้ดพร้อม · ⬜ ยังไม่ deploy | schema เพิ่มอย่างเดียว ไม่แตะข้อมูลเดิม |
| M1 seed template | ✅ seed ลง DB local แล้ว | 7 template ใน org ทดสอบและ org DIIS |
| Rekey template (ซ่อน key) | ✅ รันบน DB local แล้ว (7 template) | `scripts/migrate_car_form_template_keys.py [--dry-run]` |
| Backfill `cars.vehicle_type` | ⬜ | ไม่บังคับ แต่ต้องมีเพื่อกรองรถตามประเภท |
| M2 index | ⬜ | ดูข้อ 6.3 |
| M3 ใช้คู่กัน (pilot) | 🟡 ทดสอบใน DB local | |
| M4 ย้ายคำขอเดิมไปใช้ template | ⬜ ยังไม่มีสคริปต์ | `scripts/migrate_car_applications_to_templates.py` |
| M5 ลบโค้ดและฟิลด์เดิม | ⬜ | หลัง M4 + backup |

### 6.2 ลำดับขั้นตอนต่อ environment (staging ก่อน production)

1. **Backup:** `mongodump --db <db> --collection car_applications --collection cars --collection organization_user_roles`
   (staging ไม่มี NTP นาฬิกาอาจเพี้ยน)
2. **Deploy โค้ด** (M0) โดย `CAR_LEGACY_FLOW_ENABLED` ปิดไว้ หรือเปิดไว้ถ้ายังมีคำขอเดิมค้างอนุมัติ (ดูข้อควรระวัง)
3. **Seed template** ต่อ org:
   ```bash
   .venv/bin/python scripts/seed_car_form_templates_poc.py \
     --organization <org_id> --template <key> --pdf "<path pdf>" [--approver-user <user_id>] [--config <cfg>]
   ```
   PDF ทางการไม่อยู่ใน repo, seed รันซ้ำได้ (ชื่อซ้ำใน org = ข้าม)
4. **Rekey** template ที่สร้างก่อนมี key แบบสุ่ม: `scripts/migrate_car_form_template_keys.py --dry-run` แล้วค่อยรันจริง
5. **ตั้งค่า org:**
   - มีผู้ใช้ role `director` ถ้า template มีขั้น director (ไม่มี = คำขอค้าง)
   - สมาชิกต้องมี `division` (ขั้น head แบบ `same_division`)
   - ผู้อนุมัติทุกคนต้องมี role ใน org (global admin ข้ามไม่ได้)
   - คนขับห้ามเป็นผู้อนุมัติ
6. **Backfill `cars.vehicle_type`** ผ่านหน้าแก้รถ หรือสคริปต์ map ตามทะเบียน (DIIS: `กษ-9318` INNOVA, `บล-5746` WULING ต้องยืนยันประเภทก่อน)
7. **สร้าง index** (M2)
8. **ย้ายคำขอเดิม** (M4) แล้วตรวจผล
9. **ลบโค้ดเดิม** (M5)

### 6.3 Index ที่ต้องสร้าง
- `car_form_templates: {organization: 1, status: 1}`
- `car_applications: {organization: 1, form_template: 1, status: 1, current_step: 1}` (inbox)
- `car_form_paper_files: {organization: 1}`

### 6.4 M4: map คำขอเดิม → template

สคริปต์ต้องมี `--dry-run`, ทำทีละ org, idempotent (ข้ามเอกสารที่มี `form_template` แล้ว)

| `using_type` เดิม | template |
|---|---|
| `general` / `""` | `diis_general` |
| `airport transfer` | `diis_airport` |
| `out of town` | `diis_out_of_town` |

| status เดิม | status ใหม่ | `current_step` |
|---|---|---|
| `pending on header` / `admin` / `director` | `pending` | 0 / 1 / 2 |
| `denied by header` / `admin` / `director` | `denied` | 0 / 1 / 2 |
| `active`, `completed`, `disactive` | คงเดิม | `len(steps)` หรือคงเดิม |

ฟิลด์สนามบิน (`airport_transfer_type`, `flight_*`, `passenger_location`) ย้ายเข้า `details.custom_*`, `header/admin/director_approval` แปลงเป็น `step_approvals`, `template_snapshot` = snapshot ของ template ณ เวลา migrate, `assigned_vehicle_type` = `car.vehicle_type`

**ตรวจหลัง migrate:** จำนวนตามสถานะก่อน/หลังตรงกัน, สุ่มเทียบใบพิมพ์ใหม่กับเดิม 10 ใบ, ปฏิทินและ car tasks ยังแสดงคำขอเดิมครบ

### 6.5 ข้อควรระวัง
- ขณะ flag ปิด **คำขอเดิมที่ค้าง `pending on *` ไม่มีใครอนุมัติต่อได้** จนกว่าจะเปิด flag หรือทำ M4
- template flow **ยังไม่ส่งอีเมล** แจ้งเตือน (flow เดิมส่ง) ต้องทำก่อนเลิกใช้ flow เดิม
- ไฟล์ที่ match `pending on` / `denied by` ในระบบเบิกของ (`approve_orders.py`, `item_orders.py`, procurement) ไม่เกี่ยวกับระบบรถ ห้ามแตะตอน M5

### 6.6 M5: โค้ดเดิมที่ต้องลบหรือแก้
`car_permissions.py` + templates, `car_applications` (`create_or_edit`, `paper`, `combine_paper` → redirect ไป template flow, `combine_paper` ต้องทำใหม่ด้วยการรวม PDF), `CarApplicationForm` ส่วน airport/using_type, `email_utils.py` (อีเมลรายขั้นตาม `template_snapshot.steps`), `car_tasks` / `history_car_lending` / `status_badge` / `car_manuals` ที่อ่าน `using_type` หรือสถานะเดิม, ฟิลด์เดิมใน `CarApplication`, test ของ flow เดิม (`test_car_applications_workflow.py`, `test_car_application_email.py`) ดูตารางเต็มใน migration log ข้อ 5

---

## 7. ยังค้างก่อนใช้งานจริง

ปิดไปแล้วตั้งแต่ migration log ถูกเขียน:
- ~~ปฏิทินไม่แสดงคำขอ `pending`~~ (แก้ใน working tree)
- ~~หลังยื่นคำขอพาไป inbox~~ (ตอนนี้พาไปรายการคำขอ `/car_form_requests/`)
- ~~approve/deny ไม่ตรวจ CSRF~~ (ใช้ WTForms + CSRF แล้ว, `c9704834`)

ยังค้าง:
- [ ] อีเมลแจ้งเตือนรายขั้นและตอน active
- [ ] ตัวแปรเลขไมล์ออก/กลับ, ระยะทาง, ค่าใช้จ่ายท้ายใบ
- [ ] ตัวแปรวันที่อนุมัติแยก วัน/เดือน/ปี
- [ ] ฟอร์ม DIIS สนามบิน แถว "ไปรับ" ยังแสดงตามเงื่อนไขไม่ได้
- [ ] ช่องติ๊กรถ DIIS (INNOVA/WULING) match ป้ายทะเบียนแบบตรงตัว
- [ ] template กองกายภาพบางตัวเก็บชื่อ PDF เป็น `form.pdf`
- [ ] ฟิลด์กลาง (เบอร์โทร, เหตุผล, จำนวนผู้โดยสาร) เลือก บังคับ/ไม่บังคับ/ซ่อน ต่อ template (รอตัดสินใจ)
- [ ] catalog เพิ่ม: `country`, `city_state`, `coordinator`, `passengers[]`, `flight`
- [ ] ขั้น "ผู้อนุมัติ" ใช้ role `endorser` หรือระบุตัวคน (คำถามค้าง)
- [ ] email template เดิม render ด้วย `jinja2.Template` ไม่มี sandbox (ความเสี่ยง SSTI, แยก ticket)
- [ ] test ที่ fail อยู่ก่อนแล้ว (ไม่เกี่ยวกับ branch นี้): `test_inventory_manual_cross_tenant_isolation`, `test_procurement_manual_unauthorized_org`
