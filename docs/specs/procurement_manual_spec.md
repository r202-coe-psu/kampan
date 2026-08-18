# Specification: Procurement & Hiring System User Manual (คู่มือการใช้งานระบบขอซื้อขอจ้าง)

## 1. วัตถุประสงค์และภาพรวม (Objective & Overview)

เอกสารนี้กำหนดข้อกำหนดทางเทคนิค (Technical Specification) สำหรับการสร้างหน้า **"คู่มือการใช้งาน ระบบขอซื้อขอจ้างและบริหารสัญญา (MA)"** ในระบบ Kampan โดยมีมาตรฐานการออกแบบ UI/UX, โครงสร้างโค้ด และฟังก์ชันการทำงานเทียบเท่ากับคู่มือระบบยานพาหนะ (`vehicle_lending/car_manuals/index.html`)

### คุณสมบัติหลักที่ต้องมี
1. **ครบถ้วนทุกฟอร์มและโมดูล (Comprehensive Coverage):** ครอบคลุมทั้ง 15 โมดูลและฟอร์ม CRUD ทั้งหมดของระบบขอซื้อขอจ้าง
2. **Scroll-spy Navigation:** เมนูด้านข้าง (Sticky TOC) ไฮไลต์หัวข้อตามตำแหน่งการเลื่อนหน้า พร้อม Progress Bar แสดง % ความคืบหน้า
3. **Role-Aware Content:** มีป้ายกำกับบทบาท (Role Badge) ที่เข้าถึงได้ชัดเจนในทุกโมดูล
4. **Interactive Read-only Demos:** มีกล่องตัวอย่างหน้าจอ (Mockup UI) จำลองจากแบบฟอร์มและตารางจริงในระบบ (ปิดการรับ input ด้วย `pointer-events-none` และ `tabindex="-1"`)
5. **Print & Responsive Friendly:** รองรับการพิมพ์ (Print CSS) และแสดงผลสมบูรณ์บนทุกขนาดหน้าจอด้วย Tailwind CSS และ DaisyUI

---

## 2. สถาปัตยกรรมและการเชื่อมต่อ (Architecture & Blueprint)

### 2.1 Route Handler
- **ไฟล์:** `kampan/web/views/procurement/manuals.py`
- **Blueprint:** `manuals` ภายใต้ `procurement` (เข้าถึงผ่าน `/procurement/manuals?organization_id=...`)
- **การรักษาความปลอดภัย (Security / ACL):** ตรวจสอบสิทธิ์ด้วย `@acl.organization_roles_required("admin", "staff", "head", "manager", "supervisor supplier")`

```python
from flask import Blueprint, render_template
from flask_login import login_required
from kampan.web import acl

module = Blueprint("manuals", __name__, url_prefix="/manuals")

@module.route("")
@login_required
@acl.organization_roles_required(
    "admin", "staff", "head", "manager", "supervisor supplier"
)
def index():
    organization = acl.get_organization()
    if not organization:
        return redirect(url_for("dashboard.index"))

    return render_template(
        "/procurement/requisitions/manual.html",
        organization=organization,
    )
```

### 2.2 โครงสร้างสารบัญ (Table of Contents - 18 รายการ)

```python
toc = [
    ("overview",           "ph-users-three",     "ภาพรวมและบทบาทผู้ใช้งาน"),
    ("flow-main",          "ph-flow-arrow",      "ขั้นตอนการทำงานภาพรวมทั้งระบบ"),
    ("upload-files",       "ph-upload-simple",   "1. อัปโหลดไฟล์นำเข้าข้อมูลแหล่งเงินและสัญญาบริการ"),
    ("products",           "ph-package",         "2. รายการสินค้าและสัญญาบริการ"),
    ("payment",            "ph-credit-card",     "3. บันทึกการชำระเงินสินค้า"),
    ("procurement-list",   "ph-clipboard-text",  "4. รายการสัญญาบริการที่ใกล้หมดอายุ"),
    ("renewal-requested",  "ph-arrow-clockwise", "5. รายการขอซื้อขอจ้าง"),
    ("non-renewal",        "ph-x-circle",        "6. รายการสัญญาบริการที่ไม่ต่ออายุ"),
    ("mas",                "ph-bank",            "7. แหล่งเงินงบประมาณระบบ MAS"),
    ("create-requisition", "ph-file-plus",       "8. สร้างและแก้ไขคำขอซื้อขอจ้าง"),
    ("head-approve",       "ph-shield-check",    "9. หัวหน้าฝ่ายอนุมัติขั้นที่ 1"),
    ("admin-approve",      "ph-stamp",           "10. เจ้าหน้าที่พัสดุอนุมัติและจองเงินงบประมาณ"),
    ("manager-approve",    "ph-user-check",      "11. ผู้จัดการอนุมัติขั้นสุดท้าย"),
    ("timeline",           "ph-list-checks",     "12. ติดตามความคืบหน้าการดำเนินงาน 8 ขั้นตอน"),
    ("timeline-items",     "ph-shopping-bag",    "13. รายการสินค้าในการดำเนินงานและส่งออกข้อมูล"),
    ("billing",            "ph-receipt",         "14. บันทึกการเบิกจ่ายงบประมาณ"),
    ("document",           "ph-file-pdf",        "15. เอกสารคำขอและพิมพ์รายงาน"),
    ("status",             "ph-path",            "ตารางสรุปสถานะคำขอและขั้นตอนการดำเนินงาน"),
]
```

---

## 3. รายละเอียดเนื้อหาและฟอร์ม CRUD ในแต่ละโมดูล

### 0. ภาพรวมและบทบาทผู้ใช้งาน (`#overview`)
- **โครงสร้างและกลุ่มงานหลักในระบบ (15 โมดูล / 5 กลุ่มงาน):**
  1. **กลุ่มนำเข้าและเตรียมข้อมูล:** อัปโหลดไฟล์ Excel สำหรับ MAS/MA และดาวน์โหลดแม่แบบมาตรฐาน (โมดูล 1)
  2. **กลุ่มทะเบียนสินค้าและสัญญาบริการ:** ทะเบียนพัสดุ ซอฟต์แวร์ สัญญาบริการ (MA) บันทึกการจ่ายเงิน และสัญญาใกล้หมดอายุ (โมดูล 2-6)
  3. **กลุ่มงบประมาณและแหล่งเงิน:** จัดการแหล่งเงิน MAS กำหนดวงเงินจัดสรร และประวัติการจองงบประมาณ (โมดูล 7)
  4. **กลุ่มคำขอและการอนุมัติ 3 ระดับ:** สร้างคำขอจัดซื้อจัดจ้าง และสายการอนุมัติ 3 ขั้นตอน (หัวหน้าฝ่าย -> เจ้าหน้าที่พัสดุ -> ผู้จัดการ) (โมดูล 8-11)
  5. **กลุ่มจัดซื้อและติดตามผลการดำเนินงาน:** ติดตามความคืบหน้า 8 ขั้นตอน รายการสินค้า บันทึกการเบิกจ่าย (Billing) และเอกสารรวม PDF (โมดูล 12-15)
- **บทบาทและหน้าที่ของผู้ใช้งาน (Roles & Permissions):**
  - **staff (พนักงาน):** สร้างคำขอซื้อ/จ้าง, แก้ไขคำขอของตน, กดขอต่ออายุสัญญา MA, ติดตามความคืบหน้า, พิมพ์เอกสาร
  - **head (หัวหน้าฝ่าย):** ตรวจสอบและอนุมัติคำขอขั้นที่ 1 สำหรับบุคลากรในฝ่ายเดียวกัน หรือกดปฏิเสธพร้อมระบุเหตุผล
  - **admin (เจ้าหน้าที่พัสดุ/ผู้ดูแล):** อัปโหลดไฟล์ Excel, จัดการ MAS, อนุมัติขั้นที่ 2 & จองเงิน MAS, มอบหมายผู้จัดการ, ขับเคลื่อน Timeline 8 ขั้นตอน, บันทึกการเบิกจ่าย (Billing), บันทึกการจ่ายเงิน
  - **manager (ผู้จัดการ/ทีมบริหาร):** อนุมัติขั้นสุดท้าย (ขั้นที่ 3) สำหรับคำขอที่ได้รับมอบหมาย เพื่อเปลี่ยนสถานะเป็น complete และเปิด Timeline อัตโนมัติ
  - **supervisor supplier (หัวหน้าฝ่ายบริหารจัดการ):** ตรวจสอบและดูภาพรวมคำขอจัดซื้อจัดจ้างทั้งหมดในหน่วยงาน
- **Note (warning):** ผู้ใช้งานต้องได้รับการกำหนดบทบาทและสังกัดฝ่ายก่อนจึงจะสร้างคำขอได้

### 0.1 ขั้นตอนการทำงานภาพรวมทั้งระบบ (`#flow-main`)
- **Flow ก. เตรียมข้อมูลก่อนใช้งาน:** อัปโหลดไฟล์ Excel -> ตั้งค่า MAS -> กำหนดวงเงิน -> สร้างทะเบียนสินค้า
- **Flow ข. กระบวนการคำขอ 1 ใบ:** สร้างคำขอ (`pending`) -> หัวหน้าอนุมัติ (`progress`) -> พัสดุอนุมัติ & จอง MAS -> ผู้จัดการอนุมัติ (`complete`) -> สร้าง Timeline 8 ขั้น -> บันทึกเบิกจ่าย Billing -> ตรวจรับ -> จ่ายเงิน -> ปิดโครงการ (`completed`)
- **Note (success):** ระบบส่งอีเมลแจ้งเตือนอัตโนมัติในทุกขั้นตอน

### โมดูล 1 — อัปโหลดไฟล์นำเข้าข้อมูลแหล่งเงินและสัญญาบริการ (`#upload-files`)
- **ผู้ใช้:** `admin`
- **View:** `admin.upload_files.index`, `admin.upload_files.upload_or_edit`, `download_mas_template`, `download_ma_template`
- **CRUD Operations:**
  - **Create / Upload:** ฟอร์มอัปโหลดไฟล์ Excel (`.xlsx`) สำหรับนำเข้าข้อมูลงบประมาณ MAS หรือสัญญาบริการ MA พร้อมเลือกหมวดหมู่ รองรับการอัปโหลดหลายไฟล์พร้อมกัน
  - **Read:** ตารางรายการไฟล์ สถานะการตรวจสอบ (`waiting`, `failed`, `completed`) แสดงข้อผิดพลาด (Error Messages)
  - **Process (Redis Job):** ปุ่ม "ประมวลผล" เพื่อส่งไฟล์เข้าคิวงาน Background Worker (`save_mas_db`, `save_ma_db`)
  - **Template:** ปุ่ม "ดาวน์โหลดเทมเพลต" (เปิดหน้าต่างเลือก "Template แหล่งเงิน (MAS)" หรือ "Template MA (Procurement)")
  - **Delete:** ลบประวัติไฟล์ที่ไม่ต้องการ
- **Demo:** ฟอร์มอัปโหลดไฟล์ + ตารางสถานะการประมวลผล + ปุ่มดาวน์โหลดเทมเพลต
- **Note (info):** การประมวลผลไฟล์ขนาดใหญ่จะทำงานเบื้องหลังผ่าน Redis Worker เพื่อความรวดเร็ว

### โมดูล 2 — รายการสินค้าและสัญญาบริการ (`#products`)
- **ผู้ใช้:** `admin`, `staff`, `head`, `manager`
- **View:** `procurement.products.index`, `procurement.products.create`, `procurement.products.edit_image`
- **CRUD Operations:**
  - **Create:** ฟอร์มเพิ่มสินค้า/สัญญาใหม่ (`create.html`)
    - ฟิลด์: ชื่อพัสดุ/บริการ, หมวดหมู่, เลขที่เบิกจ่ายหลายเลข (`product_numbers`), เลขที่ครุภัณฑ์หลายเลข (`asset_codes`), วันที่เริ่มต้น-สิ้นสุด, วงเงิน, บริษัทคู่ค้า, ผู้รับผิดชอบหลายคน (`responsible_by`), อัปโหลดรูปภาพ
  - **Read:** ตารางสินค้าพร้อมตัวกรอง (ชื่อ, หมวดหมู่, สถานะจ่ายเงิน) และ Status Count Badges
  - **Update / Edit Image:** ฟอร์มเปลี่ยนรูปภาพสินค้า (`edit_image.html`)
  - **Template:** ดาวน์โหลดแม่แบบ Excel สินค้า
- **Demo:** ตารางรายการสินค้า + status count badges + ปุ่ม action
- **Note (info):** สินค้าในหน้านี้คือพัสดุและบริการที่จัดซื้อสำเร็จแล้ว

### โมดูล 3 — บันทึกการชำระเงินสินค้า (`#payment`)
- **ผู้ใช้:** `admin`
- **View:** `procurement.payment.index`, `procurement.payment.set_paid`
- **CRUD Operations:**
  - **Create/Update Payment:** บันทึกการชำระเงินสำหรับสัญญา/สินค้า: งวดที่ชำระ, วันที่ชำระ, เลขที่ใบสำคัญจ่าย, จำนวนเงินที่ชำระ, หมายเหตุ
  - **Read:** ตารางประวัติการจ่ายเงินทั้งหมดของสินค้านั้น ยอดรวมที่ชำระแล้ว และยอดคงเหลือ
  - **Status Update:** ปรับสถานะการชำระเงิน (`paid`, `waiting`, `expired`)
- **Demo:** ฟอร์มบันทึกการชำระเงินและตารางประวัติงวดการจ่าย
- **Note (info):** การบันทึกการชำระเงินจะช่วยให้ระบบสรุป Status Badges ในหน้ารายการสินค้าได้อย่างแม่นยำ

### โมดูล 4 — รายการสัญญาบริการที่ใกล้หมดอายุ (`#procurement-list`)
- **ผู้ใช้:** `admin`, `staff`
- **View:** `procurement.requisitions.index`
- **CRUD / Actions:**
  - **Read & Filter:** กรองช่วงวันหมดอายุ (expired, 1 เดือน, 3 เดือน, 6 เดือน, 1 ปี)
  - **Action - ขอต่ออายุ:** Modal ยืนยันขอต่ออายุ -> สร้าง Requisition พร้อมรหัสอัตโนมัติ และเปลี่ยนสถานะ MA เป็น `renewal-requested`
  - **Action - ไม่ต่ออายุ:** Modal ยืนยันไม่ต่ออายุ -> เปลี่ยนสถานะเป็น `disactive`
- **Demo:** ตารางรายการ MA พร้อม Countdown Badge และปุ่มต่ออายุ/ไม่ต่ออายุ

### โมดูล 5 — รายการขอซื้อขอจ้าง (`#renewal-requested`)
- **ผู้ใช้:** ทุกบทบาท (`staff`, `head`, `admin`, `manager`)
- **View:** `procurement.requisitions.renewal_requested`
- **โครงสร้างหน้าจอ:**
  1. ส่วนรออนุมัติหัวหน้าฝ่าย (สำหรับ `head`)
  2. ส่วนรออนุมัติผู้จัดการ (สำหรับ `manager`)
  3. ส่วนรายการที่ผู้จัดการส่งแล้ว
  4. ตารางรายการขอซื้อขอจ้างทั้งหมด
- **Demo:** ตาราง Requisitions พร้อมสถานะอนุมัติแยกตามบทบาท

### โมดูล 6 — รายการสัญญาบริการที่ไม่ต่ออายุ (`#non-renewal`)
- **ผู้ใช้:** `admin`, `staff`
- **View:** `procurement.requisitions.non_renewal`
- **CRUD Operations:** ดูประวัติและกรองรายการสัญญาที่สิ้นสุดแล้วและไม่ต่ออายุ (สถานะ `disactive`)
- **Demo:** ตารางรายการ MA ที่ไม่ต่ออายุ

### โมดูล 7 — แหล่งเงินงบประมาณระบบ MAS (`#mas`)
- **ผู้ใช้:** `admin`
- **View:** `admin.mas.index`, `admin.mas.create_or_edit`, `admin.mas.reservation`, `export_excel`
- **CRUD Operations:**
  - **Create / Edit:** ฟอร์มสร้าง/แก้ไขแหล่งเงิน MAS (`create_or_edit.html`) (รหัส MAS, คำอธิบาย, วงเงินรวม `total_amount`)
  - **Read:** ตาราง MAS แสดงยอดวงเงินรวม, วงเงินที่จองไว้ (`reserved`), และวงเงินคงเหลือ (`remaining`)
  - **Delete:** ลบแหล่งเงิน MAS
  - **Reservations:** หน้ารายการจองเงิน (`reservation.html`) ตรวจสอบว่าคำขอใดกำลังจองยอดเงินนี้อยู่
  - **Export:** ส่งออกข้อมูล MAS เป็น Excel
- **Demo:** ตาราง MAS + สรุปยอดวงเงิน 3 ช่อง + ตาราง Reservation
- **Note (warning):** ต้องสร้าง MAS และกำหนดยอดเงินก่อนเริ่มการอนุมัติของพัสดุ

### โมดูล 8 — สร้างและแก้ไขคำขอซื้อขอจ้าง (`#create-requisition`)
- **ผู้ใช้:** `staff`, `head`, `admin`
- **View:** `procurement.requisition.create` / `edit`
- **CRUD Operations:**
  - **Create / Edit:** แบบฟอร์มขอซื้อขอจ้าง (`create_or_edit.html`):
    - รหัสคำขอ Running number อัตโนมัติ (`0001/2568`)
    - ผู้ขอซื้อ ดึงจาก `current_user` อัตโนมัติ
    - Dynamic Items: เพิ่ม/ลบรายการสิ่งของ (ชื่อ, ประเภท, จำนวน, หน่วย, ราคา/หน่วย, รวม)
    - แนบไฟล์ TOR และใบเสนอราคา QT (PDF)
    - Dynamic Committees: เพิ่ม/ลบรายชื่อกรรมการ 3 ชุด (กำหนดคุณลักษณะ, จัดซื้อจัดจ้าง, ตรวจรับพัสดุ)
  - **Delete / Cancel:** ยกเลิกคำขอ
- **Demo:** ฟอร์มสร้างคำขอพร้อม Dynamic Item Rows และ Committee Rows

### โมดูล 9 — หัวหน้าฝ่ายอนุมัติขั้นที่ 1 (`#head-approve`)
- **ผู้ใช้:** `head`, `admin`
- **View:** `procurement.requisitions.renewal_requested` (Head section) & `action`
- **Action Operations:**
  - ตรวจสอบคำขอของบุคลากรในฝ่ายเดียวกัน
  - กด **"อนุมัติ"** -> เปลี่ยนสถานะเป็น `progress` และส่งต่อพัสดุ
  - กด **"ปฏิเสธ"** พร้อมระบุเหตุผล (`remark`) -> สถานะเป็น `incomplete`

### โมดูล 10 — เจ้าหน้าที่พัสดุอนุมัติและจองเงินงบประมาณ (`#admin-approve`)
- **ผู้ใช้:** `admin`
- **Action Operations / Modal:**
  - เลือกแหล่งเงิน MAS (Single / Multi-MAS)
  - กรอกจำนวนเงินที่จอง (`reserved_amount`)
  - เลือกผู้จัดการที่มอบหมาย (`selected_manager`) พร้อมระบุสถานะรักษาการ (`is_acting`)
  - กดอนุมัติเพื่อสร้าง `Reservation` และล็อกวงเงินใน MAS
- **Demo:** Modal อนุมัติของพัสดุพร้อมช่องจัดสรร MAS และเลือกผู้จัดการ

### โมดูล 11 — ผู้จัดการอนุมัติขั้นสุดท้าย (`#manager-approve`)
- **ผู้ใช้:** `manager`
- **Action Operations:**
  - ตรวจสอบคำขอที่ได้รับมอบหมาย
  - กด **"อนุมัติ"** -> ครบ 3 ขั้น -> สถานะเป็น `complete` -> ระบบสร้าง `RequisitionTimeline` อัตโนมัติ
  - กด **"ปฏิเสธ"** พร้อมระบุเหตุผล -> สถานะเป็น `incomplete`

### โมดูล 12 — ติดตามความคืบหน้าการดำเนินงาน 8 ขั้นตอน (`#timeline`)
- **ผู้ใช้:** `admin` (แก้ไข), `staff` (ดู)
- **View:** `procurement.requisition_timeline.index`, `add_progress`, `details_specified`, `completed_submit`, `cancel`
- **8 ขั้นตอนและการดำเนินงาน:**
  1. `request_created`: สร้างอัตโนมัติเมื่อผู้จัดการอนุมัติ
  2. `vendor_contacted`: ติดต่อผู้ขายแล้ว
  3. `details_specified`: ฟอร์มระบุรายละเอียดคุณลักษณะและขอบเขตงาน (`details_specified.html`)
  4. `order_confirmed`: ยืนยันคำสั่งซื้อ (เปิดฟอร์ม Billing)
  5. `awaiting_delivery`: บันทึกวันที่ส่งมอบ (`delivery_date`)
  6. `inspection`: บันทึกวันที่ตรวจรับ (`inspection_date`)
  7. `payment_processed`: ดำเนินการชำระเงิน
  8. `completed`: ฟอร์มยืนยันเสร็จสิ้นโครงการ (`completed_submit.html`)
  - **Cancel:** กดยกเลิกโครงการพร้อมระบุเหตุผล -> ระบบคืนเงินจอง MAS อัตโนมัติ
- **Demo:** Progress Stepper 8 ขั้น + ปุ่มเลื่อนขั้นสถานะ

### โมดูล 13 — รายการสินค้าในการดำเนินงานและส่งออกข้อมูล (`#timeline-items`)
- **ผู้ใช้:** `admin`, `staff`
- **View:** `procurement.requisition_timeline_items.index`, `export_excel_modal`, `export_excel`
- **CRUD Operations:**
  - **Read & Filter:** ดูรายการสิ่งของทั้งหมดที่อยู่ระหว่างจัดซื้อตาม Timeline
  - **Export:** ส่งออกข้อมูลรายการสิ่งของออกเป็นไฟล์ Excel ตามช่วงเวลา
- **Demo:** ตารางรายการสิ่งของใน Timeline + Modal ส่งออก Excel

### โมดูล 14 — บันทึกการเบิกจ่ายงบประมาณ (`#billing`)
- **ผู้ใช้:** `admin`
- **View:** `procurement.requisition_timeline.billing_modal` / `billing.html`
- **CRUD Operations:**
  - เปิดได้เฉพาะเมื่อ Timeline อยู่ที่ขั้น `order_confirmed`
  - กรอกวิธีการจัดซื้อ (`purchase_method`) และผู้ชนะการเสนอราคา (`quotation_winner`)
  - กรอกจำนวนเงินที่ใช้จริง (`actual_amount`) และจำนวนชิ้น (`actual_quantity`) แยกตาม Item x MAS Allocation
  - เมื่อบันทึก -> ตัดยอดจริงจาก Reservation และเลื่อน Timeline ไป `awaiting_delivery` อัตโนมัติ
- **Demo:** ฟอร์มบันทึกการเบิกจ่ายพร้อมตารางจัดสรร MAS

### โมดูล 15 — เอกสารคำขอและพิมพ์รายงาน (`#document`)
- **ผู้ใช้:** ทุกบทบาท
- **View:** `procurement.requisition.document`, `download_all`
- **Operations:**
  - ดูเอกสารคำขอรูปแบบทางการ (Print Preview)
  - แสดงรายชื่อกรรมการ 3 ชุด และลายมือชื่ออิเล็กทรอนิกส์
  - รวมไฟล์คำขอ + TOR + QT เป็น PDF รวม 1 ฉบับ

### ตารางสรุปสถานะคำขอและขั้นตอนการดำเนินงาน (`#status`)
- ตารางสรุปสถานะทั้งหมด: `pending`, `progress`, `complete`, `incomplete`, `cancelled`, `renewal-requested`, `disactive` และสถานะ 8 ขั้นของ Timeline

---

## 4. รายการ Demo Blocks ทั้งหมด (10 บล็อก)

1. `upload-files` - ฟอร์มอัปโหลดไฟล์ Excel + ตารางประวัติการประมวลผล
2. `products` - ตารางรายการสินค้า + Status Count Badges + ปุ่ม Action
3. `payment` - ฟอร์มบันทึกการชำระเงินและตารางประวัติงวดการจ่าย
4. `procurement-list` - ตารางรายการ MA พร้อม Countdown Badge + ปุ่มต่ออายุ/ไม่ต่ออายุ
5. `renewal-requested` - ตารางรายการขอซื้อขอจ้าง + ส่วนอนุมัติแยกตามบทบาท
6. `mas` - ตารางแหล่งเงิน MAS + สรุปยอดวงเงิน 3 ช่อง + ตาราง Reservation
7. `create-requisition` - ฟอร์มสร้างคำขอซื้อ/จ้าง พร้อม Dynamic Items และ คณะกรรมการ 3 ชุด
8. `admin-approve` - Modal พัสดุอนุมัติ & จัดสรรงบประมาณ MAS + มอบหมายผู้จัดการ
9. `timeline` - Progress Stepper 8 ขั้น + ปุ่มเลื่อนขั้นสถานะ
10. `billing` - ฟอร์มบันทึกการเบิกจ่ายพร้อมตารางจัดสรร Item × MAS Allocation
