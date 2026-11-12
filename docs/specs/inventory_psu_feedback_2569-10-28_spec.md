# Spec: ข้อเสนอแนะระบบ Inventory PSU (ประชุม 28/10/2569)

> ที่มา: บันทึกประชุมรับ feedback ผู้ใช้งานงานพัสดุ 28/10/2569
> ขอบเขตหลัก: โมดูลขอซื้อขอจ้าง (Requisition / Requisition Timeline), ทะเบียนสินค้าและสัญญาบริการ (Procurement / MA), การแจ้งเตือนทางอีเมล และระบบวัสดุ
> updated: 2026-11-13

---

## Amendment 2026-11-04 (ผู้ตัดสิน: Mhapong)

หัวข้อนี้มีผลเหนือข้อความเดิมด้านล่างทุกจุดที่ขัดกัน เนื้อหาเดิมคงไว้เป็นประวัติ ติดตามงานได้ใน PR #44

### ขอบเขตใหม่
- โมดูล procurement เหลือแค่ **ระบบจัดการสัญญา (MA)**
- ปิด **ขอซื้อขอจ้าง** (Requisition, Requisition Timeline 8 ขั้น, รายการสินค้าของคำขอ) และ **MAS / แหล่งเงิน** ออกจากระบบไว้ก่อน (ตัดสินอีกครั้งหลังประชุม) โดยไม่ลบโค้ด model และข้อมูล ใช้ flag `PROCUREMENT_REQUISITION_ENABLED` ใน config ซึ่งไม่ตั้ง = ปิด (ไม่มีปุ่มเปิด/ปิดในหน้าเว็บ)
  - ส่วนของขอซื้อขอจ้างหรือ MAS ที่ทับกับงาน MA แล้วทำให้ระบบพัง ให้ตัดออกจากเส้นทางของ MA (เช่น ปุ่มต่ออายุแบบเดิมที่สร้างคำขอซื้อ)
  - ตอน flag ปิด: เมนูหาย และ URL ตอบ 404
  - การ์ดในหน้าเลือกระบบชื่อ "ระบบจัดการสัญญา (MA)" และพาไปหน้ารายการ MA
- **E4 / #35:** เลิกใช้ MAS ภายใน (ทางเลือก A) ไม่ลบข้อมูลด้วยโค้ด (staging ล้างข้อมูล MAS / Reservation ไปแล้ว)
  - ตัดปุ่ม Template แหล่งเงิน (MAS) และการอัปโหลดไฟล์ MAS ออก
  - ยอดเงินของ MA ไม่ผูกและไม่ตัดยอด MAS
- สร้าง MA ได้จากหน้ารายการ MA เท่านั้น ตัดปุ่ม "สร้าง MA" จากขั้นเสร็จสิ้นของขอซื้อขอจ้าง
- ข้อมูล MA เดิมจะถูกลบทิ้งทั้งหมด จึง**ไม่มี migration** (ยกเลิกข้อ Data migration ด้านล่าง) โค้ดรองรับเฉพาะโครงสร้างใหม่
- ไม่ทำ **E2** (filter ปีงบประมาณ, #33) เพราะไม่ใช้ปีงบประมาณแล้ว
- **E3** (#34) รอยืนยันในการประชุม
- งานระบบยานพาหนะ (#40, #43) พักไว้
- ปัญหาของ MAS ที่พบ เปิดเป็น #46, #47, #48 ไว้ทำเมื่อกลับมาใช้ MAS

### งวด, การจ่าย, รูปภาพ และหน้ารายการ MA (อัปเดต 2026-11-05)
- **งวดเป็นสวิตช์ต่อรายการย่อย "แบ่งจ่ายเป็นงวด"** (`installment_mode`)
  - ปิด (ค่าเริ่มต้นของรายการใหม่): จ่ายครั้งเดียวก่อนสิ้นสุด ระบบเก็บงวดเดียว `due_date` = `end_date` ของรายการ สร้างและย้ายตามวันสิ้นสุดอัตโนมัติ ผู้ใช้ไม่กรอกอะไร ไม่แสดงตารางงวด
  - เปิด: ผู้ใช้เพิ่มเฉพาะวันครบกำหนด (ปุ่ม "เพิ่มงวด" ขั้นต่ำ 1 สูงสุด 120)
  - งวดมีแค่วันครบกำหนดในฟอร์ม ตัดปุ่ม "สร้างวันครบกำหนดเท่า ๆ กัน" และช่องจำนวนงวดออก
  - รายการเก่าที่ไม่มี field นี้: มากกว่า 1 งวด = เปิด ไม่เช่นนั้นปิด (ไม่ต้อง migrate) การนำเข้า Excel: จำนวนงวด > 1 = เปิด
  - ปิดสวิตช์ตอนมีงวดที่จ่ายแล้ว 2 งวดขึ้นไปไม่ได้ ลบงวดที่จ่ายแล้วไม่ได้ (แก้ MA ไม่ทับสถานะการจ่าย จับคู่งวดด้วย `installment_id`)
- **วันจ่ายบันทึกหลังสร้างแล้ว** ด้วยปุ่ม "จ่ายแล้ว" ที่หน้ารายละเอียด (ไม่กรอกในฟอร์มสร้าง/แก้ไข) เลือกวันที่จ่าย (ปฏิทิน พ.ศ.) เลขที่เอกสารและยอดไม่บังคับ
  - ทุกครั้งที่กดจ่าย / ยกเลิกการจ่าย เพิ่มประวัติใน `pay_log` ของงวด (เวลากด, วันที่จ่าย, ผู้กด, เลขที่เอกสาร, ยอด) แสดงใหม่สุดก่อนใต้งวด
- **ตัดการอัปโหลดรูปภาพ** ออกจากฟอร์ม MA และปุ่มแก้รูป (ข้อมูลและ route แสดงรูปเดิมยังอยู่)
- **ฟอร์มและหน้า procurement ใช้ DaisyUI ทั้งหมด:** วันที่แสดงปี พ.ศ. (ค่าที่ส่งยังเป็น ISO ค.ศ.), dropdown แทน `<select>`
- **หน้ารายการ MA** (รายการ MA, MA ขอต่ออายุ, ไม่ต่ออายุ) มีแถบตัวกรองเดียวกัน (ค้นหา, ตัวกรองย่อย, จำนวนผลลัพธ์, ล้างตัวกรอง) และเรียงลำดับด้วย `?sort=` (สร้างล่าสุด/เก่าสุด, ใกล้หมดอายุที่สุด/หมดอายุหลังสุด, ชื่อ ก-ฮ)
  - ค่าตั้งต้น: รายการ MA = สร้างล่าสุดก่อน, MA ขอต่ออายุ = ใกล้หมดอายุที่สุด, ไม่ต่ออายุ = หมดอายุหลังสุด
  - หน้าไม่ต่ออายุเพิ่มตัวกรอง ผู้รับผิดชอบ, บริษัท, ช่วงวันสิ้นสุด, ประเภท

### สิทธิ์
- **ผู้สร้าง MA:** สมาชิกที่ active ของหน่วยงานทุก role สร้าง MA ได้ (ไม่จำกัดเฉพาะ admin) ผู้สร้างแก้ไขและเห็น MA ของตัวเองได้เสมอ
- **ผู้แก้ไข MA ได้:** admin ของหน่วยงาน, ผู้สร้าง MA (`created_by`) และผู้รับผิดชอบของรายการย่อยใดก็ได้ใน MA นั้น
  - สิทธิ์เดียวกันนี้ใช้กับ: แก้ไข MA (รวมงวดที่จ่ายแล้ว), ต่ออายุ, ไม่ต่ออายุ, บันทึกการจ่ายงวด และเพิ่ม log การแจ้งเตือนเอง
- **D1:** role ที่เห็น MA ทั้งหน่วยงานคือ `admin`, `head`, `manager`, `supervisor supplier` และ `director` มี role ใดในกลุ่มนี้ก็เห็นทั้งหมด แม้จะมี `staff` ด้วย
- role อื่นเห็นเฉพาะ MA ที่ตัวเองรับผิดชอบรายการย่อย
- ใช้กติกาเดียวกันทุกหน้าที่แสดง MA
- ข้อมูลของหน่วยงานอื่นตอบ 404

### เงิน (A5 / #23)
- คง `DecimalField` (เก็บเป็น double) ไม่ migrate และยอดเงินที่อยู่ใน DB ต้องไม่เปลี่ยน
- ปัดเศษแบบ banker's rounding (`ROUND_HALF_EVEN`) เฉพาะค่าที่ระบบคำนวณเอง
- ฟอร์มปฏิเสธ input ที่มีทศนิยมเกิน 2 ตำแหน่ง ไม่ปัดให้เงียบ ๆ
- ไฟล์ Excel ที่อัปโหลดและมีทศนิยมเกิน 2 ตำแหน่ง ระบบปัดแบบธนาคารตอนบันทึก

### โครงสร้าง MA (B5 / B7 / #25 / #26 / #27)
- **หัวสัญญา:** เลขที่ ม.อ.เบิกจ่าย (บังคับในฟอร์ม ซ้ำได้), ยอดเงินรวม
- **รายการย่อย:** ผังบัญชี, ช่วงวันที่, ยอดเงิน, ผู้รับผิดชอบ, ผู้ชนะ, ราคาต่อหน่วย, หมายเหตุ โดยผู้ชนะและราคาต่อหน่วยไม่บังคับ
  - **ยี่ห้อ / รุ่น / รายละเอียด (S/N, รหัสครุภัณฑ์ ฯลฯ)** เป็นแถวย่อยของรายการย่อย กดเพิ่มได้ตามต้องการ (สูงสุด 100 แถวต่อรายการ) แถวที่ว่างทุกช่องไม่บันทึก
  - **แยกช่อง S/N และ รหัสครุภัณฑ์ เป็นช่องเฉพาะ (มีสวิตช์ toggle เปิด/ปิด):**
    - ในฟอร์มสร้าง/แก้ไข MA มีสวิตช์เปิด/ปิด "ระบุ S/N" (`has_sub_item_sn`) และ "ระบุรหัสครุภัณฑ์" (`has_sub_item_asset`) ต่อรายการย่อย
    - เมื่อเปิดสวิตช์ จะแสดงช่องกรอก S/N หรือ รหัสครุภัณฑ์ ในแถวย่อย (ซิงค์ด้วย JavaScript ทันทีทั้งตอนเปลี่ยนสวิตช์และตอนกดเพิ่มแถว)
    - ในหน้ารายละเอียด MA (`/procurement/payment/<id>`) ตารางข้อมูลเครื่อง/ครุภัณฑ์ จะตรวจสอบว่ารายการนั้นมี S/N หรือ รหัสครุภัณฑ์ หรือไม่ โดยหากมีช่องใดหรือทั้งสองช่อง จะเพิ่มคอลัมน์ S/N และ/หรือ รหัสครุภัณฑ์ ในตารางให้อัตโนมัติ
  - ส่วนข้อมูลเพิ่มเติมของรายการย่อย (แถวยี่ห้อ / รุ่น / รายละเอียด, ผู้ชนะ, ราคาต่อหน่วย, หมายเหตุ) แสดงตลอด ไม่พับซ่อน
- **Sum check:** ผลรวมยอดรายการย่อยต้องเท่ายอดรวม MA (บังคับ)
- **งวดไม่มีการแบ่งเงิน** (ยกเลิก B7.3 ส่วนจำนวนเงินรายงวด และ sum check ระดับงวด) งวดเป็นตัวช่วยจำว่าจ่ายไปแล้วกี่งวด
  - แต่ละงวดมี: วันครบกำหนด และสถานะจ่าย (วันที่จ่าย, ผู้บันทึก, เลขที่เอกสาร)
  - ยอดที่จ่ายจริงไม่บังคับ
- สถานะ "ใกล้ครบกำหนด" คือ 30 วัน
- ยอด 0 บาทบันทึกได้ แต่ต้องมีอย่างน้อย 1 งวด

### การแจ้งเตือน (C / #28 / #29 / #30)
- แต่ละรายการย่อยมี checkbox 2 ชุด เลือกได้ 6/5/4/3/2/1 เดือน และ 15/7 วันก่อนถึงกำหนด ส่งทุกช่วงที่ติ๊ก:
  - **เตือนหมดอายุ:** ค่าเริ่มต้น 3/2/1 เดือน และ 15/7 วัน
  - **เตือนจ่ายงวด:** ค่าเริ่มต้น 3/2/1 เดือน และ 15/7 วัน
- กรอกเพิ่มได้:
  - จำนวนวันเตือนก่อนหมดอายุ 1–730 วัน (ห้ามซ้ำ)
  - วันที่เตือนเจาะจง เป็นปี พ.ศ. `DD/MM/YYYY` และวันที่เก่ากว่า 7 วันจะไม่ส่งย้อนหลัง
- ในวันครบกำหนดเตือน 1 ครั้ง ไม่เตือนซ้ำรายสัปดาห์หลังเลยกำหนด (ยกเลิกข้อ "expired: เตือนซ้ำสัปดาห์ละครั้ง")
- สัญญาหลักที่แยกสัญญาย่อยแล้ว (มีสัญญาย่อยอ้างถึง) ไม่เตือนเอง เตือนจากสัญญาย่อยเท่านั้น เพราะรายการย่อยของสัญญาย่อยเป็นสำเนาของสัญญาหลัก (ตัดสินใจ 2026-11-12 โดย Mhapong)
- ส่งไม่สำเร็จให้บันทึกเป็น failed และไม่ retry เอง
- กันส่งซ้ำด้วย unique key แบบไม่พึ่ง `partialFilterExpression` เพราะยังไม่รู้เวอร์ชัน MongoDB ของ production
- **ประวัติการแจ้งเตือน:** เรียงใหม่สุดก่อน ทุกคนที่เปิด MA ได้เห็นประวัติ และผู้แก้ไข MA ได้เพิ่ม log เองได้

### การต่ออายุ (E1 / #32)
- กด "ต่ออายุ" แล้วจะเปิดฟอร์มสร้าง MA ที่ดึงข้อมูลเดิมมาให้
  - **เว้นว่างให้กรอกใหม่:** วันเริ่ม-สิ้นสุดของรายการย่อย และเลขที่ ม.อ.เบิกจ่าย
  - **ไม่ copy:** งวด, สถานะการจ่าย และวันที่เตือนเจาะจง
- บันทึกแล้วจะได้ MA ใหม่ และ MA เดิมเปลี่ยนเป็น "ต่ออายุแล้ว"
- ต่ออายุได้จากทุกสถานะ ยกเว้น "ต่ออายุแล้ว"
- ปุ่ม "ยื่นขอต่ออายุ" แบบเดิม (สร้างคำขอซื้อ) ถูกปิดไปพร้อมขอซื้อขอจ้าง
- เลิกใช้สถานะ "ยื่นขอต่ออายุ" (`renewal-requested`) และปุ่ม "ขอต่ออายุ" ในตารางรายการ MA: MA ที่รายการย่อยจะหมดภายใน 90 วันถูก controller ย้ายเป็น "รอดำเนินการ" (`pending`) แล้วอยู่ในหน้า "รายการ MA ใกล้หมดอายุ" เอง ข้อมูลเดิมที่เป็น `renewal-requested` ยังอ่านและแสดงในหน้านั้นได้ (ตัดสินใจ 2026-11-13 โดย Mhapong)
- ก่อนต่ออายุ ถ้า MA มีงวดที่ยังไม่ได้บันทึกจ่าย (ทุกรายการย่อย ทุกงวดที่ยังไม่จ่าย) ให้ขึ้น modal เตือนพร้อมปุ่ม "บันทึกจ่าย" ของแต่ละงวด และปุ่ม "ต่ออายุต่อไป" (เตือนเท่านั้น ไม่บังคับ) เพราะ MA เดิมเมื่อต่ออายุจะถูกปิดและหยุดเตือนทุกงวด (ตัดสินใจ 2026-11-13 โดย Mhapong)
- รายการย่อยที่มีงวดเดียว: ต่ออายุ = จ่ายงวดนั้น ระบบบันทึกงวดของ MA เดิมว่าจ่ายแล้ววันที่ต่ออายุ (ผู้บันทึก = ผู้กดต่ออายุ ประวัติการกดเป็น "จ่ายตอนต่ออายุ") และไม่นับในการเตือนก่อนต่ออายุ ส่วนเลขที่เอกสาร/ยอดจริงแก้ได้ที่หน้ารายละเอียด (ตัดสินใจ 2026-11-13 โดย Mhapong)


---

## TODO List (สรุปสำหรับติดตามงาน)

### A. ตรวจสอบ / แก้บั๊ก (Quick checks)

- [X] **A1** ตรวจว่าเพิ่มกรรมการ (Committees) ในคำขอซื้อขอจ้างได้เกิน 3 คนหรือไม่ และกำหนดกฎให้ชัด (จำกัด/ไม่จำกัด ต่อประเภทกรรมการ)
- [X] **A2** ตรวจสอบการลบแหล่งเงิน (MAS) — ห้ามลบเมื่อมี Reservation ที่ active อ้างอิงอยู่ / ยอด remaining ต้องถูกต้องหลังลบ
- [X] **A3** ปุ่ม "ถอยกลับ" ขั้นตอนการดำเนินการ (Requisition Timeline 8 ขั้น) — ย้อนกลับได้ 1 ขั้น พร้อมบันทึกลง `RequisitionTimelineLogs`
- [ ] **A4** ตรวจการแสดงผล icon (Phosphor) ทั่วเว็บ — หา icon ที่ไม่ขึ้น/ชื่อ class ผิด
- [ ] **A5** ตรวจทุก field เงินเป็น `DecimalField` (precision=2) ทั้ง model และ form และไม่มีการแปลงเป็น float ระหว่างคำนวณ
- [ ] **A6** ระบบวัสดุ: จำนวนคงเหลือไม่ตรง — ไล่หาสาเหตุ (register / checkout / lost-break / inventory)
- [ ] **A7** ตรวจว่าอีเมลแจ้งเตือนส่งถึง "ผู้รับผิดชอบ" จริง และส่งตามเวลาที่ควร (ดู Further Notes: flag `notified_90d/30d` ไม่ได้เป็น field ใน model)

### B. ประเภทและข้อมูลรายการ Software/บริการ

- [ ] **B1** เพิ่มประเภท "สินทรัพย์ไม่มีตัวตน" (intangible asset) ใน `CATEGORY_CHOICES`
- [ ] **B2** เพิ่ม field "รายละเอียด" เป็น textarea กรอกอิสระ (free-style) ในรายการย่อยทุกประเภท (ซอฟต์แวร์, ครุภัณฑ์/hardware, บริการ, อื่น ๆ) — ใช้บันทึกรายละเอียดบริการ, S/N, รหัสครุภัณฑ์ หรือข้อมูลอื่นตามที่ผู้กรอกต้องการ → ปรับ: ยี่ห้อ / รุ่น / รายละเอียด เป็นแถวย่อยของรายการย่อย กดเพิ่มได้หลายแถว และแสดงตลอดไม่พับ (ดู Amendment "โครงสร้าง MA")
- [ ] **B3** ~~toggle เปิด/ปิด S/N และรหัสครุภัณฑ์~~ → ยกเลิก รวมเข้ากับ B2: เอา input S/N / รหัสครุภัณฑ์แบบแยกช่องออกจากฟอร์ม และ migrate ข้อมูลเดิมเข้า textarea
- [ ] **B4** เพิ่ม field "เลขที่ ม.อ. เบิกจ่าย" + ค้นหาด้วยเลขนี้เป็นหลัก (index)
- [ ] **B5** โครงสร้าง "สัญญา (หัว) → รายการย่อย": หัวมียอดเงินรวม + เลขที่ ม.อ.เบิกจ่าย ร่วมกัน, รายการย่อยแต่ละรายการมี ผังบัญชี / วันเริ่ม-สิ้นสุด / ยอดเงิน / จำนวนงวด / ผู้รับผิดชอบ (default = ผู้กรอก) ของตัวเอง
- [ ] **B6** รวมขั้นตอนดำเนินการที่ 3 (ระบุรายละเอียด) เข้ากับหน้าเพิ่มรายการ
- [ ] **B7** ยอดเงิน 3 ชั้น + sum check กันกรอกผิด
  - [ ] **B7.1** กรอก "ยอดเงินรวมของ MA" (top-level) ที่หัวสัญญา
  - [ ] **B7.2** กรอกยอดเงินของแต่ละรายการย่อย
  - [ ] **B7.3** ตารางงวดการจ่ายต่อรายการย่อย: แต่ละงวดระบุวันครบกำหนด + จำนวนเงินเองได้ (มีปุ่มช่วยแบ่งเท่า ๆ กัน เศษสตางค์ไปลงงวดสุดท้าย)
  - [ ] **B7.4** แสดงผลรวมแบบ real-time ในฟอร์ม: ยอด MA / ผลรวมรายการย่อย / ส่วนต่าง (เขียว = ตรง, แดง = ไม่ตรง) และเช่นเดียวกันที่ระดับงวดของแต่ละรายการย่อย
  - [ ] **B7.5** server-side validation: ผลรวมรายการย่อย ≠ ยอด MA หรือ ผลรวมงวด ≠ ยอดรายการย่อย → ไม่ให้บันทึก พร้อม error ระบุว่าต่างกันเท่าไหร่และอยู่ที่รายการไหน
- [ ] **B8** checkbox "ต้อง activate เมื่อหมดอายุ" (จ่ายแล้วแต่ต้องกด activate ก่อนใช้งาน)
- [ ] **B9** ประเภทการเตือนของรายการย่อย: MA / License / เช่า-จ้างเหมามีระยะเวลา

### C. การแจ้งเตือน (สำคัญที่สุด)

- [ ] **C1** แจ้งเตือนหมดอายุ/ต่ออายุไปยังผู้รับผิดชอบของรายการย่อย
- [ ] **C2** ค่าเริ่มต้นเตือนล่วงหน้า 3, 2, 1 เดือน (แทน 90d/30d เดิม)
- [ ] **C3** เตือนจ่ายเงินรายงวด ล่วงหน้า 1–3 เดือน (เลือกได้)
- [ ] **C4** ผู้ใช้กำหนดช่วงเตือนเองได้ (offset เช่น 90/60/30 วัน) และ/หรือเลือก "วันที่เจาะจง" เช่น 28/05/2570, 18/10/2570, 10/04/2571
- [ ] **C5** แยกอีเมลรายรายการ แต่กันไม่ให้เป็น spam (dedupe ต่อรายการ+ประเภท+วันที่, rate limit, subject ชัดเจน)
- [ ] **C6** ประวัติ (log) การส่งอีเมลแจ้งเตือนต่อรายการ + เพิ่ม log ด้วยมือได้ (เช่น โทรแจ้งแล้ว)

### D. สิทธิ์การมองเห็น

- [ ] **D1** หัวหน้าฝ่าย (`head`), ผู้บริหาร (`manager`) และเจ้าหน้าที่พัสดุ (`admin`, `supervisor supplier`) เห็นรายการ MA **ทั้งหมด** ใน organization
- [ ] **D2** เพิ่ม filter "เฉพาะฝ่ายของฉัน" ในหน้ารายการ MA สำหรับ role ใน D1 — แสดงเฉพาะ MA ที่มีรายการย่อยอย่างน้อย 1 รายการซึ่งผู้รับผิดชอบสังกัดฝ่ายของผู้ใช้ (default = ปิด แสดงทั้งหมด)
- [ ] **D3** role อื่น (ผู้รับผิดชอบทั่วไป) เห็นเฉพาะ MA ที่ตนเป็นผู้รับผิดชอบในรายการย่อยอย่างน้อย 1 รายการ
- [ ] **D4** แต่ละ MA แสดงชื่อฝ่ายทั้งหมดที่รับผิดชอบ (derive จากฝ่ายของผู้รับผิดชอบในรายการย่อย ไม่ต้องกรอกเอง)

### E. การต่ออายุ / รายงาน / เอกสาร

- [ ] **E1** ต่ออายุ MA = สร้าง MA ใหม่จากข้อมูลเดิม + ผูก relation กับ MA เก่า
  - [ ] **E1.1** ปุ่ม "ต่ออายุ" บน MA เดิม → เปิดฟอร์มสร้าง MA ใหม่ที่ pre-fill ข้อมูลหัวสัญญาและรายการย่อยจาก MA เดิม แก้ไข/เพิ่ม/ลบรายการย่อยได้ก่อนบันทึก
  - [ ] **E1.2** กดบันทึก → สร้าง MA ใหม่เป็นเอกสารแยก (MA เดิมไม่ถูกแก้ข้อมูล) โดย MA ใหม่เก็บ `renewed_from` → MA เดิม และ MA เดิมเก็บ `renewed_to` → MA ใหม่
  - [ ] **E1.3** MA เดิมเปลี่ยนสถานะเป็น "ต่ออายุแล้ว" และแสดงแถบ "ต่ออายุไปที่รายการ xxx แล้ว" พร้อมลิงก์ไป MA ใหม่; MA ใหม่แสดง "ต่ออายุจากรายการ xxx" พร้อมลิงก์กลับ
  - [ ] **E1.4** MA ที่ต่ออายุแล้วกดต่ออายุซ้ำไม่ได้ (ปุ่มหาย/disabled) และหยุดการแจ้งเตือนหมดอายุของ MA เดิม
  - [ ] **E1.5** หน้า MA แสดงประวัติการต่ออายุเป็นสายต่อเนื่อง (ปี 2567 → 2568 → 2569)
- [ ] **E2** filter ดูรายการแยกตามปี (ปีงบประมาณ พ.ศ.)
- [ ] **E3** (อาจทำ) สร้างเอกสารอัตโนมัติ: หนังสือขออนุมัติ, หนังสือรายงานผลพิจารณา (ได้ใคร)
- [ ] **E4** (ตัดสินใจ) ระบบ MAS ภายในอาจไม่ต้องใช้ เพราะมหาวิทยาลัยบังคับใช้ระบบ MAS ของ ม.อ.

---

## Problem Statement

เจ้าหน้าที่พัสดุ (ผู้กรอกหลักประมาณ 2 คน) ใช้ระบบเป็น "ระบบบันทึกความจำ" ว่าซอฟต์แวร์/บริการ/สัญญา MA ใดจ่ายเงินแล้ว ยังไม่จ่าย จ่ายให้ใคร และเมื่อไหร่ต้องต่ออายุ แต่ในปัจจุบัน:

- หนึ่งสัญญา (หนึ่งเลขที่ ม.อ.เบิกจ่าย) มักมีหลายรายการย่อยที่ผังบัญชี ระยะเวลา และผู้รับผิดชอบต่างกัน แต่ระบบเก็บเป็นรายการเดียวที่มีวันเริ่ม/สิ้นสุดและผู้รับผิดชอบชุดเดียว
- งวดการจ่ายถูกคำนวณโดยหารวันเท่า ๆ กัน ไม่ตรงกับสัญญาจริงที่ระบุวันจ่ายและยอดแต่ละงวด
- การแจ้งเตือนมีแค่ 90 วัน / 30 วัน / หมดอายุ แบบตายตัว ไม่สามารถเลือกช่วงหรือวันที่ต้องการได้ และไม่แน่ใจว่าอีเมลไปถึงผู้รับผิดชอบจริง ไม่มีประวัติให้ตรวจสอบย้อนหลัง
- ค้นหาด้วยเลขที่ ม.อ.เบิกจ่าย (ซึ่งเป็นสิ่งที่ใช้ค้นบ่อยที่สุด) ไม่ได้
- ผู้รับผิดชอบทั่วไปเห็นรายการที่ไม่เกี่ยวกับตัวเอง ส่วนหัวหน้า/ผู้บริหาร/เจ้าหน้าที่พัสดุไม่มีวิธีกรองดูเฉพาะ MA ที่ฝ่ายตัวเองรับผิดชอบ
- การต่ออายุต้องกรอกใหม่ทั้งหมด
- รายการบางชนิด (สินทรัพย์ไม่มีตัวตน) ไม่มีที่ลงที่เหมาะสม และฟอร์มบังคับช่อง S/N / รหัสครุภัณฑ์แบบตายตัว ซึ่งหลายรายการไม่มี ขณะที่ไม่มีที่ให้เขียนรายละเอียดอื่นแบบอิสระ
- มีบั๊ก/ความไม่แน่นอนหลายจุด: จำนวนกรรมการ, การลบแหล่งเงิน, ถอยขั้นตอนไม่ได้, icon ไม่แสดง, จำนวนวัสดุไม่ตรง

## Solution

- ปรับทะเบียนสัญญาบริการเป็นโครงสร้าง **สัญญา (หัว) → รายการย่อย** โดยหัวเก็บเลขที่ ม.อ.เบิกจ่าย ยอดเงินรวม และบริษัท ส่วนรายการย่อยเก็บผังบัญชี ระยะเวลา ยอดเงิน ตารางงวด ผู้รับผิดชอบ รายละเอียดแบบ free text (รวม S/N / รหัสครุภัณฑ์) และตั้งค่าการเตือนของตัวเอง
- ตารางงวดกำหนดวันและยอดเงินรายงวดได้เอง (มีปุ่มช่วยสร้างงวดเท่า ๆ กันเป็นค่าเริ่มต้น)
- ระบบการเตือนใหม่ที่คำนวณ "กำหนดการเตือน" จากรายการย่อย: ค่าเริ่มต้น 3/2/1 เดือนก่อนหมดอายุ และก่อนวันจ่ายแต่ละงวด ผู้ใช้ปรับ offset หรือเพิ่มวันที่เจาะจงได้ ส่งอีเมลแยกรายรายการโดยมีการ dedupe และบันทึก log ทุกครั้ง (รวมถึง log ที่เพิ่มด้วยมือ)
- สิทธิ์การมองเห็นตามบทบาท: หัวหน้าฝ่าย / ผู้บริหาร / เจ้าหน้าที่พัสดุ → เห็น MA ทั้งหมด พร้อม filter "เฉพาะฝ่ายของฉัน" (อิงฝ่ายของผู้รับผิดชอบในรายการย่อย); ผู้รับผิดชอบทั่วไป → เฉพาะ MA ที่ตนรับผิดชอบ
- ปุ่มต่ออายุที่ copy รายการย่อยไปไว้ในฟอร์มให้แก้ไขได้ และ filter ตามปี
- แก้บั๊กและเพิ่ม validation ตามรายการ A1–A7

## User Stories

### ทะเบียนสัญญาและรายการย่อย

1. As a เจ้าหน้าที่พัสดุ, I want to create a contract header with a เลขที่ ม.อ.เบิกจ่าย and a total amount, so that all sub-items paid under the same disbursement are grouped together
2. As a เจ้าหน้าที่พัสดุ, I want to add multiple sub-items under one contract, each with its own ผังบัญชี, so that items funded from different accounts can share one disbursement number
3. As a เจ้าหน้าที่พัสดุ, I want each sub-item to have its own start and end date, so that licenses with different durations under one contract are tracked correctly
4. As a เจ้าหน้าที่พัสดุ, I want to enter the MA's total amount first and then each sub-item's amount, and be blocked from saving if the sub-item amounts don't sum to the MA total, so that typos are caught before they reach the register
4a. As a เจ้าหน้าที่พัสดุ, I want to see the running sum and the remaining difference live while I type, so that I can fix mismatches without submitting first
4b. As a เจ้าหน้าที่พัสดุ, I want the error message to tell me the exact difference and which level (MA vs sub-items, or sub-item vs installments) is off, so that I know what to fix
5. As a เจ้าหน้าที่พัสดุ, I want to search contracts by เลขที่ ม.อ.เบิกจ่าย, so that I can find a contract the way I usually look it up
6. As a เจ้าหน้าที่พัสดุ, I want a free-text "รายละเอียด" textarea on every sub-item regardless of category (software, hardware, service, other), so that I can describe the item however fits it
7. As a เจ้าหน้าที่พัสดุ, I want to write S/N and asset codes inside that textarea instead of fixed inputs, so that items without them don't force me to fill dummy values and items with many of them aren't limited by the form
8. As a เจ้าหน้าที่พัสดุ, I want a category "สินทรัพย์ไม่มีตัวตน", so that intangible assets are classified correctly
9. As a เจ้าหน้าที่พัสดุ, I want to mark a sub-item's reminder type as MA, License or rental/outsourced service, so that the reminder email wording fits the item
10. As a เจ้าหน้าที่พัสดุ, I want step 3 (ระบุรายละเอียด) of the procurement process merged into the add-item page, so that I don't enter the same details twice
11. As a ผู้กรอก, I want the responsible person of a sub-item to default to me, so that I don't have to pick myself every time
12. As a ผู้กรอก, I want to change or add responsible people per sub-item, so that each sub-item reaches the right owner
13. As a ผู้กรอก, I want to tick "ต้อง activate เมื่อหมดอายุ" on a sub-item, so that the system reminds the owner to activate a prepaid license on the expiry date

### งวดการจ่าย

14. As a เจ้าหน้าที่พัสดุ, I want to enter each installment's due date and amount exactly as written in the contract, so that the payment schedule matches reality
15. As a เจ้าหน้าที่พัสดุ, I want a helper that pre-fills equal installments, so that simple contracts are quick to enter
16. As a เจ้าหน้าที่พัสดุ, I want saving to be blocked when a sub-item's installment amounts don't sum to that sub-item's amount, so that totals stay consistent
17. As a เจ้าหน้าที่พัสดุ, I want to record a payment against a specific installment with a payment number, so that I know what was paid, when and to whom
18. As a เจ้าหน้าที่พัสดุ, I want to see paid / unpaid / upcoming / overdue status per installment, so that I know at a glance what's outstanding
19. As a ผู้ดูแลระบบ, I want all monetary values stored and computed as Decimal, so that totals never drift due to float rounding

### การแจ้งเตือน

20. As a ผู้รับผิดชอบ, I want to be emailed 3, 2 and 1 months before a sub-item expires, so that I have time to start renewal procurement
21. As a ผู้รับผิดชอบ, I want to be emailed 1–3 months before each installment is due, so that payments are never late
22. As a ผู้กรอก, I want to customize the reminder offsets per sub-item, so that short contracts don't get irrelevant reminders
23. As a ผู้กรอก, I want to add specific reminder dates (e.g. 28/05/2570, 18/10/2570, 10/04/2571), so that I get reminded at milestones I choose
24. As a ผู้รับผิดชอบ, I want one email per sub-item reminder, so that I can see exactly which item needs action
25. As a ผู้รับผิดชอบ, I want never to receive the same reminder twice, so that the emails aren't treated as spam
26. As a ผู้รับผิดชอบ, I want an expired-item reminder at most at a bounded frequency (not daily forever), so that my inbox isn't flooded
27. As a เจ้าหน้าที่พัสดุ, I want to see a log of every reminder email sent for a sub-item (date, type, recipients, success/fail), so that I can prove the owner was notified
28. As a เจ้าหน้าที่พัสดุ, I want to add a manual log entry (e.g. "โทรแจ้งแล้ว"), so that offline follow-ups are recorded in the same history
29. As a เจ้าหน้าที่พัสดุ, I want failed email sends to appear in the log, so that I can follow up manually
30. As a ผู้รับผิดชอบ, I want reminders to stop once the item is renewed, marked not-renewed, or fully paid, so that I don't get irrelevant emails
31. As a ผู้รับผิดชอบ, I want an activation reminder on the expiry date for items flagged "ต้อง activate", so that I don't forget to activate the paid renewal

### สิทธิ์การมองเห็น

32. As a ผู้รับผิดชอบ (role ทั่วไป), I want to see only the MA contracts where I'm responsible for at least one sub-item, so that my list is relevant
33. As a หัวหน้าฝ่าย, I want to see every MA contract in the organization, so that I have the full picture across divisions
34. As a ผู้บริหาร, I want to see every MA contract in the organization, so that I can oversee all contracts
35. As a เจ้าหน้าที่พัสดุ, I want to see every MA contract in the organization, so that I can manage the whole register
36. As a หัวหน้าฝ่าย / ผู้บริหาร / เจ้าหน้าที่พัสดุ, I want a "เฉพาะฝ่ายของฉัน" filter that shows only MA contracts having a sub-item whose responsible person is in my division, so that I can focus on my division's work
37. As a ผู้ใช้, I want to see the names of all responsible divisions on each MA (derived from its sub-items' responsible people), so that I know which divisions are involved
38. As a ผู้ใช้ from another organization, I must not see or modify any of these contracts, so that tenant data stays isolated

### การต่ออายุและรายงาน

39. As a ผู้รับผิดชอบ, I want a "ต่ออายุ" button that opens a new-MA form pre-filled with the old MA's header and sub-items, so that I only edit what changed
40. As a ผู้รับผิดชอบ, I want to add, edit or remove sub-items in the renewal form, so that the renewed contract reflects the new scope
41. As a เจ้าหน้าที่พัสดุ, I want saving the renewal to create a separate new MA and leave the old MA's data untouched, so that the old contract's payment history stays intact
42a. As a ผู้ใช้, I want the old MA to show "ต่ออายุไปที่รายการ xxx แล้ว" with a link to the new MA, so that I can jump to the current contract
42b. As a ผู้ใช้, I want the new MA to show "ต่ออายุจากรายการ xxx" with a link back, so that I can trace where it came from
42c. As a เจ้าหน้าที่พัสดุ, I want to see the full renewal chain of an MA across years, so that I can review the contract's history
42d. As a ผู้รับผิดชอบ, I want an MA that's already been renewed to stop sending expiry reminders and not offer "ต่ออายุ" again, so that I don't get duplicate contracts or stale emails
42e. As a ผู้รับผิดชอบ, I want nothing to be created if I cancel the renewal form, so that abandoned renewals don't leave junk records
42. As a ผู้ใช้, I want to filter contracts by fiscal year, so that I can review each year separately

### ขั้นตอนขอซื้อขอจ้าง

43. As a ผู้สร้างคำขอ, I want a clear rule on how many committee members I can add (and a validation error beyond it), so that I don't submit invalid committees
44. As a เจ้าหน้าที่พัสดุ, I want to step back one stage in the 8-stage timeline, so that I can correct a mistake without editing the database
45. As a เจ้าหน้าที่พัสดุ, I want every step-back recorded in the timeline log, so that changes are auditable
46. As a เจ้าหน้าที่พัสดุ, I want deleting a fund source to be blocked while it has active reservations, so that budgets don't become inconsistent
47. As a เจ้าหน้าที่พัสดุ, I want (optionally) to generate an approval letter and a consideration-result letter from a requisition, so that I don't type documents by hand

### อื่น ๆ

48. As a ผู้ใช้, I want every icon on the site to render, so that the UI is understandable
49. As a เจ้าหน้าที่คลังวัสดุ, I want material stock quantities to match the sum of receipts minus checkouts and losses, so that I can trust the numbers

## Implementation Decisions

- **Domain model ใหม่/ปรับ (Procurement module)**
  - `Procurement` กลายเป็น "สัญญา" (หัว): เพิ่ม `psu_disbursement_number` (indexed, ใช้ค้นหาหลัก), `total_amount` (Decimal), `fiscal_year`, `renewed_from` (reference ไป MA เดิม), `renewed_to` (reference ไป MA ใหม่)
  - เพิ่ม embedded/รายการย่อย `ProcurementItem`: `name`, `category` (+ `intangible`), `account_code` (ผังบัญชี), `start_date`, `end_date`, `amount` (Decimal), `reminder_kind` (`ma` | `license` | `rental`), `requires_activation` (bool), `details` (StringField ยาว, textarea free-style ใช้กับทุก category — แทน `product_numbers` / `asset_codes`), `responsible_by` (list → `OrganizationUserRole`, default ผู้สร้าง), `responsible_divisions` (list → `Division`, denormalize จากฝ่ายของ `responsible_by` ตอนบันทึก เพื่อใช้ filter/แสดงผล), `installments`, `reminder_offsets_days` (default `[90, 60, 30]`), `custom_reminder_dates`
  - `Installment` (embedded): `due_date`, `amount` (Decimal), `paid_date`, `paid_by`, `payment_number` — แทนการหารวันเท่ากันใน `get_payment_due_dates()`; helper สร้างงวดเท่ากันยังคงมีไว้เป็นค่าเริ่มต้นของฟอร์มเท่านั้น (ปัดเป็นสตางค์ เศษไปงวดสุดท้าย)
  - **Sum check (B7)**: invariant 2 ชั้น ตรวจด้วย `Decimal` แบบเท่ากันเป๊ะ (ไม่มี tolerance)
    - `sum(item.amount for item in ma.items) == ma.total_amount`
    - `sum(i.amount for i in item.installments) == item.amount` ทุกรายการย่อย
    - ตรวจใน form validation (WTForms `validate`) เป็น hard block และตรวจซ้ำใน model ก่อน save เพื่อกันข้อมูลจาก path อื่น (import Excel, renewal)
    - ฝั่ง UI คำนวณ live ด้วย JS แค่เพื่อแสดงผล ไม่ใช่ตัวตัดสิน
    - error ระบุส่วนต่าง เช่น "ผลรวมรายการย่อย 95,000.00 บาท ไม่ตรงกับยอด MA 100,000.00 บาท (ขาด 5,000.00 บาท)"
  - ตัดสินใจเก็บรายการย่อยเป็น **separate collection** (ไม่ใช่ embedded) เพราะต้อง query ตามผู้รับผิดชอบ/ฝ่าย และแนบ log แยกรายรายการ
  - Data migration: Procurement เดิม 1 รายการ → 1 สัญญา + 1 รายการย่อย; `payment_records` เดิม → `installments` ที่จ่ายแล้ว; `product_numbers` / `asset_codes` เดิม → ต่อเป็นข้อความใน `details` (เช่น บรรทัด `S/N: ...` และ `รหัสครุภัณฑ์: ...`)
  - ค้นหาข้อความ: ช่องค้นหาในหน้ารายการ match `details` ด้วย (เพื่อยังค้น S/N / รหัสครุภัณฑ์ได้) นอกเหนือจากเลขที่ ม.อ.เบิกจ่ายและชื่อรายการ
- **Reminder module (deep module ใหม่)**
  - interface เดียว: รับ `today` แล้วคืนรายการ "reminder ที่ถึงกำหนดและยังไม่เคยส่ง" (`item`, `kind`: `expiry` | `payment` | `activation` | `custom`, `trigger_date`, `recipients`) — pure, ไม่แตะ Redis/SMTP
  - ใช้ `ReminderLog` collection (`item`, `kind`, `trigger_date`, `recipients`, `status` sent/failed/manual, `note`, `created_by`) ทั้งเป็นประวัติและเป็น dedupe key (`item + kind + trigger_date` unique) — แทน flag `notified_90d/30d` ที่ไม่ได้ประกาศใน model
  - การนับ "เดือน" ใช้ calendar month (เช่น `relativedelta`) ไม่ใช่ 30 วัน
  - expired: เตือนซ้ำได้ไม่เกินสัปดาห์ละครั้ง และหยุดเมื่อสถานะเป็นต่ออายุแล้ว/ไม่ต่ออายุ
  - scheduler ใน `controllers/server.py` เหลือหน้าที่แค่เรียก reminder module แล้ว enqueue job ส่งเมล; job ส่งเมลเขียน `ReminderLog` (sent/failed)
  - ส่งอีเมล 1 ฉบับต่อ 1 reminder; subject ระบุชื่อรายการ + เลขที่ ม.อ.เบิกจ่าย + ประเภท; ผู้รับ = ผู้รับผิดชอบของรายการย่อย (cc หัวหน้าฝ่ายตามเดิมถ้ายังต้องการ)
- **Visibility**: query helper เดียวสำหรับ "MA ที่ user นี้เห็นได้" รับ `(user, organization, only_my_division: bool)`
  - role `head`, `manager`, `admin`, `supervisor supplier` → เห็น MA ทั้ง org
  - เมื่อ `only_my_division=True` (เฉพาะ role ข้างบน) → กรองเหลือ MA ที่มีรายการย่อย `responsible_divisions ∋ ฝ่ายของ user` (ฝ่ายจาก `get_current_division()`); ถ้า user ไม่มีฝ่าย ให้ซ่อน filter
  - role อื่น → MA ที่มีรายการย่อย `responsible_by ∋ user` และส่ง `only_my_division` มาก็ไม่มีผล
  - ภายใน MA ที่เปิดดู แสดงรายการย่อยทั้งหมดของ MA นั้น (ไม่ซ่อนรายการย่อยของฝ่ายอื่น) แต่ highlight รายการย่อยของฝ่ายตัวเอง
  - filter ส่งเป็น query param (เช่น `division=mine`) และใช้ร่วมกับ filter ปีงบประมาณและค้นหาเลขที่ ม.อ.เบิกจ่ายได้
  - ทุก query scope ด้วย `organization`
  - เมื่อแก้ผู้รับผิดชอบ หรือผู้รับผิดชอบย้ายฝ่าย ต้อง recompute `responsible_divisions`
- **Renewal (E1)**: MA เดิมเป็น immutable record ส่วน MA ใหม่เป็นเอกสารแยก เชื่อมกันด้วย relation 2 ทาง
  - GET ปุ่ม "ต่ออายุ" → render ฟอร์มสร้าง MA (ฟอร์มเดียวกับเพิ่ม MA ใหม่) ที่ pre-fill จาก MA เดิม **ยังไม่สร้างอะไรใน DB** (ไม่มี draft ค้าง ถ้ากดยกเลิกก็จบ)
  - ข้อมูลที่ copy: ชื่อ, บริษัท, ยอดเงินรวม, และรายการย่อยทั้งหมด (ชื่อ, ประเภท, ผังบัญชี, ยอดเงิน, `details`, ผู้รับผิดชอบ, ประเภทการเตือน, `requires_activation`, `reminder_offsets_days`)
  - ข้อมูลที่ไม่ copy: เลขที่ ม.อ.เบิกจ่าย (ต้องกรอกใหม่), งวดที่จ่ายแล้ว, `custom_reminder_dates`, ReminderLog; วันเริ่มของรายการย่อย pre-fill เป็นวันถัดจากวันสิ้นสุดเดิม และวันสิ้นสุด pre-fill ตามระยะเวลาเดิม
  - POST บันทึก (atomic เท่าที่ทำได้): validate รวม sum check B7 → สร้าง MA ใหม่ + รายการย่อย โดยตั้ง `renewed_from` = MA เดิม → อัปเดต MA เดิม `renewed_to` = MA ใหม่ และ `status` = `renewed` ("ต่ออายุแล้ว", เพิ่มใน `RENEWAL_STATUS_CHOICES`)
  - รายการย่อยใหม่เก็บ `renewed_from_item` → รายการย่อยเดิม (ถ้า copy มา; รายการที่เพิ่มใหม่เป็น null) เพื่อดูประวัติรายรายการย่อย
  - กันต่ออายุซ้ำ: ถ้า MA เดิมมี `renewed_to` แล้ว → ซ่อนปุ่มและ POST ถูก reject (ตรวจแบบ conditional update `renewed_to=None` กัน race กดสองครั้ง)
  - reminder module ข้าม MA ที่ `status=renewed`
  - หน้า detail แสดงแถบ relation ทั้งสองฝั่ง และ timeline ของสายการต่ออายุ (เดินตาม `renewed_from` / `renewed_to`)
- **Year filter**: filter ด้วยปีงบประมาณ พ.ศ. (ต.ค.–ก.ย.) จาก `start_date` ของรายการย่อย
- **Requisition**
  - Committees: กำหนด max ต่อ `committee_type` ใน form validation (ค่า default 3 ต่อประเภท, รอยืนยันจากงานพัสดุ — ระเบียบอาจกำหนดขั้นต่ำ 3 คน)
  - Timeline step-back: เพิ่ม action ย้อน 1 ขั้น ลบ `Progress` ล่าสุดและเขียน `RequisitionTimelineLogs` พร้อม metadata ว่า revert; จำกัดสิทธิ์ admin/staff พัสดุ; ห้ามย้อนจาก `completed` ถ้าเบิกจ่ายแล้ว
  - MAS delete: soft-delete (`status`) และ block เมื่อมี `Reservation` active
- **MAS**: ไม่ลบระบบ MAS ในรอบนี้ แต่ให้เป็น optional ระดับ organization (ขึ้นกับการตัดสินใจ E4)
- **Decimal audit**: ทุก field เงินใช้ `DecimalField(precision=2)` และ form ใช้ `DecimalField`; ห้าม sum เริ่มจาก `0` int/float ปน (ใช้ `Decimal("0")`)

## Testing Decisions

- test ที่ดี = test ผ่าน external behavior: ผลลัพธ์ของ function สาธารณะของ module หรือ HTTP response/DB state ผ่าน Flask test client ไม่ assert รายละเอียดภายใน (เช่น ชื่อ helper ภายใน หรือจำนวนครั้งที่ query)
- **Seams ที่เสนอ** (ใช้ของเดิมก่อน):
  1. **Flask test client + mongomock/test DB** (seam เดิม, `tests/conftest.py` fixtures `create_org`, `create_user`, `assign_user_to_org`) — ใช้กับ visibility, renewal form, year filter, committee validation, step-back, MAS delete, multi-tenant isolation
  2. **Reminder module `due_reminders(today)`** (seam ใหม่ seam เดียว) — pure function ที่ test ได้โดยส่ง `today` เข้าไป ครอบคลุม 3/2/1 เดือน, งวดจ่าย, custom dates, activation, dedupe ด้วย `ReminderLog`, การหยุดเตือนเมื่อต่ออายุ — ไม่ต้อง mock Redis/SMTP
- เคส visibility ที่ต้องมี: head/manager/admin/supervisor supplier เห็น MA ของทุกฝ่าย; เปิด filter "เฉพาะฝ่ายของฉัน" แล้วเหลือเฉพาะ MA ที่มีรายการย่อยของฝ่ายตัวเอง (รวม MA ที่มีหลายฝ่ายปนกัน); ผู้รับผิดชอบทั่วไปเห็นเฉพาะ MA ของตัวเองแม้ส่ง `division=mine`; user org อื่นไม่เห็นอะไรเลย
- เคส sum check (B7): ยอดตรงทั้ง 2 ชั้น → บันทึกได้; รายการย่อยรวมขาด/เกินยอด MA → ไม่บันทึกและ error บอกส่วนต่าง; งวดรวมไม่ตรงยอดรายการย่อย → ไม่บันทึก; ทศนิยมสตางค์ (เช่น 100,000 แบ่ง 3 งวด) ต้องผ่านโดยไม่มี rounding error; ฟอร์มต่ออายุและ import ก็โดนตรวจเหมือนกัน
- เคส renewal (E1): GET ฟอร์มต่ออายุแล้วไม่มีเอกสารใหม่ใน DB; POST แล้วได้ MA ใหม่ที่ `renewed_from` ชี้ MA เดิม และ MA เดิม `renewed_to` ชี้ MA ใหม่ + status `renewed`; ข้อมูล/งวดที่จ่ายแล้วของ MA เดิมไม่เปลี่ยน; POST ซ้ำกับ MA ที่ต่ออายุแล้วถูก reject; หน้า MA เดิมแสดงลิงก์ "ต่ออายุไปที่รายการ xxx แล้ว"; reminder ไม่ออกสำหรับ MA เดิม
- Modules ที่ test: Procurement/ProcurementItem (installment status, Decimal totals), Reminder module, visibility query helper (ผ่าน views), Requisition forms (committees), Timeline step-back, MAS delete
- Prior art: `tests/test_procurement_views.py` (cross-tenant isolation, ACL), `tests/test_car_feedback_logic.py` (logic test แบบ pure), `tests/test_car_applications_workflow.py` (workflow/state transition), `tests/test_multi_org.py`

## Out of Scope

- เชื่อมต่อ API กับระบบ MAS ของ ม.อ. โดยตรง
- ระบบลงนามอิเล็กทรอนิกส์บนเอกสารที่สร้าง
- การแจ้งเตือนผ่านช่องทางอื่นนอกจากอีเมล (LINE, SMS)
- redesign UI ทั้งโมดูลนอกเหนือจากหน้าที่กล่าวถึง

## Further Notes

- **บั๊กที่พบระหว่างสำรวจ (เกี่ยวกับ A7)**: scheduler ตั้งค่า `notified_90d`, `notified_30d`, `last_expiry_notification_date` บน `Procurement` แต่ field เหล่านี้ไม่ได้ประกาศใน model จึงอาจไม่ถูกบันทึกจริง → เสี่ยงส่งซ้ำหรือไม่ส่ง และการเตือนอิง `days_left == 90` แบบตรงวัน ถ้า scheduler ไม่ได้รันวันนั้นจะพลาดการเตือน; อีกทั้งปัจจุบันเตือนจาก "วันครบกำหนดงวดจ่าย" ไม่ใช่ "วันหมดอายุ" — reminder module ใหม่ควรใช้ `trigger_date <= today` + dedupe log แทน
- `Requisition.items` จำกัด `max_length=4` — ตรวจว่าขัดกับการรวมขั้นตอนที่ 3 หรือไม่
- E3 (สร้างเอกสาร) และ E4 (เลิกใช้ MAS ภายใน) ยังเป็น "อาจจะ" ต้องยืนยันกับงานพัสดุก่อนเริ่ม
- A6 (จำนวนวัสดุไม่ตรง) ข้อมูลจากประชุมไม่ครบ ต้องขอตัวอย่างรายการที่ไม่ตรงก่อน diagnose
- ลำดับแนะนำ: A (quick fixes) → B5/B7 (model + migration) → C (reminder module) → D → E
