import logging
import datetime
from kampan import models

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

        procurement = models.Procurement.objects(id=str(procurement_id)).first()
        if not procurement or procurement.status == "draft":
            return

        # สถานะการจ่ายคำนวณสดจากงวดของรายการย่อย ไม่ต้องเก็บ งานนี้อัปเดตเฉพาะสถานะการใช้งาน (usage_status)
        # ของทุก MA ที่ไม่ใช่แบบร่าง (สถานะการต่ออายุเปลี่ยนด้วยคนเท่านั้น)
        if procurement.refresh_usage_status(datetime.date.today()):
            logger.info("Procurement %s usage status is now %s", procurement.id, procurement.usage_status)
