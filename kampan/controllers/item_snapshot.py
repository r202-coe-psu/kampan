from kampan import models
import logging
import datetime
import asyncio
import decimal

logger = logging.getLogger(__name__)


class ItemSnapshot:
    def __init__(self, settings):
        self.settings = settings
        models.init_mongoengine(settings)

    async def snapshot_items(self, item=None):

        item_snapshot = models.items.ItemSnapshot(
            item=item,
            amount=item.get_amount_pieces(),
            organization=item.organization,
        )

        last_price = item.get_last_price()
        last_price_per_piece = item.get_last_price_per_piece()
        remaining_balance = item.get_remaining_balance()
        if last_price:
            item_snapshot.last_price = decimal.Decimal(last_price)

        if last_price_per_piece:
            item_snapshot.last_price_per_piece = decimal.Decimal(last_price_per_piece)

        if remaining_balance:
            item_snapshot.remaining_balance = decimal.Decimal(remaining_balance)

        try:
            item_snapshot.save()
            item_snapshot.update_data()
        except Exception as e:
            logger.debug(e)

    async def process_data(self, data={}):
        logger.debug("Start Process Data ")

        if "item_id" not in data:
            return

        item_id = str(data["item_id"])
        logger.debug("Start snapshot item id: " + item_id)
        item = models.items.Item.objects(id=item_id).first()

        if not item:
            return

        await self.snapshot_items(item)
        await asyncio.sleep(0.01)

        logger.debug("Snapshot Success item id: " + item_id)
