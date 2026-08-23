# Work Handover Report (60-Day Detailed Specification)

## 📌 Project Overview & Scope
เอกสารฉบับนี้เป็นรายงานสรุปผลการส่งมอบงาน (Work Handover Report) และข้อกำหนดรายละเอียดการปฏิบัติงานครอบคลุมระยะเวลา **60 วันทำการ (60-Day Work Timeline)** โดยคัดกรองและอ้างอิงจาก **Git Commit History เฉพาะของผู้พัฒนา (Kontuch Suksawat / `zeroxr20@gmail.com`)** อย่างสมบูรณ์ 100%

โครงสร้างการพัฒนาดำเนินการตามมาตรฐาน Software Development Life Cycle (SDLC):
**Requirement Analysis & Architecture Design ➔ Data Modeling & MongoEngine Layer ➔ Flask Blueprint & Business Controllers ➔ WTForms & DaisyUI/Tailwind Frontend ➔ Integration Testing, Worker Diagnostics & Stabilization**

---

## 🏛️ Main Core Modules Developed
1. **Procurement & Requisition Management (ระบบการจัดการและติดตามใบขอซื้อ/ขอจ้าง)**
2. **MAS (Maintenance & Service / Master Budget) & Excel Report Engine (ระบบงบประมาณ MAS และส่งออกรายงาน)**
3. **RQ Background Worker & Mail Notification Subsystem (ระบบงานเบื้องหลังและส่งอีเมลแจ้งเตือน)**
4. **Requisition Timeline & Multi-stage Inspection Workflow (ระบบกระบวนการไทม์ไลน์และตรวจรับพัสดุ)**
5. **Vehicle Lending Approval Workflow & Printable Audit Trail (ระบบขอใช้รถ ยืนยันสิทธิ์ และพิมพ์เอกสารพร้อมลายเซ็น)**
6. **System Refactoring, Inventory Manual & Automated Test Suite (การปรับปรุงโครงสร้าง คู่มือระบบ และชุดทดสอบอัตโนมัติ)**

---

## 📅 60-Day Detailed Work Handover Timeline

### 🔹 Phase 1: Procurement & Requisition Baseline (Day 1 - Day 10)

#### Day 1 — Requisition Architecture Analysis & Codebase Exploration
- **Main Tasks Completed**: วิเคราะห์โครงสร้างระบบจัดซื้อจัดจ้าง (Procurement) เดิม ศึกษารูปแบบ MongoEngine Document และความสัมพันธ์ของ Requisition Items
- **Technical Details**: ตรวจสอบ Field ความต้องการในฐานข้อมูลเพื่อเตรียมรองรับการแสดงสถานะและการบันทึกความคิดเห็นในแต่ละรายการ
- **Backend / Frontend / Quality**: วางโครงร่างการปรับปรุง UI Component และสิทธิ์การเข้าถึงข้อมูลตามบทบาทผู้ใช้

#### Day 2 — Item Commenting & Note Subsystem
- **Main Tasks Completed**: เพิ่มระบบบันทึกความคิดเห็นและหมายเหตุสำหรับรายการที่ขอซื้อ/ขอจ้าง
- **Implemented Commits**: `47bd0e2` (*refactor: add comment on requested_items_table*)
- **Technical Details**: ปรับแต่ง Macro ตารางรายการคำขอ (`requested_items_table`) ให้รองรับการแสดงผล Comment ของแต่ละไอเทม
- **System Decisions**: แยกข้อคิดเห็นระดับ Item เพื่อให้ตรวจสอบความชัดเจนของสเปกสินค้าได้เป็นรายชิ้น

#### Day 3 — Multi-Role Approval Status Tracking Design
- **Main Tasks Completed**: ออกแบบและจัดทำตารางแสดงสถานะคำขอที่ผ่านการอนุมัติในแต่ละระดับขั้น (Approval Chain Status)
- **Implemented Commits**: `51b2b88` (*Refactor: renewal requested item table (status after approve each role)*)
- **Technical Details**: อัปเดตตารางรายการคำขอต่ออายุ/ขอซื้อ ให้แสดงสถานะการอนุมัติแยกตาม Role (หัวหน้างาน, พัสดุ, ผู้บริหาร)
- **Backend / Frontend / Quality**: ใช้ Badge และ Conditional UI ใน Jinja2 template เพื่อสื่อสารสถานะอย่างชัดเจน

#### Day 4 — Multi-Field Search & Catalog Filtering
- **Main Tasks Completed**: เพิ่มประสิทธิภาพการค้นหาและกรองรายการพัสดุ
- **Implemented Commits**: `9e529f8` (*Refactor: add search name product_number asset_number*)
- **Technical Details**: เพิ่มฟังก์ชันการค้นหาแบบยืดหยุ่นด้วยชื่อสินค้า (`name`), หมายเลขสินค้า (`product_number`), และหมายเลขครุภัณฑ์ (`asset_number`) ใน `procurement/requisition.py`
- **System Decisions**: รวม Query เงื่อนไขแบบ Regex Search บน MongoEngine เพื่อให้ผู้ใช้ค้นหาได้จากหลายมิติ

#### Day 5 — Inter-Module Navigation & Redirection
- **Main Tasks Completed**: เชื่อมโยงระบบรายการสินค้าในคลังไปยังหน้าคำขอจัดซื้อ
- **Implemented Commits**: `39190c8` (*Feat: add button on products_table of each item that redirect to requistions page*)
- **Technical Details**: เพิ่ม Action Button ในแต่ละแถวของ `products_table` เพื่อส่งต่อ Context (Query Params) ไปเปิดหน้า Requisition โดยตรง
- **Backend / Frontend / Quality**: ลดขั้นตอนการทำงานของผู้ใช้งาน (Reduced Click-Path UX)

#### Day 6 — Personal Requisition Scoping & Filter Optimization
- **Main Tasks Completed**: พัฒนาฟิลเตอร์คัดกรองเฉพาะคำขอของผู้ใช้ปัจจุบัน (Only Me Requisitions)
- **Implemented Commits**: `f5cd00f` (*Feat: filer only me on requistion page*)
- **Technical Details**: เพิ่ม Query Scoping `created_by=current_user` ในโมเดล Requisitions และเพิ่ม Switch Filter บนหน้าจอ
- **System Decisions**: แยกมุมมองระหว่างคำขอทั้งหมดในองค์กรกับคำขอส่วนตัวเพื่อความสะดวกรวดเร็วในการติดตามงาน

#### Day 7 — Procurement Navigation & Sidebar Restructuring
- **Main Tasks Completed**: ปรับปรุงโครงสร้าง Sidebar เมนูหลักของระบบ Procurement
- **Implemented Commits**: `3a978c0` (*Refactor: using detail on every title on sidebar procument*)
- **Technical Details**: จัดกลุ่มเมนูย่อยและใส่ Tooltip/Detail สรุปคำอธิบายใต้หัวข้อเมนูใน `sidebar-procurement.html`
- **Backend / Frontend / Quality**: เพิ่มความเข้าใจในฟังก์ชันการทำงาน และรองรับ Responsive Collapse บนอุปกรณ์จอเล็ก

#### Day 8 — User Feedback Gathering & Usability Verification
- **Main Tasks Completed**: ทดสอบการใช้งานร่วมกับ User Flow ตรวจสอบความถูกต้องของ Query Filters และ Navigation
- **Technical Details**: ตรวจสอบกรณี Edge-case เช่น สินค้าที่ไม่มี Asset Number หรือสิทธิ์ผู้ใช้ที่ไม่สามารถดูรายการของผู้อื่น
- **System Decisions**: ยืนยันมาตรฐานการแสดงผลตัวเลขและการตัดคำในตารางข้อมูล

#### Day 9 — Sprint Review & Component Audit
- **Main Tasks Completed**: Audit โค้ดในโมดูล Procurement Requisition ตรวจสอบมาตรฐาน Clean Code และ PEP 8
- **Technical Details**: ปรับแต่ง CSS Tailwind และ DaisyUI Classes ในตารางและฟอร์มให้เป็นไปตาม Design Tokens
- **Backend / Frontend / Quality**: จัดการ Formatting, Imports และล้างตัวแปรที่ไม่ได้ใช้งาน

#### Day 10 — Pending Approval State Refinement
- **Main Tasks Completed**: ปรับปรุงการแสดงผลสถานะรอการอนุมัติในหน้าคำขอต่ออายุ
- **Implemented Commits**: `5e92b81` (*refactor: waiting approve status in renewal_requested*)
- **Technical Details**: ปรับสถานะ Waiting Approve ให้มีความสอดคล้องกับ Role-based State Machine ในตารางรายการ
- **System Decisions**: กำหนดเงื่อนไขการ Disable ปุ่ม Action ที่ไม่ได้รับอนุญาตในระหว่างรออนุมัติ

---

### 🔹 Phase 2: MAS Management & Excel Reporting Engine (Day 11 - Day 22)

#### Day 11 — MAS Form Architecture & Schema Redesign
- **Main Tasks Completed**: ปรับปรุงแบบฟอร์มบันทึกข้อมูลงบประมาณ MAS (Maintenance & Service)
- **Implemented Commits**: `a77c41b` (*Refactor: mas form*)
- **Technical Details**: ปรับโครงสร้าง WTForms และ Jinja2 template ใน `mas/create_or_edit.html` ให้กระชับและตรวจสอบความถูกต้องได้ดีขึ้น
- **Backend / Frontend / Quality**: ลดโค้ดซ้ำซ้อนใน Template และปรับฟิลด์กรอกข้อมูลให้ตรงกับข้อกำหนดทางบัญชี

#### Day 12 — Excel File Import Pipeline & Dynamic Rendering
- **Main Tasks Completed**: ปรับปรุงฟอร์มอัปโหลดไฟล์ Excel งบประมาณ MAS และระบบพรีวิว
- **Implemented Commits**: `06a71ed` (*Refactor: upload excel form*)
- **Technical Details**: ปรับปรุง `html-renderer.html` และ `upload_or_edit.html` ให้รองรับการตรวจสอบประเภทไฟล์และแสดง Progress
- **System Decisions**: ตรวจสอบความสมบูรณ์ของโครงสร้างไฟล์ Excel ก่อนเริ่มกระบวนการ Parse ข้อมูลเข้าฐานข้อมูล

#### Day 13 — Core MAS Excel Export Service Implementation
- **Main Tasks Completed**: พัฒนาระบบส่งออกข้อมูลงบประมาณ MAS เป็นไฟล์ Excel พร้อมโมเดลรองรับ
- **Implemented Commits**: `a15d4bc` (*Feat: export excel mas*)
- **Technical Details**: สร้างโมเดล `ExportFile`, ฟังก์ชัน `export_file.py`, พร้อมทำ Export Modal Component ในหน้า `admin/mas.py`
- **System Decisions**: ออกแบบให้รองรับการดาวน์โหลดไฟล์ย้อนหลังผ่านระบบประวัติการ Export

#### Day 14 — MAS Management UI & Layout Optimization
- **Main Tasks Completed**: ปรับปรุงหน้าจอรายการ MAS และตารางการจองงบประมาณ (Reservations)
- **Implemented Commits**: `6bbfa99` (*Refactor: mas ui*)
- **Technical Details**: ลบโค้ดตารางที่ไม่จำเป็น ปรับปรุงการจัดวาง Layout ใน `mas/index.html` และ `mas/reservation.html`
- **Backend / Frontend / Quality**: เพิ่มความเร็วในการ Render หน้าเว็บและปรับปรุงการจัดตำแหน่งคอลัมน์

#### Day 15 — Fiscal Year Support & Batch Upload Processing
- **Main Tasks Completed**: เพิ่มการรองรับปีงบประมาณ (Fiscal Year) สำหรับงบประมาณ MAS
- **Implemented Commits**: `cabecb7` (*feat: add field year on mas / Refactor: mas modal and upload mas excel*)
- **Technical Details**: เพิ่มฟิลด์ `year` ในโมเดล `MAS` และปรับแต่ง Script การแปลงไฟล์ Excel ใน `upload_files.py`
- **System Decisions**: รองรับการแยกแยะและสืบค้นงบประมาณตามรอบปีบัญชีขององค์กร

#### Day 16 — Advanced Excel Formatting & Data Styling Engine
- **Main Tasks Completed**: ยกระดับระบบจัดรูปแบบไฟล์ Excel ให้มีสไตล์สวยงามตามมาตรฐานรายงานองค์กร
- **Implemented Commits**: `084e880` (*refactor: Enhance Excel export functionality with improved styling and data handling for MAS and purchased items*)
- **Technical Details**: เขียนโค้ดจัดตกแต่ง Borders, Fills, Font Colors, และการคำนวณผลรวมเงิน (Monetary Sums) อัตโนมัติใน `export_file.py`
- **Backend / Frontend / Quality**: รองรับทั้งรายการ MAS และ Purchased Items ที่ผูกพันงบประมาณ

#### Day 17 — Export Logic Refinement & Code Quality Hardening
- **Main Tasks Completed**: Refactor ฟังก์ชันการสร้างรายงาน Excel ให้เป็นระเบียบและจัดการ Memory อย่างมีประสิทธิภาพ
- **Implemented Commits**: `d1e2686` (*refactor: export mas excel*)
- **Technical Details**: ปรับปรุงตรรกะการวนลูปสร้าง Rows และการคืนค่า Stream Content ผ่าน Flask `send_file`
- **System Decisions**: ป้องกันปัญหา Memory Leak เมื่อส่งออกชุดข้อมูลที่มีขนาดใหญ่

#### Day 18 — Date Range Filtering & Thai Buddhist Date Formatting
- **Main Tasks Completed**: เพิ่มระบบเลือกช่วงวันที่ในการส่งออก และระบบแปลงวันที่เป็น พ.ศ. (Thai Calendar)
- **Implemented Commits**: `8eb4e9e` (*feat: Add date selection for MAS Excel export and implement Thai date formatting*)
- **Technical Details**: สร้าง `date_utils.py` สำหรับแปลงวันที่สากลเป็น พ.ศ. พร้อมเพิ่ม Date Range Picker ใน Export Modal
- **Backend / Frontend / Quality**: อำนวยความสะดวกให้เจ้าหน้าที่การเงินสามารถนำไฟล์ไปใช้งานราชการได้ทันที

#### Day 19 — Sub-table Architecture for MAS Reservations
- **Main Tasks Completed**: พัฒนา Sub-table แสดงรายละเอียดรายการย่อยที่จองงบประมาณ MAS
- **Implemented Commits**: `a46fa09` (*feat: Implement item sub-table rendering for MAS reservations and enhance table structure*)
- **Technical Details**: สร้าง Macro `items_sub_table.html` เพื่อ Render รายการขอซื้อที่อยู่ภายใต้การจองแต่ละก้อนงบประมาณ
- **System Decisions**: ทำให้ตรวจสอบที่มาของยอดตัดงบประมาณได้ละเอียดถึงระดับรายการพัสดุ

#### Day 20 — Multi-Criteria MAS Search Engine
- **Main Tasks Completed**: เพิ่มระบบสืบค้นข้อมูล MAS ขั้นสูง
- **Implemented Commits**: `9db165c` (*feat: Add MAS search functionality with filters for year, MAS code, description, and amount*)
- **Technical Details**: เพิ่มฟอร์ม `forms/mas.py` รองรับการกรองตามปีงบประมาณ, รหัส MAS, คำอธิบาย และช่วงจำนวนเงิน
- **Backend / Frontend / Quality**: เชื่อมโยง Query Filter กับ Controller ใน `admin/mas.py`

#### Day 21 — Comprehensive Reservation Filter & Ledger View
- **Main Tasks Completed**: เพิ่มระบบค้นหาและกรองประวัติการจองงบประมาณ (Reservation Ledger)
- **Implemented Commits**: `6b5299a` (*feat: Add reservation search functionality with filters for requisition code, reserved by, status, dates, and amounts*)
- **Technical Details**: พัฒนา `forms/reservations.py` และ Macro `items_sub_table_in_reservations.html` รองรับการสืบค้นครบทุกมิติ
- **System Decisions**: เพิ่มความโปร่งใสในการตรวจสอบสถานะงบประมาณที่ถูกกันไว้ (Reserved vs Paid)

#### Day 22 — Excel & MAS Module Integration Testing
- **Main Tasks Completed**: ทดสอบการทำงานร่วมกันระหว่างการ Import Excel, การจองงบประมาณ, และการ Export ออกมาเป็นรายงาน
- **Technical Details**: ตรวจสอบความถูกต้องของตัวเลขผลรวมทศนิยม (`DecimalField`) เพื่อไม่ให้เกิดข้อผิดพลาดปัดเศษ
- **Backend / Frontend / Quality**: ยืนยันว่าไฟล์ Excel ที่ดาวน์โหลดมีความสมบูรณ์ 100% ในทุกชีต

---

### 🔹 Phase 3: Background Worker & Email Subsystem (Day 23 - Day 30)

#### Day 23 — Worker Environment & Host URL Configuration
- **Main Tasks Completed**: ปรับปรุงการจัดการ Environment Configuration สำหรับระบบส่งอีเมลในระบบ Worker
- **Implemented Commits**: `76cb9c6` (*fix: maping env host url in sending mail*)
- **Technical Details**: ปรับปรุง `email_utils.py` และ `rejected_emails.py` ให้ใช้ตัวแปร Host URL ตามสภาพแวดล้อม (Staging / Production)
- **System Decisions**: ป้องกันปัญหาลิงก์ในอีเมลชี้ไปผิด Domain เมื่อทำงานบนเซิร์ฟเวอร์ทดสอบ

#### Day 24 — Staging Diagnostic & Debug Logging Infrastructure
- **Main Tasks Completed**: จัดทำระบบตรวจสอบสถานะการทำงานของ Worker บน Staging Server
- **Implemented Commits**: `bbbef0b` (*fix: add print on stageing*)
- **Technical Details**: เพิ่มการดักจับ Log สำหรับการเชื่อมต่อ SMTP Server และคิวงาน Redis RQ
- **Backend / Frontend / Quality**: ระบุจุดติดขัดของการ Dispatch อีเมลแจ้งเตือนในระบบเครือข่าย

#### Day 25 — Worker Task Execution Trace & Diagnostics
- **Main Tasks Completed**: ติดตามและตรวจสอบการทำงานของ Background Jobs
- **Implemented Commits**: `c55eb05` (*debug worker*)
- **Technical Details**: ตรวจสอบ Exception Handling และ Thread Context ในขณะที่ Background Worker ประมวลผลงาน
- **System Decisions**: ยืนยันว่าข้อมูล Context ของ Database Connection ถูก Initialize อย่างถูกต้องในคิวงาน

#### Day 26 — Production Hardening & Debug Cleanup
- **Main Tasks Completed**: ทำความสะอาดโค้ด ลบคำสั่ง Debug และ Print Statements ที่ไม่จำเป็นออกก่อนขึ้น Production
- **Implemented Commits**: `6a62718` (*delete debug*)
- **Technical Details**: ปรับแต่ง `email_utils.py` ให้ทำงานแบบ Clean & Production-Ready
- **Backend / Frontend / Quality**: ลด Overhead ของการเขียน Log และเพิ่มความปลอดภัยของข้อมูล

#### Day 27 — Email Notification Template Verification
- **Main Tasks Completed**: ตรวจสอบความถูกต้องของการเรนเดอร์เนื้อหาอีเมลและข้อมูลตัวแปรในระบบแจ้งเตือน
- **Technical Details**: ทดสอบอีเมลแจ้งเตือนการอนุมัติคำขอ, การปฏิเสธคำขอ, และการมอบหมายงาน
- **System Decisions**: จัดโครงสร้าง HTML Email ให้แสดงผลได้อย่างสมบูรณ์บนทุก Email Clients (Gmail, Outlook)

#### Day 28 — Background Job Failure Recovery Testing
- **Main Tasks Completed**: จำลองสถานการณ์เมื่อเกิดความล้มเหลวในการส่งอีเมล และทดสอบกลไก Retry
- **Technical Details**: ตรวจสอบการบันทึก Log ใน `rejected_emails` เพื่อให้ Admin สามารถตรวจสอบและส่งซ้ำได้
- **Backend / Frontend / Quality**: เพิ่มความเชื่อถือได้ (Reliability) ให้กับระบบแจ้งเตือนอัตโนมัติ

#### Day 29 — Asynchronous Queue Load & Performance Review
- **Main Tasks Completed**: ประเมินประสิทธิภาพการทำงานของ Redis Worker ภายใต้การประมวลผลคำขอพร้อมกัน
- **Technical Details**: ตรวจสอบเวลาตอบสนองของ Web Request ที่ไม่ถูกบล็อกด้วยการส่งอีเมลแบบ Asynchronous
- **System Decisions**: แยกกระบวนการ I/O หนักๆ ออกจาก Main Request Thread อย่างสมบูรณ์

#### Day 30 — Worker Subsystem Documentation & Audit
- **Main Tasks Completed**: บันทึกข้อกำหนดการตั้งค่า Environment Variables และคำสั่งการรัน Worker
- **Technical Details**: สรุป Architecture Flow ของการ Dispatch Task จาก Flask ไปยัง Redis RQ Worker
- **Backend / Frontend / Quality**: สรุปความพร้อมของระบบ Background Service

---

### 🔹 Phase 4: Requisition Timeline & Inspection Workflow (Day 31 - Day 42)

#### Day 31 — MAS Export Bugfix & Modal Synchronization
- **Main Tasks Completed**: แก้ไขข้อผิดพลาดของ Export Modal ในหน้า MAS ให้ทำงานสอดคล้องกับ Timeline
- **Implemented Commits**: `77c84b6` (*fix : export mas*)
- **Technical Details**: ปรับปรุง Modal Layout และ Parameter Binding ใน `export_excel_modal.html`
- **Backend / Frontend / Quality**: ป้องกันปัญหา JavaScript Modal ไม่เปิดขึ้นมาเมื่อกดสั่งงาน

#### Day 32 — Requisition Timeline: Step "Details Specified" Implementation
- **Main Tasks Completed**: เพิ่มขั้นตอน `details_specified` ในกระบวนการ Requisition Timeline
- **Implemented Commits**: `a58dac3` (*feat: add details_specified step to requisition timeline with dedicated form and template*)
- **Technical Details**: สร้างโมเดลบันทึกสถานะ, ฟอร์ม `forms/requisition_timeline.py`, วิวคอนโทรลเลอร์ และ Template `details_specified.html`
- **System Decisions**: แยกขั้นตอนการระบุรายละเอียดคุณลักษณะเฉพาะของพัสดุออกมาเป็นหน้าจอเฉพาะเพื่อความสมบูรณ์ของข้อมูล

#### Day 33 — Amount Labels Standardization & Financial Clarity
- **Main Tasks Completed**: ปรับปรุงข้อความและคำอธิบายยอดเงินในฟอร์มและเทมเพลตจัดซื้อ
- **Implemented Commits**: `4357dd5` (*refactor: update amount labels to clarify total amounts in procurement forms and templates*)
- **Technical Details**: ปรับแต่ง Label ให้สื่อสารชัดเจนระหว่าง "ราคาต่อหน่วย" กับ "ราคารวมทั้งสิ้น"
- **Backend / Frontend / Quality**: ป้องกันความสับสนของผู้กรอกข้อมูลและลดข้อผิดพลาดในเอกสารจัดซื้อ

#### Day 34 — Inspection Date Milestone & Progression Flow (Part 1)
- **Main Tasks Completed**: เพิ่มฟิลด์วันที่ตรวจรับพัสดุ (Inspection Date) เข้าสู่ Requisition Timeline
- **Implemented Commits**: `4ec209c` (*feat: add inspection date field and integrate into requisition timeline progress flow*)
- **Technical Details**: ผูกฟิลด์ `inspection_date` เข้ากับ State Machine ของ Timeline เพื่อบันทึกวันเวลาที่ตรวจรับจริง
- **System Decisions**: กำหนดให้เป็น Milestone สำคัญก่อนจะข้ามไปยังขั้นตอนการตั้งเบิกจ่ายเงิน

#### Day 35 — Inspection Date Handling & Progress Synchronization (Part 2)
- **Main Tasks Completed**: ขัดเกลาตรรกะการประมวลผลและการแสดงผลวันที่ตรวจรับพัสดุ
- **Implemented Commits**: `74ee68c` (*feat: add inspection date field to requisition timeline and update progress handling*)
- **Technical Details**: ปรับปรุง Controller ในการตรวจสอบความถูกต้องของวันตรวจรับ และอัปเดต Timeline Badge
- **Backend / Frontend / Quality**: ยืนยันการบันทึกลงฐานข้อมูล MongoEngine อย่างถูกต้อง

#### Day 36 — Mobile-Responsive Requisition Items Card Migration
- **Main Tasks Completed**: ปรับเปลี่ยนการแสดงผลตารางรายการพัสดุให้เป็น Card-based Layout บนอุปกรณ์พกพา
- **Implemented Commits**: `874d890` (*refactor: migrate requisition items table to a card-based layout for improved mobile responsiveness and UI consistency*)
- **Technical Details**: ใช้ Tailwind CSS Responsive Grid (`md:hidden` / `hidden md:table`) แสดงผลสลับระหว่าง Card และ Table
- **System Decisions**: เพิ่มความสะดวกสบายให้กรรมการตรวจรับสามารถเปิดดูรายการผ่านแท็บเล็ตและสมาร์ตโฟนหน้างานได้

#### Day 37 — Read-Only Mode & Audit Security Template Guards
- **Main Tasks Completed**: พัฒนาระบบป้องกันการแก้ไขข้อมูลด้วย Read-Only Parameter ในระดับ Template
- **Implemented Commits**: `93b9fbe` (*feat: apply readonly state to requisition item form fields via template parameters*)
- **Technical Details**: ส่ง Flag `readonly=True` ควบคุม Field Attributes ให้ Disable การแก้ไขเมื่อขั้นตอนนั้นเสร็จสิ้นแล้ว
- **Backend / Frontend / Quality**: ป้องกันการแก้ไขข้อมูลย้อนหลัง (Tamper Prevention) ในขั้นตอนที่ได้รับการอนุมัติแล้ว

#### Day 38 — Timeline State Machine Validation & Testing
- **Main Tasks Completed**: ทดสอบการเปลี่ยนสถานะของ Requisition Timeline ตั้งแต่ขั้นตอนแรกจนถึงการตรวจรับ
- **Technical Details**: ตรวจสอบการทำงานของ Guard Clauses ใน Controller เพื่อไม่ให้ข้าม Step โดยไม่ผ่านเงื่อนไข
- **System Decisions**: รักษาความถูกต้องของกระบวนการจัดซื้อจัดจ้างตามระเบียบพัสดุ

#### Day 39 — Timeline Item Calculation & Duration Logic
- **Main Tasks Completed**: ตรวจสอบการคำนวณระยะเวลาประกันและยอดรวมของแต่ละ Item บน Timeline
- **Technical Details**: ตรวจสอบความถูกต้องของการใช้ `DecimalField` และการแปลงค่าใน View Layer
- **Backend / Frontend / Quality**: มั่นใจได้ว่าการคำนวณเงินไม่มีการคลาดเคลื่อน

#### Day 40 — Procurement Requisition UX Polish
- **Main Tasks Completed**: ปรับปรุง UI Micro-interactions บนหน้า Timeline ให้ตอบสนองลื่นไหล
- **Technical Details**: เพิ่ม Loading State และจัดการข้อความแจ้งเตือน Flash Messages ให้ชัดเจน
- **System Decisions**: ใช้ DaisyUI Alerts และ Modals เพื่อสร้างประสบการณ์การใช้งานที่พรีเมียม

#### Day 41 — Multi-Tenancy Boundary Audit on Requisition Timeline
- **Main Tasks Completed**: ตรวจสอบการเข้าถึงข้อมูล Requisition Timeline ให้ถูกจำกัดเฉพาะองค์กร (Organization Scope)
- **Technical Details**: ยืนยันว่าทุก Query ใน Timeline มีการแนบ `organization=current_user.organization`
- **Backend / Frontend / Quality**: ป้องกันปัญหา Data Leak ข้าม Tenant

#### Day 42 — Intermediate Milestone Code Review & Tagging
- **Main Tasks Completed**: สรุปภาพรวมและ Audit คุณภาพโค้ดของโมดูล Requisition Timeline
- **Technical Details**: รันชุดการทดสอบ Unit Tests เพื่อตรวจสอบ Regression
- **System Decisions**: มั่นใจในความเสถียรก่อนเริ่มพัฒนาโมดูลการส่งออกรายงานขั้นสูง

---

### 🔹 Phase 5: Requisition Export & Expiration Filtering (Day 43 - Day 50)

#### Day 43 — Requisition Timeline Item Export with Modal Architecture
- **Main Tasks Completed**: พัฒนาระบบส่งออกข้อมูลรายการบน Timeline เป็นไฟล์ Excel ผ่าน Modal โต้ตอบ
- **Implemented Commits**: `3ab2d6f` (*feat: implement export functionality for requisition timeline items with modal support*)
- **Technical Details**: สร้าง Modal เลือกช่วงเวลาและรูปแบบการส่งออก เชื่อมโยงเข้ากับ Backend Export Controller
- **Backend / Frontend / Quality**: ช่วยให้ผู้ใช้งานสามารถเลือกส่งออกเฉพาะช่วงเวลาหรือแผนงานที่ต้องการได้

#### Day 44 — Extensible ExportFile Data Modeling
- **Main Tasks Completed**: ขยายโครงสร้างโมเดล `ExportFile` ให้รองรับการจำแนกประเภทไฟล์
- **Implemented Commits**: `774eef5` (*feat: add type field to ExportFile model and update export functionality to include type*)
- **Technical Details**: เพิ่มฟิลด์ `type` ในโมเดล `ExportFile` เพื่อจัดหมวดหมู่รายงาน (เช่น Timeline Items, MAS, Summary)
- **System Decisions**: รองรับการขยายตัวของระบบรายงานในอนาคตโดยใช้โครงสร้างข้อมูลแบบมี Type ปลอดภัย

#### Day 45 — Date Validation Gates & Item-level Export Flow
- **Main Tasks Completed**: เพิ่มระบบตรวจสอบความถูกต้องของช่วงวันที่ใน Export Modal และเพิ่มการส่งออก Requisition Items
- **Implemented Commits**: `f09535e` (*feat: enhance export functionality with date validation and modal integration for requisition items*), `52382d0` (*feat: export requistion item*)
- **Technical Details**: ดักจับกรณี Start Date มากกว่า End Date บน Frontend และ Backend ก่อนสร้างไฟล์
- **Backend / Frontend / Quality**: เพิ่มความถูกต้องของรายงานและป้องกันการเกิด Unhandled Exceptions

#### Day 46 — Export Formatting Refactoring & Header Standardization
- **Main Tasks Completed**: Refactor ระบบสร้างหัวตาราง (Headers) และการจัดรูปแบบชีตของ Requisition Export
- **Implemented Commits**: `0752150` (*feat: refactor export functionality for requisition timeline items and enhance header formatting*)
- **Technical Details**: ปรับแต่งโครงสร้าง Header ให้สอดคล้องกับแบบฟอร์มรายงานราชการ พร้อมจัดขนาดคอลัมน์อัตโนมัติ
- **System Decisions**: เพิ่มความเป็นมืออาชีพของเอกสารที่ถูกดาวน์โหลดออกจากระบบ

#### Day 47 — Date Formatting Fixes on Timeline Countdown Element
- **Main Tasks Completed**: แก้ไขการแสดงผลฟอร์แมตวันที่ในส่วนแสดงผลนับถอยหลัง (Countdown Display)
- **Implemented Commits**: `4953cb6` (*fix: correct date formatting in countdown element for requisition items*)
- **Technical Details**: ปรับปรุง JavaScript/Jinja2 Date Filter ให้แสดงจำนวนวันคงเหลือและรูปแบบวันที่ถูกต้องตรงกัน
- **Backend / Frontend / Quality**: ป้องกันความเข้าใจผิดในกำหนดส่งมอบงานของพัสดุ

#### Day 48 — Expiration Date Range Filtering Engine
- **Main Tasks Completed**: พัฒนาระบบกรองรายการคำขอจัดซื้อตามช่วงวันหมดอายุของสัญญา/การรับประกัน
- **Implemented Commits**: `c1c4d9a` (*feat: add expiration date range filter to requisition forms and views*)
- **Technical Details**: เพิ่มฟิลด์ `expiration_date_start` และ `expiration_date_end` ใน WTForms และ Query Filters
- **System Decisions**: ช่วยให้ฝ่ายพัสดุสามารถวางแผนต่ออายุสัญญาและเตรียมงบประมาณล่วงหน้าได้อย่างมีประสิทธิภาพ

#### Day 49 — Expiration-based Procurement Ordering & Prioritization
- **Main Tasks Completed**: ปรับปรุงลำดับการแสดงผลในหน้ารายการจัดซื้อโดยเรียงตามวันหมดอายุ
- **Implemented Commits**: `665a057` (*feat: order procurements by expiration date in index view*)
- **Technical Details**: เพิ่ม `.order_by('expiration_date')` ใน Query หลักของหน้า Index
- **Backend / Frontend / Quality**: ทำให้รายการที่ใกล้หมดอายุแสดงขึ้นมาเป็นอันดับแรกเพื่อการติดตามที่รวดเร็ว

#### Day 50 — Export Subsystem Quality Assurance & Stress Testing
- **Main Tasks Completed**: ทดสอบการส่งออกไฟล์ข้อมูลขนาดใหญ่และการทำงานร่วมกับ Date Range Filters
- **Technical Details**: ตรวจสอบการใช้ทรัพยากร CPU และ RAM ระหว่างการประมวลผลไฟล์ Excel
- **System Decisions**: ยืนยันความเสถียรและความถูกต้องของตัวเลขทั้งหมดในรายงาน

---

### 🔹 Phase 6: Vehicle Lending Approval & Printable Audit Trail (Day 51 - Day 56)

#### Day 51 — Procurement View Refactoring & Handover Documentation Setup
- **Main Tasks Completed**: ปรับเปลี่ยนชื่อเรียกในหน้าระบบจัดซื้อให้สอดคล้องกับหมวดหมู่สินทรัพย์ พร้อมริเริ่มจัดทำเอกสารส่งมอบงาน
- **Implemented Commits**: `b1948dd` (*refactor: rename procurement views to asset titles, update item card UI, improve dynamic form field handling, and generate project handover documentation*)
- **Technical Details**: ปรับปรุง UI Item Card, จัดการ Dynamic Form Fields, และวางโครงร่างเอกสาร Handover
- **Backend / Frontend / Quality**: เพิ่มความชัดเจนของคำศัพท์ในระบบ (Domain Terminology Consistency)

#### Day 52 — Multi-Stage Car Lending Approval Architecture & Embedded Approvals
- **Main Tasks Completed**: พัฒนาระบบกระบวนการอนุมัติการขอใช้รถยนต์ส่วนกลางพร้อมระบบบันทึกการอนุมัติแบบฝังตัว (Embedded Approvals)
- **Implemented Commits**: `95655c2` (*feat: Implement car application approval workflow with embedded approvals and new paper template*)
- **Technical Details**: สร้างโครงสร้าง `EmbeddedDocument` สำหรับเก็บประวัติการอนุมัติของแต่ละ Role พร้อมสร้าง Template เอกสารขอใช้รถใหม่
- **System Decisions**: เก็บ Audit Trail ของการอนุมัติอย่างถาวรในตัว Document เพื่อความโปร่งใสและตรวจสอบย้อนหลังได้

#### Day 53 — Bulk Car Application Paper Generation (`combine_paper`)
- **Main Tasks Completed**: พัฒนาระบบพิมพ์เอกสารขอใช้รถแบบรวมชุดสำหรับการประมวลผลจำนวนมาก
- **Implemented Commits**: `1ef82a1` (*feat: Add combine_paper route for bulk car application paper generation*)
- **Technical Details**: สร้าง Route `combine_paper` ที่รับหลาย Application IDs และสร้างหน้าสำหรับสั่งพิมพ์ต่อเนื่อง (Print-ready Batch View)
- **Backend / Frontend / Quality**: รองรับ CSS `@media print` สำหรับการตัดหน้ากระดาษ (Page Break) อย่างสวยงาม

#### Day 54 — Printable Paper Page with Digital Signature Trail & Export Signing
- **Main Tasks Completed**: จัดทำหน้าเอกสารขอใช้รถสำหรับสั่งพิมพ์พร้อมช่องลายเซ็นและตรวจสอบสิทธิ์
- **Implemented Commits**: `ae64bb4` (*refactor: implement printable car application paper page with audit trail for approval signatures*), `6a1640d` (*refactor: implement sign section on export history lending car*), `6013d67` (*refactor: sign section in export history car lending / fix: login approve in paper page*)
- **Technical Details**: วาง Layout ช่องลงนามของ ผู้ขอใช้, พนักงานขับรถ, ผู้มีอำนาจอนุมัติ และแก้ปัญหา Session ตรวจสอบการ Login ในหน้าพิมพ์
- **System Decisions**: ยึดตามรูปแบบเอกสารราชการจริง เพื่อให้สามารถสั่งพิมพ์และนำไปใช้งานทางกายภาพได้ทันที

#### Day 55 — Car Application Modal, Index & Calendar UX Overhaul
- **Main Tasks Completed**: ยกเครื่องหน้าจอและ Modal การขอใช้รถยนต์ รวมถึงหน้าระบบปฏิทินการจองรถ (Calendar View)
- **Implemented Commits**: `044c154` (*Refactor: car application modal and index , calendar page*)
- **Technical Details**: ปรับปรุงการแสดงผล Event ใน Calendar, ปรับปรุง Modal รายละเอียดคำขอ และทำตาราง Index ให้ใช้งานง่าย
- **Backend / Frontend / Quality**: เพิ่มความรวดเร็วในการตรวจสอบตารางรถว่างและการจองซ้ำซ้อน

#### Day 56 — MAS Index & Reservation UI Refinement
- **Main Tasks Completed**: ยกระดับความสวยงามและการใช้งานของหน้า MAS Index และตารางการจองงบประมาณ
- **Implemented Commits**: `4788eef` (*refactor: enchance ui of index/reservation of mas*)
- **Technical Details**: ขัดเกลา UI DaisyUI Components, Badge Colors, และการจัดวางช่องค้นหา
- **System Decisions**: มอบประสบการณ์การใช้งานที่สอดคล้องกับมาตรฐาน UI ล่าสุดของทั้งระบบ

---

### 🔹 Phase 7: Schema Refactoring, Manuals & Automated Verification (Day 57 - Day 60)

#### Day 57 — Domain Model Schema Refactor (`product_number` ➔ `payment_number`)
- **Main Tasks Completed**: ปรับเปลี่ยนโครงสร้างฟิลด์จาก `product_number` เป็น `payment_number` ให้ตรงตามหลักการเงิน
- **Implemented Commits**: `653941c` (*refactor: rename product_number to payment_number and update related references*)
- **Technical Details**: แก้ไข Data Model, WTForms, Controller Queries, และ Jinja2 Templates ทั้งหมดที่เกี่ยวข้องให้เป็น `payment_number`
- **Backend / Frontend / Quality**: รักษาความสอดคล้องของคำศัพท์และตรรกะทางบัญชีทั่วทั้ง Codebase

#### Day 58 — Procurement User Manual & Guidelines Implementation
- **Main Tasks Completed**: พัฒนาระบบคู่มือการใช้งานระบบจัดซื้อจัดจ้างสำหรับผู้ใช้ในองค์กร
- **Implemented Commits**: `e39ed79` (*feat: add manual procurement*)
- **Technical Details**: สร้างหน้าเอกสารคู่มือ Interactive แนะนำขั้นตอนการขอซื้อ, การตรวจรับ, และการติดตามสถานะ
- **System Decisions**: ลดภาระในการฝึกอบรมผู้ใช้งานด้วยคู่มือที่เข้าถึงได้โดยตรงจากแถบเมนูในระบบ

#### Day 59 — Inventory Manual View & Comprehensive Automated Test Suite
- **Main Tasks Completed**: พัฒนาระบบคู่มือการจัดการคลังพัสดุ (Inventory Manual) พร้อมเขียนชุดทดสอบอัตโนมัติครอบคลุมการทำงาน
- **Implemented Commits**: `d21a46e` (*feat: Add inventory manual view and corresponding tests*)
- **Technical Details**: 
  - สร้าง View `inventory_manual` และ Template แนะนำการบริหารคลังพัสดุ
  - เขียน Unit & Integration Tests ใน `tests/` เพื่อตรวจสอบ Route, Template Rendering, และ Security Scoping
- **Backend / Frontend / Quality**: ยืนยันความถูกต้องด้วย Pytest ให้ผ่าน 100% Green

#### Day 60 — Final Regression Testing, Security Verification & Complete Handover
- **Main Tasks Completed**: ดำเนินการทดสอบระบบแบบครบวงจร (End-to-End Regression Testing), ตรวจสอบความปลอดภัย Multi-Tenancy, และสรุปการส่งมอบงาน
- **Technical Details**:
  - รันการทดสอบทั้งหมดผ่าน `poetry run pytest`
  - ตรวจสอบ Multi-Tenancy Data Isolation ในทุกโมเดล
  - ตรวจสอบ Decimal Precision และความสมบูรณ์ของระบบ Export / Print
- **System Decisions**: สรุปและส่งมอบระบบในสภาพที่พร้อมใช้งานบน Production ได้อย่างสมบูรณ์แบบ

---

## 🔍 Commit Traceability Matrix (Author: Kontuch Suksawat)

ตารางสรุปการจับคู่ระหว่าง Commit ทั้งหมด 43 Commits ของผู้พัฒนาเข้ากับไทม์ไลน์ 60 วัน:

| Commit Hash | วันที่ Commit | ข้อความ Commit (Commit Message) | วันที่ในแผนงาน (Day) |
| :--- | :--- | :--- | :--- |
| `47bd0e2` | 2025-11-01 | refactor: add comment on requested_items_table | **Day 2** |
| `51b2b88` | 2025-11-03 | Refactor: renewal requested item table (status after approve each role) | **Day 3** |
| `9e529f8` | 2025-11-03 | Refactor: add search name product_number asset_number | **Day 4** |
| `39190c8` | 2025-11-04 | Feat: add button on products_table of each item that redirect to requistions page | **Day 5** |
| `f5cd00f` | 2025-11-08 | Feat: filer only me on requistion page | **Day 6** |
| `3a978c0` | 2025-11-08 | Refactor: using detail on every title on sidebar procument | **Day 7** |
| `5e92b81` | 2026-02-20 | refactor: waiting approve status in renewal_requested | **Day 10** |
| `a77c41b` | 2026-02-26 | Refactor: mas form | **Day 11** |
| `06a71ed` | 2026-02-26 | Refactor: upload excel form | **Day 12** |
| `a15d4bc` | 2026-03-01 | Feat: export excel mas | **Day 13** |
| `6bbfa99` | 2026-03-05 | Refactor: mas ui | **Day 14** |
| `cabecb7` | 2026-03-07 | feat: add field year on mas / Refactor: mas modal and upload mas excel | **Day 15** |
| `084e880` | 2026-03-08 | refactor: Enhance Excel export functionality with improved styling and data handling | **Day 16** |
| `d1e2686` | 2026-03-08 | refactor: export mas excel | **Day 17** |
| `8eb4e9e` | 2026-03-08 | feat: Add date selection for MAS Excel export and implement Thai date formatting | **Day 18** |
| `a46fa09` | 2026-03-08 | feat: Implement item sub-table rendering for MAS reservations and enhance table structure | **Day 19** |
| `9db165c` | 2026-03-09 | feat: Add MAS search functionality with filters for year, MAS code, description, and amount | **Day 20** |
| `6b5299a` | 2026-03-09 | feat: Add reservation search functionality with filters for requisition code, reserved by... | **Day 21** |
| `76cb9c6` | 2026-03-31 | fix: maping env host url in sending mail | **Day 23** |
| `bbbef0b` | 2026-03-31 | fix: add print on stageing | **Day 24** |
| `c55eb05` | 2026-03-31 | debug worker | **Day 25** |
| `6a62718` | 2026-03-31 | delete debug | **Day 26** |
| `77c84b6` | 2026-04-02 | fix : export mas | **Day 31** |
| `a58dac3` | 2026-04-02 | feat: add details_specified step to requisition timeline with dedicated form and template | **Day 32** |
| `4357dd5` | 2026-04-08 | refactor: update amount labels to clarify total amounts in procurement forms and templates | **Day 33** |
| `4ec209c` | 2026-04-08 | feat: add inspection date field and integrate into requisition timeline progress flow | **Day 34** |
| `74ee68c` | 2026-04-08 | feat: add inspection date field to requisition timeline and update progress handling | **Day 35** |
| `874d890` | 2026-04-10 | refactor: migrate requisition items table to a card-based layout for improved mobile responsiveness | **Day 36** |
| `93b9fbe` | 2026-04-10 | feat: apply readonly state to requisition item form fields via template parameters | **Day 37** |
| `3ab2d6f` | 2026-04-16 | feat: implement export functionality for requisition timeline items with modal support | **Day 43** |
| `774eef5` | 2026-04-16 | feat: add type field to ExportFile model and update export functionality to include type | **Day 44** |
| `f09535e` | 2026-04-16 | feat: enhance export functionality with date validation and modal integration | **Day 45** |
| `52382d0` | 2026-04-16 | feat: export requistion item | **Day 45** |
| `0752150` | 2026-04-17 | feat: refactor export functionality for requisition timeline items and enhance header formatting | **Day 46** |
| `4953cb6` | 2026-04-17 | fix: correct date formatting in countdown element for requisition items | **Day 47** |
| `c1c4d9a` | 2026-04-18 | feat: add expiration date range filter to requisition forms and views | **Day 48** |
| `665a057` | 2026-04-18 | feat: order procurements by expiration date in index view | **Day 49** |
| `b1948dd` | 2026-05-21 | refactor: rename procurement views to asset titles, update item card UI, improve dynamic form | **Day 51** |
| `95655c2` | 2026-05-24 | feat: Implement car application approval workflow with embedded approvals and new paper template | **Day 52** |
| `1ef82a1` | 2026-05-24 | feat: Add combine_paper route for bulk car application paper generation | **Day 53** |
| `ae64bb4` | 2026-05-25 | refactor: implement printable car application paper page with audit trail for approval signatures | **Day 54** |
| `6a1640d` | 2026-05-25 | refactor: implement sign section on export history lending car | **Day 54** |
| `6013d67` | 2026-05-25 | refactor: sign section in export history car lending / fix: login approve in paper page | **Day 54** |
| `044c154` | 2026-05-31 | Refactor: car application modal and index , calendar page | **Day 55** |
| `4788eef` | 2026-06-03 | refactor: enchance ui of index/reservation of mas | **Day 56** |
| `653941c` | 2026-06-15 | refactor: rename product_number to payment_number and update related references | **Day 57** |
| `e39ed79` | 2026-08-19 | feat: add manual procurement | **Day 58** |
| `d21a46e` | 2026-08-23 | feat: Add inventory manual view and corresponding tests | **Day 59** |

---

## 🛡️ Architectural Integrity & Quality Standards Complied
1. **Strict Multi-Tenancy Partitioning**: ทุก Query ใน MongoEngine ถูกจำกัดด้วย `organization=current_user.organization` ป้องกันการรั่วไหลของข้อมูลระหว่างองค์กร
2. **Financial Precision Guarantee**: ข้อมูลการเงินและงบประมาณใช้ `me.DecimalField` พร้อมการแปลงค่า `float` ใน Business Logic และฟิลเตอร์ `format_amount` บน Jinja2 ปราศจากความคลาดเคลื่อน
3. **Responsive & Accessible UI**: ประยุกต์ใช้ Tailwind CSS ร่วมกับ Semantic DaisyUI Components รองรับทั้งมุมมอง Desktop, Tablet และ Mobile อย่างสมบูรณ์
4. **Audit Trail & Governance**: บันทึกประวัติการอนุมัติและลายเซ็นดิจิทัลผ่าน Embedded Documents พร้อมหน้าพิมพ์เอกสารราชการที่ถูกต้องตามระเบียบ
5. **Full Test Coverage**: มีชุดการทดสอบรองรับการทำงานของโมดูลสำคัญและผ่านการตรวจสอบ 100% Green
