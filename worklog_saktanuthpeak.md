# สรุปงานที่ทำ — บัญชี saktanuthpeak (โปรเจกต์ kampan)

ที่มา: รวบรวมจาก `git log` ทั้งหมดของบัญชีนี้ (author = saktanuthpeak / SaktanuthPeak / Saktanuth Praditukrit) ตั้งแต่ commit แรกสุดที่พบ (2025-07-31) ถึงล่าสุด (2026-08-18) แล้ว **จัดกลุ่มงานใหม่ให้อยู่ในทั้งหมด 38 วัน** โดยกำหนดให้ทุกวันมีชั่วโมงทำงาน **6 ชม. เท่ากันทุกวัน** งานของบางวันที่มีปริมาณน้อยถูกนำไปรวมไว้ในวันอื่นที่เหมาะสมเพื่อให้ยอดวันทำงานรวมเท่ากับ 38 วันตามที่ต้องการ เรียงลำดับจาก**วันก่อนไปวันหลังสุด** แต่ละงานมีแท็ก `[module]` บอกว่าอยู่ในส่วนไหนของโค้ด (อ้างอิงจาก path ไฟล์ที่ commit จริงแก้ไข)

รวมทั้งหมด **38 วัน × 6 ชม. = 228 ชม.**

---

## 2025-08-25 (6 ชม.)
- จำกัดชนิดไฟล์อัปโหลดให้เป็น .xlsx เท่านั้น `[procurement/products]`
- ปรับ checkbox ผู้รับผิดชอบและ styling `[procurement/products]`
- เพิ่มการตรวจสอบรูปภาพและ error handling ในฟอร์ม `[procurement/products]`

## 2025-10-03 (6 ชม.)
- เพิ่ม filter ปีในหน้า procurement/index `[procurement]`
- ปรับหัวตารางและรูปแบบการแสดงปี `[procurement/macros]`
- ปรับหัวตารางในส่วนประวัติการชำระเงิน `[procurement/payment]`
- เพิ่มการตรวจสอบและ error handling สำหรับยอดชำระเงินและเลขสินค้า `[procurement/payment]`
- ปรับรูปแบบวันที่และการเรียงลำดับในตารางจัดซื้อ `[procurement/macros]`

## 2025-10-09 (6 ชม.)
- แก้รูปแบบปีในตารางประวัติ `[procurement/macros]`
- แก้ฟอร์มยอดล่าสุดให้เป็น readonly ในหน้าชำระเงิน `[procurement/payment]`

## 2025-10-12 (6 ชม.)
- เพิ่มส่วนอัปโหลดสำหรับงานจัดซื้อและ MAS `[procurement/upload_files, mas]`

## 2025-10-27 (6 ชม.)
- แก้ datatype ในคำขอ, แก้ชื่อฟิลด์ในไทม์ไลน์คำขอ `[procurement/requisitions]`
- เพิ่ม filter ตาม progress และ choice ใน requisition-progress, ลบ view function ที่ไม่ใช้ `[procurement/requisitions]`
- แก้ query และ pagination `[procurement/requisitions]`
- ส่งอีเมลให้หัวหน้า supplier `[procurement/suppliers]`

## 2025-11-03 (6 ชม.)
- ส่งอีเมลยกเลิกให้ผู้ใช้ที่เกี่ยวข้อง `[procurement/requisitions]`
- เพิ่ม filter ตาม role หัวหน้า `[procurement]`

## 2025-11-20 (6 ชม.)
- แก้ sidebar html `[procurement/base]`
- สร้าง route เริ่มต้นสำหรับยกเลิกคำขอ `[procurement/requisitions]`

## 2026-02-16 (6 ชม.)
- แก้ไขฟิลด์/ฟอร์ม/UI ในระบบ MAS `[procurement/mas]`
- เพิ่มหน้าการจอง (reservation) ใน MAS และ flow การจองในหน้าแอดมิน `[procurement/mas]`
- เพิ่ม pagination ใน MAS/renewal requested, เพิ่ม script สำหรับ init requisitions `[procurement/mas, procurement/requisitions]`
- แก้รายการฟอร์ม MA `[procurement/mas]`
- เพิ่ม block title `[procurement/products]`
- แก้ pagination `[procurement/mas]`
- เพิ่มฟิลด์ is editable ให้แก้ไขไม่ได้เมื่อมีการมอบหมายการจองแล้ว `[procurement/mas]`

## 2026-02-19 (6 ชม.)
- Refactor ระบบ MAS ให้มีฟังก์ชันการทำงานสมบูรณ์ขึ้น `[procurement/mas]`
- แก้ไขเทมเพลตอีเมลยกเลิก `[procurement/requisitions]`

## 2026-02-25 (6 ชม.)
- Refactor components ของฟอร์มในงานจัดซื้อ `[procurement]`
- เพิ่มตารางยืนยันสำหรับหัวหน้า supplier `[procurement/suppliers]`

## 2026-02-27 (6 ชม.)
- แก้ div หน้า index ของใบเบิกรถ `[vehicle_lending/car_applications]`
- เพิ่มฟอร์มรับส่งสนามบิน, แก้การแสดงผลตาราง, แก้บั๊กหน้า index `[vehicle_lending/car_applications]`
- ปรับปรุง progress เริ่มต้นของคำขอ (requisition) `[procurement/requisitions]`
- เพิ่ม modal แจ้งอัปโหลดสำเร็จ `[procurement/products]`
- เพิ่มระบบ drag-and-drop อัปโหลดไฟล์พร้อม progress indicator และ toast แจ้งผล `[procurement/products]`
- ปรับ layout และ styling ของฟอร์มกรองและปุ่มในหน้าสินค้า `[procurement/products]`

## 2026-03-05 (6 ชม.)
- เพิ่มฟังก์ชัน hash และฟิลด์ hashed ใน requisition timeline logs `[procurement/requisition_timeline]`
- เพิ่มแถบค้นหาสำหรับคำขอต่ออายุ `[procurement/requisitions]`
- แก้ design `[procurement/requisitions]`
- เพิ่มแถบค้นหาในไทม์ไลน์คำขอและหน้าคำขอต่ออายุ `[procurement/requisitions]`

## 2026-03-06 (6 ชม.)
- Hotfix ฟอร์ม `[procurement/macros]`
- แก้ไขข้อความในหน้าเว็บ `[procurement/macros]`
- Refactor การอัปโหลดไฟล์ mas และงานจัดซื้อ `[procurement/upload_files, mas]`
- เปลี่ยนฟังก์ชัน util สำหรับอัปโหลด excel, เพิ่ม error message `[procurement/upload_files]`
- Merge งานจาก develop `[merge, ไม่มีการแก้ไฟล์]`

## 2026-03-09 (6 ชม.)
- เพิ่ม modal เสร็จสมบูรณ์สำหรับคำขอจัดซื้อ `[procurement/requisitions]`
- เพิ่มสถานะเสร็จสมบูรณ์ในปฏิทินการใช้รถ `[vehicle_lending/car_applications]`
- ปรับ modal ให้ดูอย่างเดียวได้ พร้อมปุ่มสถานะเสร็จสมบูรณ์ `[procurement/macros]`
- เพิ่มฟังก์ชันเลือกผู้จัดการที่ทำหน้าที่แทน (acting) ในกระบวนการคำขอ `[procurement/requisitions]`

## 2026-03-17 (6 ชม.)
- เพิ่มการบันทึกเลขไมล์ล่าสุดของรถและใบเบิกรถ `[vehicle_lending]`
- เพิ่มฟอร์มกรองวันที่ในหน้าประวัติการใช้รถ `[vehicle_lending/history_car_lending]`
- ปรับ indentation ของ modal ในตารางสินค้า `[procurement/macros]`
- เปลี่ยน modal เสร็จสมบูรณ์เป็นหน้ายื่นคำขอที่เสร็จสมบูรณ์ พร้อมส่วนรายการสินค้า `[procurement/macros]`
- ปรับปรุงฟอร์มคำขอให้ใช้ shared fields และเลือกผู้ตอบกลับ `[procurement/requisitions]`

## 2026-03-19 (6 ชม.)
- ปรับฟิลด์ประเภทรับส่งสนามบินให้เป็น optional, แก้ label ภาษาไทยในตารางรถ `[vehicle_lending]`
- แก้ url ให้ใช้ admin prefix สำหรับ route MAS `[procurement/mas]`
- แก้ url redirect ให้ใช้ admin prefix สำหรับงานจัดซื้อ `[procurement]`
- เพิ่มสถานะใน tor_year, ลบ tor-year โดยตั้งสถานะเป็น disactive `[procurement/tor_years]`
- เพิ่มฟังก์ชัน copy/backup จาก tor ที่มีอยู่ `[procurement/tor_years]`

## 2026-03-31 (6 ชม.)
- แก้ parameter ของฟังก์ชันส่งอีเมลให้คนขับ `[vehicle_lending]`
- แก้การสร้างเลขคำขอถัดไป `[procurement/requisitions]`
- แก้ url ของ sidebar `[procurement]`
- ปรับรูปแบบเลขคำขอ, แก้ url ลิงก์ในอีเมล `[procurement/requisitions]`
- เพิ่มโมดูล car tasks สำหรับจัดการการคืนรถและบันทึกเลขไมล์ ปรับประวัติการใช้รถให้แสดงใบเบิกที่เสร็จสมบูรณ์ `[vehicle_lending/car_tasks]`
- แก้ url เทมเพลตอีเมล `[procurement/requisitions]`

## 2026-04-01 (6 ชม.)
- Merge งานจาก main `[merge, ไม่มีการแก้ไฟล์]`
- เพิ่ม hide_label ใน macro ฟอร์ม, ปรับ UI ตาราง item คำขอ `[procurement/requisition_timeline]`
- เพิ่มฟังก์ชันหน้าฟอร์มที่เสร็จสมบูรณ์ และเลข running number `[procurement/requisition_timeline]`

## 2026-04-02 (6 ชม.)
- เริ่มต้นชุด agent/skill definitions และเอกสารอ้างอิงสำหรับ workflow ออกแบบ/พัฒนา `[dev-tooling/skills]`
- Refactor UI หน้าสินค้าในงานจัดซื้อ และ select field components `[procurement/products]`
- แก้ table design หน้าสินค้า `[procurement/products]`
- Refactor ฟอร์มค้นหาคำขอให้ใช้ components ร่วม `[procurement/requisitions]`
- เพิ่ม filter คำขอในหน้า index และหน้าคำขอต่ออายุ `[procurement/requisitions]`

## 2026-04-03 (6 ชม.)
- สร้างฟอร์มกรองไทม์ไลน์คำขอ `[procurement/requisition_timeline]`
- เพิ่มปุ่มยกเลิกคำขอ `[procurement/requisitions]`
- เปลี่ยนมาใช้ wtForm แทน request.form `[procurement]`
- เพิ่ม modal แสดงเหตุผลใน progress คำขอ `[procurement/requisitions]`
- เพิ่มการตรวจสอบค่าตอนสร้างงานจัดซื้อ `[procurement]`
- แก้ดีไซน์ปุ่มในตาราง tor years `[procurement/tor_years]`

## 2026-04-07 (6 ชม.)
- Refactor UI และ logic ของไทม์ไลน์คำขอให้รองรับขั้นตอนงานจัดซื้อรูปแบบใหม่ `[procurement/requisition_timeline]`

## 2026-04-08 (6 ชม.)
- เพิ่มโมดูลไทม์ไลน์คำขอ พร้อมระบบค้นหาและแสดงผล `[procurement/requisition_timeline]`
- เพิ่มการเลือก MA หลายรายการสำหรับการยืนยันของแอดมิน `[procurement/mas]`
- แก้สิทธิ์การเข้าถึงใน MA `[procurement/mas]`

## 2026-04-10 (6 ชม.)
- เพิ่มวันที่สร้างในตารางไทม์ไลน์คำขอ และปรับ logic การกรอง `[procurement/requisition_timeline]`
- เพิ่ม flash card ในเว็บ `[web/base]`
- เพิ่มการคำนวณระยะเวลาประกันในโมเดล, ปรับ UI ตารางไทม์ไลน์ `[procurement/requisition_timeline]`
- เพิ่มฟิลด์ requisition ในการจอง (reservation) `[procurement/mas]`

## 2026-04-19 (6 ชม.)
- เพิ่ม pagination และ filter ผู้ใช้ในไทม์ไลน์คำขอ `[procurement/requisition_timeline]`
- เพิ่ม filter คำขอที่หมดอายุ และจำกัดปุ่ม action ตามสถานะ `[procurement/requisitions]`
- แก้การกำหนด role ผู้จัดงาน (organizer) `[accounts/organizations]`
- แก้ไข title `[procurement/upload_files]`
- เพิ่ม modal ยืนยันก่อนบันทึกการชำระเงิน `[procurement/payment]`
- แก้ชื่อคอลัมน์ "ปังบประมาณ" เป็น "ปีงบประมาณ" `[procurement/upload_files]`

## 2026-04-23 (6 ชม.)
- สร้างหน้าฟีดแบ็กการใช้รถ (car feedback page) `[vehicle_lending/car_feedback]`
- เพิ่มฟิลด์ company ในรายการคำขอ, เพิ่ม gitignore `[procurement/requisitions]`
- แก้ตาราง MA `[procurement/mas]`

## 2026-05-16 (6 ชม.)
- Cleanup: ลบ skills ที่ไม่ได้ใช้งานออกจากโปรเจกต์ `[dev-tooling/skills]`

## 2026-05-21 (6 ชม.)
- แก้ max length ของฟิลด์, แก้ overflow ของ dropdown ในหน้ายื่นคำขอที่เสร็จสมบูรณ์ `[procurement/requisitions]`
- Refactor การแสดงรูปภาพ, เพิ่ม modal แสดงรูปแบบเต็ม `[procurement/item_orders]`
- แก้ฟอนต์และ layout ในเอกสารคำขอ `[procurement/requisitions]`

## 2026-05-22 (6 ชม.)
- แก้ปัญหา overflow, เอา required ออกจากขั้นตอน 7 ของฟอร์ม `[procurement/requisitions]`
- เปลี่ยน alert เป็น modal แสดงรายละเอียดกิจกรรมใบเบิกรถ `[vehicle_lending/car_applications]`
- โหลด modal event แบบไดนามิกผ่าน server-side component ในปฏิทิน `[vehicle_lending/car_applications]`
- เพิ่มผู้ใช้ที่เป็นคนขับในใบเบิกรถ, แก้การส่งอีเมลให้เฉพาะคนขับที่ถูกมอบหมาย `[vehicle_lending/car_applications]`

## 2026-05-23 (6 ชม.)
- บังคับ multi-tenant ในระบบงานจัดซื้อ `[procurement]`
- เพิ่มการผูกองค์กรตอนสร้าง/แก้ไขข้อมูลจัดซื้อ `[procurement]`
- แก้ layout ปุ่มและหน้า supplier/ปฏิทิน `[procurement/suppliers, dashboard]`

## 2026-05-24 (6 ชม.)
- เพิ่มฟิลด์องค์กรใน RequisitionTimelineLogs, แก้ไขฟิลด์ role `[procurement/requisition_timeline]`
- เพิ่มตัวเลือกกองทุนในหน้าแอดมิน `[procurement/requisitions]`
- ปรับปรุงหน้าคำขอต่ออายุที่ยื่นแล้ว พร้อมรายละเอียดกองทุน `[procurement/requisitions]`
- พัฒนาระบบฟีดแบ็กการใช้รถแบบไดนามิก รองรับคำถามหลายประเภทและ component render ฟอร์ม `[vehicle_lending/car_feedback]`
- แก้ไขหัวข้อ dashboard, แก้ปุ่ม copy link/QR สำหรับทดสอบบน staging `[vehicle_lending/car_feedback]`
- แก้บั๊กเล็กน้อย `[procurement/requisitions]`
- เพิ่ม backend สำหรับตัวติดตาม progress คำขอ `[procurement/requisitions]`

## 2026-05-27 (6 ชม.)
- แก้ layout หน้ายื่นคำขอที่เสร็จสมบูรณ์, แก้ float ให้เป็น decimal field `[procurement/requisitions]`
- Refactor การแสดงผล UI ของตารางรถ `[vehicle_lending/car_permissions]`
- เพิ่มคำสั่ง AI (GEMINI) และคู่มือ multi-agent workflow `[project-config]`
- เพิ่มฟิลด์ผู้ชนะการเสนอราคาและยอดรวมในไทม์ไลน์คำขอ ปรับฟอร์ม/เทมเพลตที่เกี่ยวข้อง `[procurement/requisition_timeline]`
- ลบ timestamp ที่ไม่จำเป็นในขั้นตอนการอนุมัติของผู้จัดการ `[procurement/requisitions]`

## 2026-05-31 (6 ชม.)
- แก้การแสดงผลหน้าผู้จัดการและหน้าคำขอต่ออายุ `[procurement/requisitions]`
- ปรับฟอร์มแก้ไข role ผู้ใช้ให้ดึงข้อมูลเดิมมาเติมอัตโนมัติ `[accounts/roles]`
- แก้สิทธิ์การเข้าถึงไทม์ไลน์คำขอ `[procurement/requisition_timeline]`
- เพิ่ม multiple select สำหรับเลือกรถในฟอร์ม `[vehicle_lending/car_feedback]`
- เพิ่มการตรวจสอบ progress ก่อนอัปเดตค่าใหม่ `[procurement/requisitions]`

## 2026-06-02 (6 ชม.)
- แก้ปุ่มพิมพ์ให้ disable เมื่อไม่มีใบเบิกรถ, เพิ่มสิทธิ์ role หัวหน้าในไทม์ไลน์คำขอ `[vehicle_lending/car_applications, procurement/requisition_timeline]`
- เพิ่มหน้า preview เอกสารต่ออายุ, แก้ไขฟอนต์ `[procurement/requisitions]`
- ปรับการจัดการสถานะคำขอ, เพิ่มการแสดงคำขอที่รอหัวหน้าอนุมัติ `[procurement/requisitions]`
- ออกแบบ modal ยืนยันใหม่, แก้การมอบหมายคนขับ/รถในหน้าแอดมิน `[vehicle_lending/car_permissions]`
- เพิ่มรายละเอียดใน modal ปฏิทิน, เพิ่มวันที่สร้างในตารางสิทธิ์การใช้รถ `[vehicle_lending/car_permissions]`

## 2026-06-04 (6 ชม.)
- แก้ตำแหน่งข้อมูลในปฏิทิน, ลบ alert ที่ไม่จำเป็น `[vehicle_lending, procurement/macros]`
- Refactor ฟอร์มและเทมเพลตงานจัดซื้อให้มีโครงสร้างและใช้งานง่ายขึ้น `[procurement]`

## 2026-06-06 (6 ชม.)
- แก้ไขช่องโหว่ความปลอดภัย (CVE) `[infra/dependencies]`
- ออกแบบ modal ใหม่ในหน้าสิทธิ์การใช้รถ และหน้าประวัติการใช้รถ `[vehicle_lending/car_permissions, vehicle_lending/history_car_lending]`
- เพิ่มช่องค้นหาในหน้าสิทธิ์การใช้รถ `[vehicle_lending/car_permissions]`
- แก้การแสดงผลวันที่ใน date picker และเทมเพลต `[vehicle_lending/car_permissions]`
- ปรับการ render ฟอร์มให้รองรับ dynamic styling และแสดง error message ตามเงื่อนไข `[procurement/requisitions]`
- เริ่มต้นระบบ MAS (init MAS system) `[procurement/mas]`

## 2026-07-13 (6 ชม.)
- เพิ่มรายละเอียดการรับส่งสนามบิน (airport transfer) ในฟอร์มและหน้าแสดงผลใบเบิกรถ พร้อม mark required และวันที่กลับ `[vehicle_lending/car_applications]`
- อัปเดต dependencies ของโปรเจกต์ `[infra/dependencies]`
- ปรับความกว้างคอลัมน์ตารางใบเบิกรถ `[vehicle_lending/car_permissions]`

## 2026-08-17 (6 ชม.)
- เขียนคู่มือการใช้งานใบเบิกรถยนต์ `[vehicle_lending]`
- แก้ layout `[procurement/requisitions]`

## 2026-08-18 (6 ชม.)
- เขียนคู่มือการใช้งานใบเบิกรถจักรยานยนต์ `[vehicle_lending]`
- พัฒนาระบบสลับองค์กร (organization switching) และรองรับผู้ใช้ที่มีหลายองค์กร พร้อมแก้ error message ตอนเลือกไซต์ในงานจัดซื้อ `[accounts/organizations, procurement]`
- เพิ่มชุด agent/testing/matt-pocock skills สำหรับเครื่องมือพัฒนา `[dev-tooling/skills]`
- ปรับปรุงฟีเจอร์ฟีดแบ็กการใช้รถ (car feedback): เพิ่มฟอร์มกรองตามรถ/ทริป, ปรับ dashboard ให้มี animation, เพิ่ม SVG star rating, แก้ layout `[vehicle_lending/car_feedback]`
- เพิ่ม test suite และ backfill script สำหรับ car feedback พร้อมแก้ไขตาม PR code review `[vehicle_lending/car_feedback, tests]`

---

*หมายเหตุ: เนื้อหางานทั้งหมดดึงมาจาก commit จริงใน git log ของบัญชีนี้ครบทุกรายการ แต่ถูกจัดกลุ่ม/ย้ายไปรวมกันใหม่ให้เหลือ 38 วัน วันที่ที่แสดงเป็นวันที่ที่มีงานหลัก (anchor) ของแต่ละกลุ่ม ส่วนตัวเลข 6 ชม./วัน เป็นค่าคงที่ที่กำหนดไว้ตามคำขอ ไม่ได้คำนวณจากขนาดหรือช่วงเวลาของ commit แท็ก `[module]` มาจากการดู path ของไฟล์ที่ commit จริงแก้ไข (เช่น `kampan/web/views/vehicle_lending/car_feedback.py` → `vehicle_lending/car_feedback`) เป็นการจัดกลุ่มโดยประมาณ ควรตรวจสอบและปรับให้ตรงกับความจริงก่อนนำไปใช้รายงานอย่างเป็นทางการ*
