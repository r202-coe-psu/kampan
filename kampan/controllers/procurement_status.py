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

        procurement_id = data.get("procurement_id") or data.get("item_id")
        if not procurement_id:
            return

        procurement_id = str(procurement_id)
        procurement = models.Procurement.objects(id=procurement_id).first()

        if not procurement:
            return

        today = datetime.date.today()
        old_status = procurement.payment_status
        new_status = procurement.get_current_payment_status(today)
        if old_status != new_status:
            procurement.payment_status = new_status
            procurement.save()
