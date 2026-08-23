# คู่มือและคำสั่งสำหรับการแคปภาพหน้าจอส่งมอบงาน (Handover Screenshot Capture Guide)

เอกสารฉบับนี้เป็นข้อกำหนดและคู่มือปฏิบัติการ (Automation/Manual Instructions) สำหรับการเปิดหน้าเว็บ Kampan เพื่อแคปภาพหน้าจอในแต่ละวัน (**Day 18 ถึง Day 37**) และนำไปบันทึกไว้ในโฟลเดอร์ `docs/images/handover/` เพื่อให้แสดงผลใน [WORK_DO_HANDOVER_REPORT_DETAILED.md](file:///f:/lab/kampan/WORK_DO_HANDOVER_REPORT_DETAILED.md) โดยอัตโนมัติ

---

## 🎯 ข้อมูลโฟลเดอร์ปลายทาง (Target Destination)

- **โฟลเดอร์สำหรับเก็บภาพทั้งหมด:** `docs/images/handover/`
- **ฟอร์แมตไฟล์ภาพ:** `.png`
- **ความละเอียดที่แนะนำ:** 1280x720 หรือ 1920x1080 (Landscape 16:9)

---

## 🤖 Prompt สำหรับสั่ง AI Subagent (Ready-to-use Prompt)

> ให้นำข้อความในกรอบนี้ไปสั่ง AI Browser Subagent หรือรันผ่านสคริปต์ Automation:

```text
คุณคือ UI QA Automation Agent โปรดเปิด Web Application Kampan ที่ Base URL: http://127.0.0.1:8081 (หรือ Staging URL ที่กำหนด) ทำการล็อกอิน และนำทางไปยัง Route/หน้าระบบตามตารางด้านล่างเพื่อทำการ Capture หน้าจอและบันทึกลงในโฟลเดอร์ "docs/images/handover/" ตามชื่อไฟล์ที่กำหนดให้ครบถ้วนตั้งแต่ Day 18 ถึง Day 37
```

---

## 📋 รายการหน้าจอและเส้นทาง URL ที่ต้องแคป (Day 18 – Day 37)

### 🔹 หมวด Feature D: ระบบงบประมาณ MAS และ Excel (Day 18 – 22)

|   วันที่   | ชื่อไฟล์เป้าหมาย                     | URL Route / หน้าจอในระบบ                             | สิ่งที่ต้องแสดงในภาพหน้าจอ                                                                    |
| :--------: | :----------------------------------- | :--------------------------------------------------- | :-------------------------------------------------------------------------------------------- |
| **Day 18** | `day18_mas_upload_form.png`          | `/admin/mas/create` หรือ `/procurement/upload_files` | หน้าฟอร์มบันทึกข้อมูล MAS ที่มีฟิลด์ปีงบประมาณ (`year`) และส่วนอัปโหลดไฟล์ Excel              |
| **Day 19** | `day19_mas_export_modal.png`         | `/admin/mas` ➔ กดปุ่ม _"ส่งออก Excel"_               | หน้าต่าง Modal ส่งออก Excel งบประมาณ MAS ที่มีปุ่มยืนยันการดาวน์โหลด                          |
| **Day 20** | `day20_excel_styled_output.png`      | เปิดไฟล์ Excel ที่ดาวน์โหลดจากระบบ                   | ตารางรายงาน Excel ที่มีเส้นขอบ (Borders), สีหัวตาราง, การแปลงวันที่ พ.ศ. และยอดรวมเงิน        |
| **Day 21** | `day21_mas_reservation_subtable.png` | `/admin/mas/reservations`                            | ตารางการจองงบประมาณที่กดขยายแสดง Sub-table รายการขอซื้อ/ขอจ้างที่ผูกกับงบ MAS                 |
| **Day 22** | `day22_mas_search_and_ledger.png`    | `/admin/mas`                                         | หน้าตาราง MAS Index ที่มีแถบค้นหาหลายเงื่อนไข (ปี, รหัส, คำอธิบาย, จำนวนเงิน) และ Badge สถานะ |

---

### 🔹 หมวด Feature E: ระบบจัดซื้อพื้นฐานและตัวกรอง (Day 23 – 25)

|   วันที่   | ชื่อไฟล์เป้าหมาย                     | URL Route / หน้าจอในระบบ                      | สิ่งที่ต้องแสดงในภาพหน้าจอ                                                                          |
| :--------: | :----------------------------------- | :-------------------------------------------- | :-------------------------------------------------------------------------------------------------- |
| **Day 23** | `day23_item_comments_and_status.png` | `/procurement/requisitions/renewal_requested` | ตารางรายการคำขอที่แสดง Comment ในแต่ละแถว และ Badge สถานะการอนุมัติแยกตาม Role                      |
| **Day 24** | `day24_multi_search_catalog.png`     | `/procurement/products`                       | ฟอร์มค้นหาพัสดุหลายมิติ (ชื่อสินค้า, รหัสสินค้า, หมายเลขครุภัณฑ์) พร้อมปุ่ม Action นำทาง            |
| **Day 25** | `day25_only_me_sidebar.png`          | `/procurement/requisitions`                   | หน้าต่างที่มีสวิตช์ฟิลเตอร์ _"Only Me"_ (เฉพาะของฉัน) และแถบเมนู Sidebar ด้านข้างที่จัดหมวดหมู่ใหม่ |

---

### 🔹 หมวด Feature F: ระบบ Background Worker และอีเมล (Day 26)

|   วันที่   | ชื่อไฟล์เป้าหมาย            | URL Route / หน้าจอในระบบ                  | สิ่งที่ต้องแสดงในภาพหน้าจอ                                                                         |
| :--------: | :-------------------------- | :---------------------------------------- | :------------------------------------------------------------------------------------------------- |
| **Day 26** | `day26_worker_mail_log.png` | ตัวอย่าง Email Inbox หรือ Terminal Worker | ตัวอย่างอีเมลแจ้งเตือนการอนุมัติ/ปฏิเสธคำขอ หรือหน้าต่าง Terminal ที่แสดง Log การรัน Worker คิวงาน |

---

### 🔹 หมวด Feature G: ระบบขอใช้รถและพิมพ์เอกสารราชการ (Day 27 – 31)

|   วันที่   | ชื่อไฟล์เป้าหมาย                       | URL Route / หน้าจอในระบบ                                                      | สิ่งที่ต้องแสดงในภาพหน้าจอ                                                                     |
| :--------: | :------------------------------------- | :---------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------- |
| **Day 27** | `day27_car_approval_workflow.png`      | `/vehicle_lending/history_car_lending` หรือ `/vehicle_lending/car_applications` | หน้าจอแสดงขั้นตอนการอนุมัติคำขอใช้รถยนต์ พร้อมประวัติการลงนามของแต่ละระดับ Role                |
| **Day 28** | `day28_combine_paper_batch.png`        | `/vehicle_lending/car_applications/combine_paper`                             | หน้ารวมชุดเอกสารขอใช้รถต่อเนื่องสำหรับสั่งพิมพ์ล็อตใหญ่ (Batch Print Layout)                   |
| **Day 29** | `day29_printable_paper_signatures.png` | `/vehicle_lending/car_applications/<id>/paper`                               | หน้าพรีวิวเอกสารขอใช้รถสำหรับสั่งพิมพ์ พร้อมช่องลงนาม 3 ฝ่าย (ผู้ขอ, พนักงานขับรถ, ผู้อนุมัติ) |
| **Day 30** | `day30_lending_export_sign.png`        | `/vehicle_lending/history_car_lending` (เปิด Modal ส่งออก)                   | รายงานประวัติการใช้รถยนต์ที่มีส่วนสำหรับลงลายมือชื่อ                                           |
| **Day 31** | `day31_calendar_and_car_modal.png`     | `/vehicle_lending/car_applications/calendar`                                | หน้าระบบปฏิทินแสดงตารางการใช้รถ พร้อมหน้าต่าง Modal แสดงรายละเอียดคำขอ                         |

---

### 🔹 หมวด Feature H: การ Refactor, คู่มือระบบ และชุดทดสอบ (Day 32 – 37)

|   วันที่   | ชื่อไฟล์เป้าหมาย                     | URL Route / หน้าจอในระบบ                       | สิ่งที่ต้องแสดงในภาพหน้าจอ                                                                     |
| :--------: | :----------------------------------- | :--------------------------------------------- | :--------------------------------------------------------------------------------------------- |
| **Day 32** | `day32_asset_titles_card.png`        | `/procurement/items` หรือ `/procurement/index` | หน้ารายการสินทรัพย์ที่มีการปรับปรุงชื่อหัวข้อ (Asset Titles) และการแสดงผล Item Card UI         |
| **Day 33** | `day33_payment_number_refactor.png`  | `/procurement/requisitions/details_specified`  | หน้าจอแบบฟอร์มและตารางที่มีการแสดงผลฟิลด์ _"Payment Number"_ (เลขที่ใบสำคัญจ่าย)               |
| **Day 34** | `day34_procurement_manual.png`       | `/procurement/manual`                          | หน้าระบบคู่มือการจัดซื้อจัดจ้างสำหรับเจ้าหน้าที่แบบ Interactive                                |
| **Day 35** | `day35_inventory_manual.png`         | `/inventory/manual`                            | หน้าระบบคู่มือการบริหารจัดการคลังพัสดุ (Inventory Management Manual)                           |
| **Day 36** | `day36_pytest_test_results.png`      | Terminal รันคำสั่ง `pytest`                    | หน้าต่าง Terminal แสดงผลการรันชุดทดสอบ `pytest tests/test_inventory_manual.py` ผ่าน 100% Green |
| **Day 37** | `day37_final_security_dashboard.png` | `/dashboard` หรือ หน้าแดชบอร์ดหลัก             | หน้าแดชบอร์ดภาพรวมระบบหลังผ่านการตรวจสอบความปลอดภัย Multi-Tenancy และความสมบูรณ์               |

---

## 🛠️ ขั้นตอนการตรวจสอบหลังนำภาพมาใส่ (Verification Checklist)

1. ตรวจสอบว่าในโฟลเดอร์ `docs/images/handover/` มีไฟล์ภาพครบทั้ง **20 ภาพ** ตามชื่อด้านบน
2. เปิดไฟล์ [WORK_DO_HANDOVER_REPORT_DETAILED.md](file:///f:/lab/kampan/WORK_DO_HANDOVER_REPORT_DETAILED.md)
3. ตรวจสอบว่ารูปภาพในแต่ละวัน (Day 18 ถึง Day 37) เรนเดอร์ขึ้นมาอย่างถูกต้องสมบูรณ์
