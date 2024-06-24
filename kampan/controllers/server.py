import asyncio
import logging
import json
from kampan import models
import datetime
from . import item_snapshot

logger = logging.getLogger(__name__)


class ControllerServer:
    def __init__(self, settings):
        self.settings = settings
        self.running = False
        self.item_queue = asyncio.Queue(maxsize=1000)
        self.quarter = 0
        self.item_snapshot = item_snapshot.ItemSnapshot(self.settings)

    async def handle_command(self, msg):
        raw_data = msg.data.decode()
        data = json.loads(raw_data)
        if data["action"] == "process":
            await self.item_queue.put(data)

    async def check_items_daily(self):
        time_check = self.settings["DAIRY_TIME_TO_SNAP_ITEM"]
        hour, minute = time_check.split(":")
        process_time = datetime.time(int(hour), int(minute), 0)
        items = models.Item.objects(status="active")

        month = datetime.datetime.now().month
        logger.debug(f"month {month}")

        now_year = datetime.datetime.now().year
        quarter_month = [10, 1, 4, 7]
        if month in quarter_month and (
            datetime.datetime(2024, 7, 1) != datetime.datetime(now_year, month % 12, 1)
        ):
            self.quarter = quarter_month.index(month)

        else:

            for i in range(12):
                month = month + 1
                if datetime.date(2024, 7, 1) == datetime.date(
                    now_year, (month) % 12, 1
                ):
                    continue
                elif month in quarter_month:
                    self.quarter = quarter_month.index(month)

                    break

        logger.debug(f"start at quarter M{month} Y{now_year} Q{self.quarter +1}")

        while self.running:
            logger.debug("start check item data daily")

            now_year = datetime.datetime.now().year
            # for item in items:

            #     data = {
            #         "action": "process",
            #         "type": "submit",
            #         "item_id": str(item.id),
            #     }
            #     await self.item_queue.put(data)
            #     await asyncio.sleep(0.01)
            quarter_year = [
                datetime.datetime(now_year, 10, 1),
                datetime.datetime(now_year + 1, 1, 1),
                datetime.datetime(now_year + 1, 4, 1),
                datetime.datetime(now_year + 1, 7, 1),
            ]

            time_to_check = quarter_year[self.quarter % 4] - datetime.datetime.now()

            logger.debug(f"sleep {time_to_check} after {datetime.datetime.now()}")
            await asyncio.sleep(time_to_check.total_seconds())

            items = models.Item.objects(status="active")
            for item in items:
                data = {
                    "action": "process",
                    "type": "submit",
                    "item_id": str(item.id),
                }
                await self.item_queue.put(data)
                await asyncio.sleep(0.01)
            self.quarter += 1
            await asyncio.sleep(10)

    async def process_item_queue(self):
        logger.debug("start process item queue")

        while self.running:

            data = await self.item_queue.get()
            if data["type"] == "submit":

                await self.item_snapshot.process_data(data)

        logger.debug("end process item queue")

    async def set_up(self):
        logging.basicConfig(
            format="%(asctime)s - %(name)s:%(levelname)s:%(lineno)d - %(message)s",
            datefmt="%d-%b-%y %H:%M:%S",
            level=logging.DEBUG,
        )

    def run(self):
        self.running = True
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.run_until_complete(self.set_up())
        item_task = loop.create_task(self.process_item_queue())
        daily_check_item = loop.create_task(self.check_items_daily())

        try:
            loop.run_forever()
        except Exception as e:
            self.running = False
        finally:
            loop.close()
