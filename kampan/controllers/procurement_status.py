import logging
import datetime
from kampan import models
from kampan.models.procurement import RENEWAL_WINDOW_DAYS  # ช่วง 90 วันก่อนหมดอายุ ใช้ร่วมกับ save_with_items

logger = logging.getLogger(__name__)


class ProcurementStatusUpdater:
    def __init__(self, settings=None):
        self.settings = settings
        models.init_mongoengine(settings)

    async def process_data(self, data={}):
        logger.debug("Start Process Procurement Data ")

        procurement_id = data.get("procurement_id")
        if not procurement_id:
            return

        procurement_id = str(procurement_id)
        procurement = models.Procurement.objects(id=procurement_id).first()

        if not procurement:
            return

        # สถานะการจ่ายคำนวณสดจากงวดของรายการย่อย (Procurement.get_payment_status) ไม่ต้องเก็บ
        today = datetime.date.today()
        end_date = procurement.get_end_date()
        if not end_date or end_date.date() > today + datetime.timedelta(days=RENEWAL_WINDOW_DAYS):
            return

        # เปลี่ยนเฉพาะ MA ที่ใช้งานอยู่ (active) ไม่ย้อน MA ที่ไม่ต่ออายุ / ต่ออายุแล้ว กลับมาเป็น pending
        updated = models.Procurement.objects(id=procurement.id, status="active").update_one(
            set__status="pending",
            set__updated_date=datetime.datetime.now(),
        )
        if updated:
            logger.info("Procurement %s moved to pending (item ends %s)", procurement.id, end_date)
