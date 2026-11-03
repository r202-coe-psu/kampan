from kampan import models

cft = models.car_form_templates

_PAPER_STYLE = """<style>
.car-paper { font-family: 'THSarabunNew', 'Sarabun', sans-serif; font-size: 18px; line-height: 1.5; color: #000; }
.car-paper .title { text-align: center; font-weight: bold; font-size: 22px; }
.car-paper .subtitle { text-align: center; }
.car-paper .right { text-align: right; }
.car-paper .fill { border-bottom: 1px dotted #000; padding: 0 6px; display: inline-block; min-width: 60px; text-align: center; }
.car-paper .indent { padding-left: 32px; }
.car-paper .sign { text-align: right; margin-top: 12px; }
.car-paper .box { border-top: 1.5px solid #000; margin-top: 14px; padding-top: 8px; }
</style>"""

_BOX_MACRO = "{% macro box(on) %}{{ '☑' if on else '☐' }}{% endmacro %}"

_DIIS_GENERAL_PAPER = _PAPER_STYLE + _BOX_MACRO + """
<div class="car-paper">
  <div class="title">ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ</div>
  <div class="right">วันที่ <span class="fill">{{ app.created.day }}</span>
    เดือน <span class="fill">{{ app.created.month_th }}</span>
    พ.ศ. <span class="fill">{{ app.created.year_be }}</span></div>
  <div><b>เรียน ผู้ควบคุมยานพาหนะ</b></div>
  <div>ข้าพเจ้า <span class="fill">{{ app.requester_name }}</span>
    ฝ่าย <span class="fill">{{ app.division }}</span>
    โทร <span class="fill">{{ app.phone }}</span></div>
  <div>มีความประสงค์จะขอใช้รถยนต์ เพื่อเดินทางไปปฏิบัติงาน ตามรายละเอียดดังต่อไปนี้</div>
  <div>ไปปฏิบัติงานที่ <span class="fill">{{ app.location }}</span></div>
  <div class="indent">
    <div>ไปปฏิบัติงานเรื่อง <span class="fill">{{ app.request_reason }}</span>
      จำนวนผู้โดยสาร <span class="fill">{{ app.passenger_number or '' }}</span> คน</div>
    <div>ในวันที่ <span class="fill">{{ app.departure.day }} {{ app.departure.month_th }} {{ app.departure.year_be }}</span>
      เวลา <span class="fill">{{ app.departure.time }}</span> น.
      ถึงเวลา <span class="fill">{{ app.return.time }}</span> น.</div>
  </div>
  <div class="sign">ลงชื่อ <span class="fill">{{ app.requester_name }}</span> ผู้ขอใช้</div>
  <div class="sign">ลงชื่อ <span class="fill">{{ approvals.head.name }}</span> หัวหน้าฝ่าย</div>
  <div class="sign">วันที่ <span class="fill">{{ approvals.head.date }}</span></div>
  <div class="box">
    <b>สำหรับผู้ควบคุมยานพาหนะ</b>
    <div>รถทะเบียน <span class="fill">{{ app.car_plate }}</span>
      พนักงานขับรถ <span class="fill">{{ app.driver_name }}</span></div>
    <div class="sign">ลงชื่อ <span class="fill">{{ approvals.admin.name }}</span> ผู้ควบคุมยานพาหนะ</div>
    <div class="sign">วันที่ <span class="fill">{{ approvals.admin.date }}</span></div>
  </div>
</div>
"""

_PHYSICAL_DOMESTIC_PAPER = _PAPER_STYLE + _BOX_MACRO + """
<div class="car-paper">
  <div class="title">ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ</div>
  <div class="subtitle">งานยุทธศาสตร์และบริการกลาง กองกายภาพและสิ่งแวดล้อม</div>
  <div class="right">วันที่ <span class="fill">{{ app.created.day }}</span>
    เดือน <span class="fill">{{ app.created.month_th }}</span>
    พ.ศ. <span class="fill">{{ app.created.year_be }}</span></div>
  <div><b>เรียน ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม</b></div>
  <div>ด้วย คณะ/หน่วยงาน <span class="fill">{{ app.division }}</span>
    หมายเลขโทรศัพท์ <span class="fill">{{ app.phone }}</span></div>
  <div>มีความประสงค์จะขอใช้รถยนต์
    {{ box(details.vehicle_kind == 'บัส') }} บัส
    {{ box(details.vehicle_kind == 'ตู้') }} ตู้
    {{ box(details.vehicle_kind == 'เก๋ง') }} เก๋ง
    {{ box(details.vehicle_kind == 'มินิบัส') }} มินิบัส</div>
  <div>พร้อมพนักงานขับรถ จำนวน <span class="fill">{{ details.vehicle_count }}</span> คัน
    มีผู้โดยสาร <span class="fill">{{ app.passenger_number or '' }}</span> คน
    เพื่อไปปฏิบัติงานที่ <span class="fill">{{ app.location }}</span>
    อำเภอ <span class="fill">{{ details.district }}</span>
    จังหวัด <span class="fill">{{ details.province }}</span>
    ด้วยเรื่อง <span class="fill">{{ app.request_reason }}</span>
    เลขที่โครงการ/หนังสือ <span class="fill">{{ details.custom_project_no }}</span></div>
  <div>ในวันที่ <span class="fill">{{ app.departure.day }} {{ app.departure.month_th }} {{ app.departure.year_be }}</span>
    ขอให้รถไปจอดรับที่ <span class="fill"></span>
    เวลา <span class="fill">{{ app.departure.time }}</span> น.
    และรถจะเดินทางกลับถึงมหาวิทยาลัยในวันที่ <span class="fill">{{ app.return.day }} {{ app.return.month_th }} {{ app.return.year_be }}</span>
    เวลาประมาณ <span class="fill">{{ app.return.time }}</span> น.</div>
  <div>ผู้รับผิดชอบค่าใช้จ่าย
    {{ box('ค่าน้ำมันเชื้อเพลิง' in details.cost_responsibility) }} ค่าน้ำมันเชื้อเพลิง
    {{ box('เบี้ยเลี้ยง' in details.cost_responsibility) }} เบี้ยเลี้ยง
    {{ box('ค่าที่พักของพนักงานขับรถ' in details.cost_responsibility) }} ค่าที่พักของพนักงานขับรถ
    {{ box('ไม่รับผิดชอบ' in details.cost_responsibility) }} ไม่รับผิดชอบ</div>
  <div class="sign">ลงชื่อ <span class="fill">{{ app.requester_name }}</span> ผู้ขอใช้รถ</div>
  <div class="sign">ลงชื่อ <span class="fill">{{ approvals.head.name }}</span> ผู้บังคับบัญชาของผู้ขอใช้รถ</div>
  <div class="sign">วันที่ <span class="fill">{{ approvals.head.date }}</span></div>
  <div class="box">
    <b>สำหรับเจ้าหน้าที่จัดบริการรถยนต์</b>
    <div>รถทะเบียน <span class="fill">{{ app.car_plate }}</span>
      พนักงานขับรถ <span class="fill">{{ app.driver_name }}</span></div>
    <div class="sign">ลงชื่อ <span class="fill">{{ approvals.admin.name }}</span> ผู้จัดรถบริการ</div>
    <div class="sign">ลงชื่อ <span class="fill">{{ approvals.approver.name }}</span> ผู้อนุมัติ</div>
    <div class="sign">วันที่ <span class="fill">{{ approvals.approver.date }}</span></div>
  </div>
  <div class="box">
    <div><b>เรียน ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม</b></div>
    <div>เพื่อโปรดพิจารณา
      {{ box(approvals.director.decision == 'approved') }} อนุมัติ
      {{ box(approvals.director.decision == 'denied') }} ไม่อนุมัติ</div>
    <div class="sign">ลงชื่อ <span class="fill">{{ approvals.director.name }}</span> ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม</div>
    <div class="sign">วันที่ <span class="fill">{{ approvals.director.date }}</span></div>
  </div>
  <div class="box">เลข ก.ม. ออก <span class="fill"></span>
    เลข ก.ม. กลับ <span class="fill"></span>
    รวมระยะทาง <span class="fill"></span> ก.ม.
    เป็นเงิน <span class="fill"></span> บาท</div>
</div>
"""


def _physical_domestic(approver_user):
    if approver_user is not None:
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="user",
            user=approver_user,
        )
    else:
        # ไม่ระบุตัวผู้อนุมัติ: fallback เป็น role endorser (ต้องระบุตัวคนภายหลัง)
        approver_step = cft.ApprovalStepDef(
            key="approver",
            label="ผู้อนุมัติ",
            approver_type="role",
            role="endorser",
        )
    return dict(
        name="ใบขอใช้รถยนต์ไปปฏิบัติงานภายในประเทศ",
        fields=[
            cft.FormFieldDef(source="catalog", key="vehicle_kind", is_required=True),
            cft.FormFieldDef(source="catalog", key="vehicle_count"),
            cft.FormFieldDef(source="catalog", key="district"),
            cft.FormFieldDef(source="catalog", key="province", is_required=True),
            cft.FormFieldDef(source="catalog", key="cost_responsibility"),
            cft.FormFieldDef(
                source="custom",
                key="project_no",
                label="เลขที่โครงการ/หนังสือ",
                field_type="text",
            ),
        ],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="ผู้บังคับบัญชาผู้ขอใช้รถ",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้จัดรถบริการ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
            approver_step,
            cft.ApprovalStepDef(
                key="director",
                label="ผู้อำนวยการกองกายภาพและสิ่งแวดล้อม",
                approver_type="role",
                role="director",
            ),
        ],
        paper_html=_PHYSICAL_DOMESTIC_PAPER,
    )


def _diis_general(approver_user):
    return dict(
        name="ใบขอใช้รถยนต์ของสำนักนวัตกรรมดิจิทัลและระบบอัจฉริยะ (ทั่วไป)",
        fields=[],
        steps=[
            cft.ApprovalStepDef(
                key="head",
                label="หัวหน้าฝ่าย",
                approver_type="role",
                role="head",
                same_division=True,
            ),
            cft.ApprovalStepDef(
                key="admin",
                label="ผู้ควบคุมยานพาหนะ",
                approver_type="role",
                role="admin",
                assigns_vehicle=True,
            ),
        ],
        paper_html=_DIIS_GENERAL_PAPER,
    )


_BUILDERS = {
    "diis_general": _diis_general,
    "physical_domestic": _physical_domestic,
}
TEMPLATE_KEYS = tuple(_BUILDERS)


def seed_template(organization, key, created_by=None, approver_user=None):
    spec = _BUILDERS[key](approver_user)
    existing = cft.CarFormTemplate.objects(
        organization=organization, name=spec["name"]
    ).first()
    if existing:
        return existing
    template = cft.CarFormTemplate(
        organization=organization,
        created_by=created_by,
        last_updated_by=created_by,
        **spec,
    )
    template.save()
    return template

