import logging
import datetime
from kampan import models

logger = logging.getLogger(__name__)


class PaymentNotifier:
    def __init__(self, settings=None):
        self.settings = settings
        models.init_mongoengine(settings)

    async def process_data(self, data={}):
        logger.debug("Start Process notification Data ")

        notification_id = data.get("notification_id")
        if not notification_id:
            return

        notification = models.Procurement.objects(id=notification_id).first()
        if not notification:
            return

        logger.debug(
            f"Processing payment notification for notification ID: {notification_id}"
        )
