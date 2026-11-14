import asyncio
import logging
import json
import datetime

from flask import current_app
from kampan import models
from dateutil.relativedelta import relativedelta

from . import item_snapshot, procurement_status, reminder_scheduler
from ..web import redis_rq

logger = logging.getLogger(__name__)


class ControllerServer:
    def __init__(self, settings):
        self.settings = settings
        self.config = settings  # use redis_rq
        self.running = False
        self.item_queue = asyncio.Queue(maxsize=1000)
        self.procurement_queue = asyncio.Queue(maxsize=1000)
        self.quarter = 0
        self.item_snapshot = item_snapshot.ItemSnapshot(self.settings)
        self.procurement_status_updater = procurement_status.ProcurementStatusUpdater(
            self.settings
        )

    async def handle_command(self, msg):
        raw_data = msg.data.decode()
        data = json.loads(raw_data)
        if data.get("action") == "process":
            # route to correct queue based on type
            if data.get("type") == "procurement":
                await self.procurement_queue.put(data)
            else:
                await self.item_queue.put(data)

    async def check_items_daily(self):
        time_check = self.settings["DAIRY_TIME_TO_SNAP_ITEM"]
        hour, minute = time_check.split(":")
        process_time = datetime.time(int(hour), int(minute), 0)
        items = models.Item.objects(status="active")

        while self.running:
            try:
                logger.debug("Start checking item data monthly")

                today = datetime.date.today()

                this_day_month_snap = datetime.datetime.combine(
                    datetime.date.today().replace(day=1), process_time
                )
                next_month = today + relativedelta(months=1)
                next_month_start = next_month.replace(day=1)
                logger.debug("This day month snap: %s", this_day_month_snap)
                if datetime.datetime.now() <= this_day_month_snap:
                    # snap for this month
                    logger.debug(
                        "Setting time to snap for this month: %s", this_day_month_snap
                    )
                    time_set = datetime.datetime.combine(today, process_time)
                else:
                    # snap for next month
                    time_set = datetime.datetime.combine(next_month_start, process_time)
                logger.debug("Next snap time set to: %s", time_set)
                time_to_check = (time_set - datetime.datetime.now()).total_seconds()
                if time_to_check > 0:
                    logger.debug(
                        f"===> Sleeping for {time_to_check} seconds until {time_set}"
                    )
                    await asyncio.sleep(time_to_check)

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
            except Exception as e:
                logger.error(f"Error in check_items_daily: {e}")

    async def process_item_queue(self):
        logger.debug("start process item queue")

        while self.running:

            data = await self.item_queue.get()
            if data["type"] == "submit":

                await self.item_snapshot.process_data(data)

        logger.debug("end process item queue")

    ### function to check procurement status daily ###

    async def check_procurement_status_daily(self):
        time_check = self.settings["DAIRY_TIME_TO_UPDATE_STATUS_PROCUREMENT"]
        hour, minute = time_check.split(":")
        process_time = datetime.time(int(hour), int(minute), 0)
        procurements = models.Procurement.objects()

        while self.running:
            try:
                logger.debug("Start checking procurement status daily")

                now = datetime.datetime.now()
                time_set = datetime.datetime.combine(now.date(), process_time)

                if now >= time_set:
                    next_day = now.date() + datetime.timedelta(days=1)
                    time_set = datetime.datetime.combine(next_day, process_time)

                time_to_check = (time_set - now).total_seconds()
                if time_to_check > 0:
                    logger.debug(
                        f"Sleeping for {time_to_check} seconds until {time_set}"
                    )
                    await asyncio.sleep(time_to_check)

                # สถานะการจ่ายคำนวณสดจากงวด งานนี้อัปเดตสถานะการใช้งาน (usage_status) ของ MA ที่ไม่ใช่แบบร่าง
                procurements = models.Procurement.objects(status__ne="draft").only("id")
                for procurement in procurements:
                    data = {
                        "action": "process",
                        "type": "procurement",
                        "procurement_id": str(procurement.id),
                    }
                    await self.procurement_queue.put(data)
                    await asyncio.sleep(0.01)

                self.quarter += 1
            except Exception as e:
                logger.error(f"Error in check_procurement_status_daily: {e}")

    async def process_procurement_queue(self):
        logger.debug("start process procurement queue")

        while self.running:
            data = await self.procurement_queue.get()
            if data["type"] == "procurement":
                await self.procurement_status_updater.process_data(data)

        logger.debug("end process procurement queue")

    ##################

    ### เตือน MA รายวัน (#28) ###

    async def check_notification_payments_daily(self):
        """วันละครั้งตามเวลา DAIRY_TIME_TO_SEND_PAYMENT_NOTIFICATION: สร้าง log + enqueue อีเมลเตือนที่ถึงกำหนด"""
        time_check = self.settings["DAIRY_TIME_TO_SEND_PAYMENT_NOTIFICATION"]
        hour, minute = time_check.split(":")
        process_time = datetime.time(int(hour), int(minute), 0)

        while self.running:
            try:
                now = datetime.datetime.now()
                time_set = datetime.datetime.combine(now.date(), process_time)
                if now >= time_set:
                    time_set = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), process_time)

                time_to_check = (time_set - now).total_seconds()
                if time_to_check > 0:
                    logger.debug(f"Reminder: sleeping for {time_to_check} seconds until {time_set}")
                    await asyncio.sleep(time_to_check)

                logs = reminder_scheduler.enqueue_due_reminders(
                    datetime.date.today(), self.settings, redis_rq.redis_queue.queue
                )
                logger.info("Reminder: enqueued %s reminders", len(logs))
            except Exception as e:
                logger.exception(f"Error in reminder scheduler: {e}")

    ##################

    async def set_up(self):
        logging.basicConfig(
            format="%(asctime)s - %(name)s:%(levelname)s:%(lineno)d - %(message)s",
            datefmt="%d-%b-%y %H:%M:%S",
            level=logging.DEBUG,
        )
        logging.getLogger("pymongo").setLevel(logging.WARNING)

    def run(self):
        self.running = True
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_debug(True)
        loop.run_until_complete(self.set_up())
        item_task = loop.create_task(self.process_item_queue())
        daily_check_item = loop.create_task(self.check_items_daily())
        procurement_queue_task = loop.create_task(self.process_procurement_queue())
        procurement_status_task = loop.create_task(
            self.check_procurement_status_daily()
        )
        reminder_task = loop.create_task(self.check_notification_payments_daily())

        try:
            loop.run_forever()
        except Exception as e:
            self.running = False
        finally:
            loop.close()
