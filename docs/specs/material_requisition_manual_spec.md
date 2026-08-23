# Specification: Material Requisition System User Manual (คู่มือการใช้งานระบบเบิกวัสดุ)

## 1. วัตถุประสงค์และภาพรวม (Objective & Overview)

เอกสารนี้กำหนดข้อกำหนดทางเทคนิค (Technical Specification) สำหรับการสร้างหน้า **"คู่มือการใช้งาน ระบบเบิกวัสดุและคลังพัสดุ (Material Requisition System)"** ในระบบ Kampan โดยมีมาตรฐานการออกแบบ UI/UX, โครงสร้างโค้ด และฟังก์ชันการทำงานเทียบเท่ากับคู่มือระบบยานพาหนะ (`vehicle_lending/car_manuals/index.html`) และระบบขอซื้อขอจ้าง (`procurement_manual_spec.md`)

### คุณสมบัติหลักที่ต้องมี
1. **ครอบคลุมครบทุกเมนูตาม Sidebar (Comprehensive Coverage):** รองรับทั้ง 9 กลุ่มงานหลัก 23 โมดูลย่อยของระบบเบิกวัสดุ
2. **Scroll-spy Navigation:** เมนูด้านข้าง (Sticky TOC) ไฮไลต์หัวข้อตามตำแหน่งการเลื่อนหน้า พร้อม Progress Bar แสดง % ความคืบหน้าการอ่านคู่มือ
3. **Role-Aware Content & Badges:** มีป้ายกำกับบทบาท (Role Badge) ที่เข้าถึงสิทธิ์ใช้งานในทุกโมดูลอย่างชัดเจน (`staff`, `head`/`endorser`, `supervisor supplier`, `admin`)
4. **Interactive Read-only Demos:** มีกล่องตัวอย่างหน้าจอ (Mockup UI) จำลองจากแบบฟอร์มและตารางจริงในระบบ (ปิดการรับ input ด้วย `pointer-events-none` และ `tabindex="-1"`)
5. **Print & Responsive Friendly:** รองรับการพิมพ์เอกสาร (Print CSS) และแสดงผลสมบูรณ์บนทุกขนาดหน้าจอด้วย Tailwind CSS และ DaisyUI

---

## 2. สถาปัตยกรรมและการเชื่อมต่อ (Architecture & Blueprint)

### 2.1 Route Handler
- **ไฟล์:** `kampan/web/views/inventories.py` (หรือ Blueprint ย่อย `manuals`)
- **URL Prefix:** `/inventories/manual` (เข้าถึงผ่าน `/inventories/manual?organization_id=...`)
- **การรักษาความปลอดภัย (Security / ACL):** ตรวจสอบสิทธิ์ด้วย `@acl.organization_roles_required("admin", "staff", "head", "endorser", "supervisor supplier")`

```python
from flask import Blueprint, render_template, redirect, url_for, request
from flask_login import login_required
from kampan.web import acl
from kampan import models

module = Blueprint("inventory_manuals", __name__, url_prefix="/inventories/manual")

@module.route("")
@login_required
@acl.organization_roles_required(
    "admin", "staff", "head", "endorser", "supervisor supplier"
)
def index():
    organization_id = request.args.get("organization_id")
    organization = models.Organization.objects(
        id=organization_id, status="active"
    ).first()
    if not organization:
        return redirect(url_for("dashboard.index"))

    return render_template(
        "/inventories/manual.html",
        organization=organization,
    )
```

### 2.2 โครงสร้างสารบัญ (Table of Contents - TOC)

```python
toc = [
    ("overview",                       "ph-users-three",      "ภาพรวมและบทบาทผู้ใช้งาน"),
    ("flow-main",                      "ph-flow-arrow",       "ขั้นตอนการทำงานภาพรวมทั้งระบบ"),
    # 1. แดชบอร์ด
    ("dashboard",                      "ph-chart-line-up",    "1. แดชบอร์ดภาพรวมคลังวัสดุ"),
    ("report-inventory-balances",      "ph-file-text",        "2. รายงานวัสดุคงเหลือ"),
    ("report-quarterly-balances",      "ph-calendar-blank",   "3. รายงานวัสดุคงเหลือตามช่วงไตรมาส"),
    ("report-custom-date-inventory",   "ph-funnel",           "4. รายงานเฉพาะวัสดุตามช่วงที่กำหนด"),
    ("notifications",                  "ph-bell",             "5. การแจ้งเตือนระบบ"),
    # 2. การจัดการวัสดุ
    ("items",                          "ph-package",          "6. จัดการข้อมูลวัสดุทั้งหมด"),
    ("categories",                     "ph-folders",          "7. จัดการหมวดหมู่วัสดุ"),
    ("suppliers",                      "ph-storefront",       "8. จัดการข้อมูลร้านค้า/คู่ค้า"),
    ("warehouses",                     "ph-warehouse",        "9. จัดการคลังวัสดุ"),
    # 3. การนำเข้าวัสดุ
    ("item-register-create",           "ph-tray-arrow-down",  "10. นำเข้าวัสดุเข้าคลัง"),
    ("item-registers",                 "ph-list-checks",      "11. รายการประวัตินำเข้าวัสดุ"),
    # 4. รูปแบบอีเมล
    ("email-templates",                "ph-envelope-simple",  "12. รูปแบบอีเมลแจ้งเตือน"),
    # 5. การเบิกวัสดุ
    ("item-orders",                    "ph-shopping-cart",    "13. คำสั่งเบิกวัสดุ (สร้างและติดตาม)"),
    ("item-checkouts",                 "ph-export",           "14. รายการนำวัสดุออก (ตัดสต็อก)"),
    # 6. การอนุมัติ
    ("approve-head",                   "ph-user-check",       "15. หัวหน้าฝ่ายอนุมัติคำสั่งเบิก (ขั้นที่ 1)"),
    ("approve-supervisor-supplier",    "ph-shield-check",     "16. หัวหน้าเจ้าหน้าที่พัสดุอนุมัติคำสั่งเบิก (ขั้นที่ 2)"),
    ("approve-head-inventory-lost",    "ph-warning-octagon",  "17. หัวหน้าพัสดุอนุมัติวัสดุชำรุด/สูญหาย/แก้ไข"),
    ("approve-admin",                  "ph-check-square",     "18. พัสดุอนุมัติคำสั่งเบิกและตัดสต็อก (ขั้นที่ 3)"),
    # 7. วัสดุชำรุด/สูญหาย/แก้ไข
    ("lost-breaks",                    "ph-first-aid-kit",    "19. การแจ้งวัสดุชำรุด/สูญหาย/แก้ไขสต็อก"),
    # 8. จัดการองค์กร
    ("divisions",                      "ph-tree-structure",   "20. จัดการแผนกและโครงสร้างฝ่าย"),
    ("org-users",                      "ph-users",            "21. จัดการสมาชิกสิทธิ์ขององค์กร"),
    ("org-detail",                     "ph-buildings",        "22. รายละเอียดข้อมูลองค์กร"),
    # 9. ข้อมูลผู้ใช้งาน
    ("user-profile",                   "ph-user-circle",      "23. ข้อมูลผู้ใช้งานส่วนบุคคล"),
    ("status-summary",                 "ph-path",             "ตารางสรุปสถานะคำสั่งเบิกและขั้นตอนดำเนินงาน"),
]
```

---

## 3. รายละเอียดเนื้อหาและฟอร์ม CRUD ในแต่ละโมดูล

### 0. ภาพรวมและบทบาทผู้ใช้งาน (`#overview`)
- **โครงสร้างกลุ่มงานในระบบ (9 กลุ่มงาน / 23 โมดูลย่อย):**
  1. **กลุ่มแดชบอร์ดและรายงาน:** สรุปภาพรวมคลัง รายงานคงเหลือ รายงานไตรมาส รายงานตามช่วงเวลา และระบบแจ้งเตือน (โมดูล 1-5)
  2. **กลุ่มจัดการข้อมูลพื้นฐานคลัง:** จัดการรายการวัสดุ หมวดหมู่ ร้านค้าคู่ค้า และตำแหน่งคลังวัสดุ (โมดูล 6-9)
  3. **กลุ่มการนำเข้าวัสดุ:** บันทึกรับวัสดุเข้าคลังและตรวจสอบประวัติการรับเข้า (โมดูล 10-11)
  4. **กลุ่มเทมเพลตแจ้งเตือน:** ตั้งค่ารูปแบบข้อความอีเมลแจ้งเตือนการเบิก (โมดูล 12)
  5. **กลุ่มคำขอเบิกและการตัดจ่าย:** สร้างคำขอเบิกวัสดุ ติดตามสถานะ และดูประวัติการจ่ายวัสดุออกจากคลัง (โมดูล 13-14)
  6. **กลุ่มสายการอนุมัติ 3 ขั้นตอน:** สายการอนุมัติคำสั่งเบิก (หัวหน้าฝ่าย -> หัวหน้าพัสดุ -> เจ้าหน้าที่พัสดุตัดสต็อก) (โมดูล 15-18)
  7. **กลุ่มการปรับปรุงและชำรุดสูญหาย:** แจ้งวัสดุชำรุด สูญหาย หรือปรับยอดสต็อกให้ตรงกับความเป็นจริง (โมดูล 19)
  8. **กลุ่มบริหารองค์กรและสมาชิก:** จัดการแผนก สิทธิ์สมาชิกองค์กร และข้อมูลหน่วยงาน (โมดูล 20-22)
  9. **กลุ่มบัญชีผู้ใช้:** จัดการข้อมูลส่วนตัวและรหัสผ่าน (โมดูล 23)

- **บทบาทและหน้าที่ของผู้ใช้งาน (Roles & Permissions):**
  - **staff (พนักงานผู้เบิก):** สร้างคำสั่งเบิกวัสดุ, เลือกรายการวัสดุ/จำนวน, ติดตามสถานะคำสั่งเบิก, ดูประวัติการเบิกของตนเอง, แจ้งเรื่องวัสดุชำรุด/สูญหาย
  - **head / endorser (หัวหน้าฝ่าย):** ตรวจสอบและอนุมัติคำสั่งเบิกขั้นที่ 1 สำหรับบุคลากรในสังกัดฝ่ายตนเอง หรือกดปฏิเสธพร้อมระบุเหตุผล
  - **supervisor supplier (หัวหน้าเจ้าหน้าที่พัสดุ):** ตรวจสอบและอนุมัติคำสั่งเบิกขั้นที่ 2 ในระดับภาพรวมองค์กร, อนุมัติการปรับปรุงวัสดุชำรุด/สูญหาย/แก้ไขสต็อก
  - **admin (เจ้าหน้าที่พัสดุ/ผู้ดูแลระบบ):** จัดการข้อมูลวัสดุ หมวดหมู่ คลัง ร้านค้า, บันทึกการนำเข้าวัสดุ, อนุมัติขั้นที่ 3 พร้อมตรวจสอบยอดคงเหลือจริงและตัดจ่ายวัสดุออกจากคลัง (Checkout), จัดการองค์กรและสิทธิ์สมาชิก

---

### 0.1 ขั้นตอนการทำงานภาพรวมทั้งระบบ (`#flow-main`)

#### ก. การเตรียมข้อมูลคลังวัสดุ (ทำโดย `admin`)
1. สร้างแผนก (`divisions`) และเพิ่มสมาชิกในองค์กรพร้อมกำหนดบทบาท
2. สร้างตำแหน่งคลังวัสดุ (`warehouses`), หมวดหมู่วัสดุ (`categories`), และรายชื่อร้านค้า (`suppliers`)
3. เพิ่มรายการวัสดุ (`items`) กำหนดรหัส หน่วยนับ (ชิ้น/ชุด) และจุดสั่งซื้อ Minimum Stock
4. นำเข้าวัสดุเข้าคลัง (`item_registers`) เพื่อสร้างยอดคงเหลือเริ่มต้น (`Inventory`)

#### ข. สายการเบิกและอนุมัติคำสั่งเบิกวัสดุ (Requisition Workflow)
1. **สร้างคำสั่งเบิก (`staff`):** เลือกรายการวัสดุ ระบุจำนวน (ชุด/ชิ้น) และเลือกหัวหน้าฝ่ายอนุมัติ -> สถานะคำสั่งเบิกเป็น `pending`
2. **อนุมัติขั้นที่ 1 (`head` / `endorser`):** หัวหน้าฝ่ายตรวจสอบความจำเป็น -> กดอนุมัติ เปลี่ยนสถานะเป็น `pending on supervisor supplier` (หากปฏิเสธ -> `denied`)
3. **อนุมัติขั้นที่ 2 (`supervisor supplier`):** หัวหน้าเจ้าหน้าที่พัสดุตรวจสอบภาพรวม -> กดอนุมัติ เปลี่ยนสถานะเป็น `pending on admin` (หากปฏิเสธ -> `denied`)
4. **อนุมัติขั้นที่ 3 & ตัดจ่ายสต็อก (`admin`):** เจ้าหน้าที่พัสดุตรวจสอบสินค้าในคลัง (`Inventory.remain`) -> ปรับจำนวนจ่ายจริงตามสต็อก -> กดอนุมัติ -> ระบบสร้าง `CheckoutItem` และหักลบยอดคงเหลือในคลัง -> เปลี่ยนสถานะเป็น `approved` (เสร็จสิ้น)

---

### โมดูล 1 — แดชบอร์ดภาพรวมคลังวัสดุ (`#dashboard`)
- **ผู้ใช้:** ทุกบทบาท (`admin`, `supervisor supplier`, `head`, `staff`)
- **View / Route:** `dashboard.index` (`GET /dashboard`)
- **ฟังก์ชันและการทำงาน:**
  - แสดงการ์ดสรุปตัวเลขสำคัญ (Stat Cards): จำนวนวัสดุทั้งหมด, ยอดรวมมูลค่าพัสดุในคลัง, รายการวัสดุคงเหลือต่ำกว่าจุดสั่งซื้อ (Low Stock), คำสั่งเบิกที่รอการอนุมัติ
  - กราฟแสดงสถิติการเบิกจ่ายวัสดุยอดนิยม (Top Requested Items) และแนวโน้มการเบิกจ่ายรายเดือน
  - ตารางสรุปรายการเบิกวัสดุล่าสุดพร้อม Badge แสดงสถานะ (`pending`, `approved`, `denied`)
- **Demo Block:** แดชบอร์ดการ์ดตัวเลข + กราฟแท่งสรุปสถิติ + ตารางคำขอเบิกล่าสุด

---

### โมดูล 2 — รายงานวัสดุคงเหลือ (`#report-inventory-balances`)
- **ผู้ใช้:** `admin`, `supervisor supplier`, `head`
- **View / Route:** `dashboard.report_inventory_balances` (`GET /dashboard/report_inventory_balances`)
- **ฟังก์ชันและการทำงาน:**
  - สรุปรายการวัสดุ ยอดรับเข้าสะสม ยอดเบิกจ่ายออกสะสม และยอดคงเหลือปัจจุบัน (`remain`) ทั้งแบบหน่วยชุดและชิ้น
  - คำนวณมูลค่าคงเหลือรวม (ตามราคาต่อหน่วยใน `DecimalField`)
  - ฟิลเตอร์กรองตามหมวดหมู่วัสดุ หรือ คลังจัดเก็บ พร้อมปุ่มส่งออกรายงานเป็นไฟล์ Excel / PDF
- **Demo Block:** ตารางรายงานวัสดุคงเหลือพร้อมคอลัมน์ยอดรับ-เบิก-คงเหลือ และมูลค่ารวม

---

### โมดูล 3 — รายงานวัสดุคงเหลือตามช่วงไตรมาส (`#report-quarterly-balances`)
- **ผู้ใช้:** `admin`, `supervisor supplier`
- **View / Route:** `dashboard.report_quarterly_inventory_balances` (`GET /dashboard/report_quarterly_inventory_balances`)
- **ฟังก์ชันและการทำงาน:**
  - รายงานเปรียบเทียบการเคลื่อนไหวของพัสดุรายไตรมาส (Q1: ต.ค.-ธ.ค., Q2: ม.ค.-มี.ค., Q3: เม.ย.-มิ.ย., Q4: ก.ค.-ก.ย.)
  - แสดงยอดคงเหลือยกมา ยอดนำเข้าระหว่างไตรมาส ยอดเบิกจ่ายระหว่างไตรมาส และยอดคงเหลือปลายไตรมาส
- **Demo Block:** ตารางรายงานจำแนกตามไตรมาส 1-4

---

### โมดูล 4 — รายงานเฉพาะวัสดุตามช่วงที่กำหนด (`#report-custom-date-inventory`)
- **ผู้ใช้:** `admin`, `supervisor supplier`
- **View / Route:** `dashboard.report_custom_date_inventory` (`GET /dashboard/report_custom_date_inventory`)
- **ฟังก์ชันและการทำงาน:**
  - ฟอร์มค้นหารายงานแบบกำหนดช่วงวันที่เริ่มต้น - วันที่สิ้นสุด (Custom Date Range Filter)
  - กรองเฉพาะหมวดหมู่ หรือ รายการวัสดุเฉพาะชิ้น เพื่อดูประวัติการเคลื่อนไหวสต็อก (Stock Movement Card)
- **Demo Block:** ฟอร์มเลือกช่วงวันที่ + ตารางประวัติการรับเข้าและเบิกออกรายวัน

---

### โมดูล 5 — การแจ้งเตือนระบบ (`#notifications`)
- **ผู้ใช้:** ทุกบทบาท
- **View / Route:** `notifications.index` (`GET /notifications`)
- **ฟังก์ชันและการทำงาน:**
  - แสดงรายการแจ้งเตือนส่วนบุคคล เช่น คำสั่งเบิกได้รับการอนุมัติ/ปฏิเสธ, มีคำสั่งเบิกใหม่รอการอนุมัติ (สำหรับ `head`/`admin`)
  - การแจ้งเตือนวัสดุใกล้หมดคลัง (Low Stock Threshold Alerts) สำหรับเจ้าหน้าที่พัสดุ
  - ปุ่มกด "ทำเครื่องหมายว่าอ่านแล้วทั้งหมด" (Mark all as read)
- **Demo Block:** รายการการแจ้งเตือนพร้อมสัญลักษณ์เวลา และไอคอนแยกประเภท

---

### โมดูล 6 — จัดการข้อมูลวัสดุทั้งหมด (`#items`)
- **ผู้ใช้:** `admin` (CRUD Full), `staff` (Read Only)
- **View / Route:** `items.index`, `items.create`, `items.edit`, `items.detail` (`/items`)
- **CRUD Operations:**
  - **Create / Edit:** แบบฟอร์มเพิ่ม/แก้ไขวัสดุ: รหัสวัสดุ, ชื่อวัสดุ, หมวดหมู่ (`Category`), คลังวัสดุ (`Warehouse`), หน่วยนับชุด (`set_unit`), หน่วยนับชิ้น (`piece_unit`), จำนวนชิ้นต่อชุด (`piece_per_set`), จุดสั่งซื้อ minimum, ราคาอ้างอิง, อัปโหลดรูปภาพวัสดุ
  - **Read:** ตารางรายการวัสดุทั้งหมดพร้อมภาพตัวอย่าง จำนวนคงเหลือปัจจุบัน (`get_amount_pieces()`) และสถานะ (`active`/`inactive`)
  - **Delete / Disable:** เปลี่ยนสถานะวัสดุเป็น `inactive` เพื่อป้องกันการเลือกเบิกใหม่โดยคงประวัติเดิมไว้
- **Demo Block:** ฟอร์มสร้าง/แก้ไขวัสดุ + ตารางรายการวัสดุพร้อม Badge สต็อก

---

### โมดูล 7 — จัดการหมวดหมู่วัสดุ (`#categories`)
- **ผู้ใช้:** `admin`
- **View / Route:** `categories.index`, `categories.create`, `categories.edit` (`/categories`)
- **CRUD Operations:**
  - **Create / Edit:** เพิ่ม/แก้ไขหมวดหมู่วัสดุ (เช่น วัสดุสำนักงาน, วัสดุคอมพิวเตอร์, วัสดุงานบ้านงานครัว) พร้อมรายละเอียดคำอธิบาย
  - **Read:** ตารางหมวดหมู่ทั้งหมดและจำนวนรายการวัสดุในแต่ละหมวด
  - **Delete:** ลบหมวดหมู่ (ตรวจสอบก่อนว่าไม่มีวัสดุเชื่อมโยงอยู่)
- **Demo Block:** ตารางหมวดหมู่วัสดุ + ฟอร์มเพิ่มหมวดหมู่

---

### โมดูล 8 — จัดการข้อมูลร้านค้า/คู่ค้า (`#suppliers`)
- **ผู้ใช้:** `admin`
- **View / Route:** `suppliers.index`, `suppliers.create`, `suppliers.edit` (`/suppliers`)
- **CRUD Operations:**
  - **Create / Edit:** บันทึกข้อมูลร้านค้า/บริษัทคู่ค้าผู้จัดจำหน่าย: ชื่อบริษัท/ร้านค้า, เลขประจำตัวผู้เสียภาษี, ที่อยู่, เบอร์โทรศัพท์, อีเมล, ชื่อผู้ติดต่อ
  - **Read:** ตารางค้นหารายชื่อร้านค้า พร้อมประวัติการสั่งซื้อนำเข้าวัสดุ
- **Demo Block:** ฟอร์มบันทึกข้อมูลร้านค้าคู่ค้า

---

### โมดูล 9 — จัดการคลังวัสดุ (`#warehouses`)
- **ผู้ใช้:** `admin`
- **View / Route:** `warehouses.index`, `warehouses.create`, `warehouses.edit` (`/warehouses`)
- **CRUD Operations:**
  - **Create / Edit:** สร้าง/แก้ไขตำแหน่งคลังวัสดุ (เช่น คลังพัสดุกลาง, คลังอาคาร A ชั้น 2, คลังวัสดุสำนักงาน)
  - **Read:** รายชื่อคลังจัดเก็บและจำนวนรายการวัสดุที่จัดเก็บในคลังนั้นๆ
- **Demo Block:** ตารางข้อมูลคลังวัสดุ

---

### โมดูล 10 — นำเข้าวัสดุเข้าคลัง (`#item-register-create`)
- **ผู้ใช้:** `admin`
- **View / Route:** `item_registers.create` (`GET/POST /item_registers/create`)
- **CRUD / Process Operations:**
  - **Create (Receive Stock):** ฟอร์มบันทึกการรับเข้าวัสดุ: เลือกพัสดุ/วัสดุ, เลือกร้านค้าผู้จัดจำหน่าย (`supplier`), กรอกเลขที่ใบสั่งซื้อ/ใบตรวจรับพัสดุ, วันที่นำเข้า, จำนวนนำเข้า (ระบุเป็นชุด และ ชิ้น), ราคาต่อหน่วยชุด/ชิ้น (บันทึกเป็น `DecimalField`), ล็อตสินค้า (Lot Number) และ วันหมดอายุ (ถ้ามี)
  - เมื่อกดบันทึก ระบบจะสร้างเอกสาร `ItemRegister` และเพิ่มยอดในโมเดล `Inventory` โดยอัตโนมัติ
- **Demo Block:** ฟอร์มนำเข้าวัสดุพร้อมคำนวณราคารวมอัตโนมัติ

---

### โมดูล 11 — รายการประวัตินำเข้าวัสดุ (`#item-registers`)
- **ผู้ใช้:** `admin`, `supervisor supplier`
- **View / Route:** `item_registers.index`, `item_registers.detail` (`/item_registers`)
- **CRUD Operations:**
  - **Read & Filter:** ตารางแสดงประวัติการนำเข้าวัสดุทั้งหมด กรองตามช่วงวันที่, ร้านค้า หรือรายการวัสดุ
  - **Detail:** ดูรายละเอียดใบนำเข้าพัสดุฉบับเต็ม พร้อมรายการวัสดุในล็อตนั้น
  - **Cancel / Void:** ยกเลิกใบนำเข้า (กรณีคีย์ข้อมูลผิด) เพื่อตัดยอดสต็อกจากคลังคืน
- **Demo Block:** ตารางรายการประวัตินำเข้าวัสดุ พร้อม Badge สถานะใบนำเข้า

---

### โมดูล 12 — รูปแบบอีเมลแจ้งเตือน (`#email-templates`)
- **ผู้ใช้:** `admin`
- **View / Route:** `email_templates.index`, `email_templates.edit` (`/email_templates`)
- **CRUD Operations:**
  - **Read / Edit:** ตั้งค่าข้อความและหัวข้ออีเมล (Email Subject & Body Template) ที่ส่งแจ้งเตือนในเหตุการณ์ต่างๆ เช่น แจ้งหัวหน้าฝ่ายอนุมัติ, แจ้งผู้เบิกเมื่อได้รับอนุมัติ, แจ้งเตือนของใกล้หมด
  - รองรับ Dynamic Placeholders เช่น `{user_name}`, `{order_number}`, `{created_date}`
- **Demo Block:** ฟอร์มแก้ไขเทมเพลตอีเมลพร้อมตัวอย่างการแทนที่ตัวแปร

---

### โมดูล 13 — คำสั่งเบิกวัสดุ (สร้างและติดตาม) (`#item-orders`)
- **ผู้ใช้:** `staff`, `head`, `supervisor supplier`, `admin`
- **View / Route:** `item_orders.index`, `item_orders.create`, `item_orders.detail`, `item_orders.edit` (`/item_orders`)
- **CRUD Operations:**
  - **Create (New Requisition Order):**
    - ผู้เบิกสร้างคำขอ เลือกหัวหน้าฝ่ายอนุมัติ (`head_endorser`)
    - เพิ่มรายการวัสดุที่ต้องการเบิกแบบ Dynamic Rows (เลือกพัสดุ, ระบุจำนวนชุด/ชิ้น, วัตถุประสงค์ในการเบิก)
    - ระบบตรวจสอบยอดสต็อกคงเหลือเบื้องหลัง หากขอเกินสต็อกจะแสดงคำเตือน
  - **Read / Tracking:** ตารางติดตามสถานะคำสั่งเบิกของตนเอง และของคนในฝ่าย
  - **Detail & Document:** ดูรายละเอียดคำสั่งเบิกและพิมพ์ใบขอเบิกพัสดุ (PDF/Print View)
  - **Cancel:** ยกเลิกคำขอเบิก (กระทำได้เฉพาะก่อนที่หัวหน้าฝ่ายจะอนุมัติ)
- **Demo Block:** ฟอร์มสร้างคำสั่งเบิกพัสดุ + รายการสิ่งของที่ขอเบิก

---

### โมดูล 14 — รายการนำวัสดุออก (ตัดสต็อก) (`#item-checkouts`)
- **ผู้ใช้:** `admin`, `supervisor supplier`
- **View / Route:** `item_checkouts.index`, `item_checkouts.detail` (`/item_checkouts`)
- **CRUD Operations:**
  - **Read:** ตารางประวัติการตัดจ่ายพัสดุจริงออกจากคลัง (`CheckoutItem`)
  - แสดงรายละเอียด: เลขที่คำสั่งเบิก, วันที่จ่ายออก, ผู้เบิก, รายการวัสดุ, จำนวนที่จ่ายจริง (ชุด/ชิ้น), ล็อตวัสดุที่ถูกตัดจ่าย, เจ้าหน้าที่ผู้จ่ายพัสดุ
- **Demo Block:** ตารางประวัติการจ่ายวัสดุออกพร้อมรายละเอียดล็อตสินค้า

---

### โมดูล 15 — หัวหน้าฝ่ายอนุมัติคำสั่งเบิก (ขั้นที่ 1) (`#approve-head`)
- **ผู้ใช้:** `head`, `endorser`
- **View / Route:** `approve_orders.endorser_index`, `endorser_approve`, `endorser_denied` (`/approve_orders/endorser`)
- **Action Operations:**
  - ตรวจสอบรายการคำสั่งเบิกของบุคลากรในฝ่ายตนเอง (สถานะ `pending`)
  - **กด "อนุมัติ" (`endorser_approve`):** ปรับสถานะคำขอเป็น `pending on supervisor supplier` และส่งคิวอีเมลแจ้งเตือนถึงหัวหน้าเจ้าหน้าที่พัสดุผ่าน Redis RQ
  - **กด "ปฏิเสธ" (`endorser_denied`):** ระบุเหตุผลการปฏิเสธ (`remark`) -> ปรับสถานะคำขอและรายการเป็น `denied`
- **Demo Block:** ตารางรายการคำขอรอการอนุมัติระดับหัวหน้าฝ่าย + ปุ่มอนุมัติ/ไม่อนุมัติ

---

### โมดูล 16 — หัวหน้าเจ้าหน้าที่พัสดุอนุมัติคำสั่งเบิก (ขั้นที่ 2) (`#approve-supervisor-supplier`)
- **ผู้ใช้:** `supervisor supplier`
- **View / Route:** `approve_orders.supervisor_supplier_index`, `supervisor_supplier_approve`, `supervisor_supplier_denied` (`/approve_orders/supervisor_supplier`)
- **Action Operations:**
  - ตรวจสอบคำสั่งเบิกที่ผ่านการอนุมัติจากหัวหน้าฝ่ายแล้ว (สถานะ `pending on supervisor supplier`)
  - **กด "อนุมัติ" (`supervisor_supplier_approve`):** ปรับสถานะเป็น `pending on admin` และส่งอีเมลถึงเจ้าหน้าที่พัสดุ
  - **กด "ปรับเปลี่ยนจำนวน" (`change_quantity`):** ปรับลดจำนวนพัสดุที่อนุญาตให้เบิกได้ตามความเหมาะสม
  - **กด "ปฏิเสธ" (`supervisor_supplier_denied`):** ระบุเหตุผล -> สถานะเปลี่ยนเป็น `denied`
- **Demo Block:** หน้าอนุมัติหัวหน้าพัสดุพร้อมช่องปรับเปลี่ยนจำนวนเบิก

---

### โมดูล 17 — หัวหน้าพัสดุอนุมัติวัสดุชำรุด/สูญหาย/แก้ไข (`#approve-head-inventory-lost`)
- **ผู้ใช้:** `supervisor supplier`, `admin`
- **View / Route:** `approve_orders.head_inventory_lost_break_approve_index` (`/approve_orders/head_inventory_lost_break`)
- **Action Operations:**
  - ตรวจสอบใบแจ้งคำขอตัดจำหน่าย/ปรับยอดวัสดุชำรุด สูญหาย หรือแก้ไขข้อมูลสต็อก (`LostBreakItem`)
  - **กด "อนุมัติ":** ยืนยันการตัดยอดพัสดุออกจากคลังถาวรตามรายการชำรุด/สูญหาย
  - **กด "ปฏิเสธ":** คืนรายการกลับสู่สถานะปกติพร้อมระบุเหตุผล
- **Demo Block:** ตารางรายการอนุมัติวัสดุชำรุด/สูญหาย

---

### โมดูล 18 — พัสดุอนุมัติคำสั่งเบิกและตัดสต็อก (ขั้นที่ 3) (`#approve-admin`)
- **ผู้ใช้:** `admin`
- **View / Route:** `approve_orders.admin_index`, `admin_approve`, `admin_denied` (`/approve_orders/admin`)
- **Action Operations:**
  - ตรวจสอบคำขอที่ผ่านการอนุมัติ 2 ขั้นแรก (สถานะ `pending on admin`)
  - **กด "อนุมัติและตัดจ่ายสต็อก" (`admin_approve`):**
    - ระบบตรวจสอบยอดสต็อกจริงจาก `Inventory.objects(item=item, remain__gt=0)`
    - ทำการหักลบยอดคงเหลือ `remain` ตามล็อต และสร้างบันทึก `CheckoutItem`
    - กำหนดเลขที่ใบเบิก Running Number (`ordinal_number`) และปรับสถานะเป็น `approved`
    - ส่งอีเมลแจ้งผู้เบิกให้มารับพัสดุ
  - **กด "ปฏิเสธ":** ปรับสถานะเป็น `admin denied`
- **Demo Block:** ตารางพัสดุอนุมัติขั้นสุดท้ายพร้อมปุ่มกดตัดจ่ายสต็อก

---

### โมดูล 19 — การแจ้งวัสดุชำรุด/สูญหาย/แก้ไขสต็อก (`#lost-breaks`)
- **ผู้ใช้:** `staff`, `admin`
- **View / Route:** `lost_breaks.index`, `lost_breaks.create`, `lost_breaks.detail` (`/lost_breaks`)
- **CRUD Operations:**
  - **Create:** ฟอร์มสร้างใบแจ้งวัสดุชำรุด/สูญหาย หรือขอปรับปรุงสต็อก: เลือกรายการวัสดุ/คลัง, ระบุประเภท (`damaged`, `lost`, `adjustment`), จำนวนชิ้น/ชุด, สาเหตุเหตุผล, และแนบรูปภาพหลักฐาน
  - **Read:** ตารางติดตามสถานะใบแจ้งชำรุดสูญหาย (รอหัวหน้าพัสดุอนุมัติ / อนุมัติแล้วตัดจำหน่าย / ปฏิเสธ)
- **Demo Block:** ฟอร์มแจ้งพัสดุชำรุดสูญหายพร้อมช่องแนบรูปภาพหลักฐาน

---

### โมดูล 20 — จัดการแผนกและโครงสร้างฝ่าย (`#divisions`)
- **ผู้ใช้:** `admin`
- **View / Route:** `divisions.index`, `divisions.create`, `divisions.edit` (`/divisions`)
- **CRUD Operations:**
  - **Create / Edit:** เพิ่มและแก้ไขรายชื่อแผนก/ฝ่ายในองค์กร (เช่น ฝ่ายบริหาร, ฝ่ายเทคโนโลยีสารสนเทศ, ฝ่ายพัสดุ)
  - **Read:** แสดงรายชื่อแผนก และจำนวนบุคลากรในสังกัด
- **Demo Block:** ตารางรายการแผนกภายในองค์กร

---

### โมดูล 21 — จัดการสมาชิกสิทธิ์ขององค์กร (`#org-users`)
- **ผู้ใช้:** `admin`
- **View / Route:** `organizations.users`, `organizations.add_user`, `organizations.edit_role` (`/organizations/users`)
- **CRUD Operations:**
  - **Read:** รายชื่อสมาชิกทั้งหมดในองค์กร
  - **Assign Roles & Division:** กำหนดบทบาทสิทธิ์ (`admin`, `supervisor supplier`, `head`, `endorser`, `staff`) และระบุการสังกัดแผนก (`division`)
- **Demo Block:** ตารางจัดการสมาชิกและสิทธิ์การใช้งาน (Roles Badge Dropdown)

---

### โมดูล 22 — รายละเอียดข้อมูลองค์กร (`#org-detail`)
- **ผู้ใช้:** `admin`
- **View / Route:** `organizations.detail`, `organizations.edit` (`/organizations/detail`)
- **CRUD Operations:**
  - **Read / Edit:** ดูและแก้ไขข้อมูลองค์กร: ชื่อหน่วยงานภาษาไทย/อังกฤษ, โลโก้หน่วยงาน, ที่อยู่, เบอร์โทรศัพท์ติดต่อ
- **Demo Block:** หน้าแสดงรายละเอียดข้อมูลองค์กร

---

### โมดูล 23 — ข้อมูลผู้ใช้งานส่วนบุคคล (`#user-profile`)
- **ผู้ใช้:** ทุกบทบาท
- **View / Route:** `accounts.profile`, `accounts.edit_profile` (`/accounts/profile`)
- **CRUD Operations:**
  - **Read / Edit:** ดูและแก้ไขข้อมูลส่วนตัว: ชื่อ-นามสกุล, เบอร์โทรศัพท์, รูปโปรไฟล์, เปลี่ยนรหัสผ่านเข้าใช้งานระบบ
- **Demo Block:** ฟอร์มแก้ไขข้อมูลผู้ใช้งานส่วนบุคคล

---

## 4. รายการ Demo Blocks ทั้งหมด (12 บล็อก)

1. `dashboard` - แดชบอร์ดสรุปสถิติคลัง การ์ดตัวเลข และกราฟเบิกจ่าย
2. `report-inventory-balances` - ตารางรายงานพัสดุคงเหลือและมูลค่ารวม
3. `items` - ฟอร์มเพิ่ม/แก้ไขรายการวัสดุ พร้อมตั้งค่าหน่วยนับ (ชุด/ชิ้น)
4. `item-register-create` - ฟอร์มบันทึกการนำเข้าวัสดุเข้าคลัง
5. `item-orders` - ฟอร์มสร้างคำสั่งเบิกพัสดุแบบ Dynamic Item Rows
6. `item-checkouts` - ตารางประวัติการตัดจ่ายวัสดุออกจากคลัง
7. `approve-head` - ตารางและ Modal อนุมัติคำขอเบิกระดับหัวหน้าฝ่าย
8. `approve-supervisor-supplier` - หน้าอนุมัติหัวหน้าเจ้าหน้าที่พัสดุพร้อมช่องปรับจำนวนเบิก
9. `approve-admin` - หน้าพัสดุอนุมัติขั้นสุดท้ายและตัดจ่ายสต็อกคงเหลือ
10. `lost-breaks` - ฟอร์มแจ้งพัสดุชำรุด/สูญหาย/ปรับยอดสต็อก
11. `org-users` - ตารางจัดการสมาชิกองค์กรและสิทธิ์ Roles
12. `email-templates` - ฟอร์มแก้ไขเทมเพลตอีเมลแจ้งเตือน

---

## 5. ตารางสรุปสถานะคำสั่งเบิกและขั้นตอนการดำเนินงาน (Status Summary Table)

| สถานะ (Status) | คำอธิบายภาษาไทย | บทบาทที่เกี่ยวข้อง | ขั้นตอนถัดไป |
| :--- | :--- | :--- | :--- |
| <span class="badge badge-warning">pending</span> | รอหัวหน้าฝ่ายอนุมัติ | `staff` (ผู้ขอ), `head` | หัวหน้าฝ่ายตรวจอนุมัติส่งต่อ หรือ ปฏิเสธ |
| <span class="badge badge-info">pending on supervisor supplier</span> | รอหัวหน้าเจ้าหน้าที่พัสดุอนุมัติ | `head`, `supervisor supplier` | หัวหน้าพัสดุตรวจอนุมัติส่งต่อ หรือ ปรับจำนวน |
| <span class="badge badge-accent">pending on admin</span> | รอเจ้าหน้าที่พัสดุอนุมัติและตัดจ่าย | `supervisor supplier`, `admin` | เจ้าหน้าที่พัสดุตรวจสอบสต็อกและตัดจ่ายพัสดุ |
| <span class="badge badge-success">approved</span> | อนุมัติและตัดจ่ายพัสดุสำเร็จ | ทุกบทบาท | ผู้ขอรับพัสดุออกจากคลัง (เสร็จสิ้น) |
| <span class="badge badge-error">denied</span> | คำขอถูกปฏิเสธ (ไม่อนุมัติ) | ทุกบทบาท | สิ้นสุดกระบวนการ (แสดงเหตุผลประกอบ) |
| <span class="badge badge-ghost">cancelled</span> | คำขอถูกยกเลิกโดยผู้ขอเบิก | `staff` | คำขอถูกยกเลิกก่อนการอนุมัติ |

---
*เอกสารนี้จัดทำขึ้นสำหรับเป็นมาตรฐานการพัฒนาคู่มือระบบเบิกวัสดุในโครงการ Kampan*
