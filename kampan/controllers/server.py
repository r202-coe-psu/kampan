import asyncio
import logging
import json
import datetime

from flask import current_app
from kampan import models, utils
from dateutil.relativedelta import relativedelta

from . import item_snapshot, procurement_status, payment_notifier
from ..web import redis_rq

logger = logging.getLogger(__name__)


class ControllerServer:
    def __init__(self, settings):
        self.settings = settings
        self.config = settings  # use redis_rq
        self.running = False
        self.item_queue = asyncio.Queue(maxsize=1000)
        self.procurement_queue = asyncio.Queue(maxsize=1000)
        self.notification_queue = asyncio.Queue(maxsize=1000)
        self.quarter = 0
        self.item_snapshot = item_snapshot.ItemSnapshot(self.settings)
        self.procurement_status_updater = procurement_status.ProcurementStatusUpdater(
            self.settings
        )
        self.payment_notifier = payment_notifier.PaymentNotifier(self.settings)

    async def handle_command(self, msg):
        raw_data = msg.data.decode()
        data = json.loads(raw_data)
        if data.get("action") == "process":
            # route to correct queue based on type
            if data.get("type") == "procurement":
                await self.procurement_queue.put(data)
            elif data.get("type") == "notification":
                await self.notification_queue.put(data)
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

                next_month = today + relativedelta(months=1)
                next_month_start = next_month.replace(day=1)
                time_set = datetime.datetime.combine(next_month_start, process_time)

                this_day_month_snap = datetime.datetime.combine(
                    today.replace(day=1), process_time
                )
                if datetime.datetime.now() <= this_day_month_snap:
                    # snap for this month
                    next_month = today + relativedelta(months=1)
                    next_month_start = next_month.replace(day=1)
                    time_set = datetime.datetime.combine(next_month_start, process_time)

                time_to_check = (time_set - datetime.datetime.now()).total_seconds()
                if time_to_check > 0:
                    logger.debug(
                        f"Sleeping for {time_to_check} seconds until {time_set}"
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

                procurements = models.Procurement.objects(payment_status__ne="paid")
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

    ### function to notify procurement status daily ###

    async def check_notification_payments_daily(self):
        time_check = self.settings["DAIRY_TIME_TO_SEND_PAYMENT_NOTIFICATION"]
        hour, minute = time_check.split(":")
        process_time = datetime.time(int(hour), int(minute), 0)
        procurements = models.Procurement.objects()

        while True:
            try:
                logger.debug("Start payment notifier daily check")

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

                procurements = models.Procurement.objects(
                    payment_status__in=["unpaid", "upcoming", "overdue"]
                )

                for notification in procurements:
                    status = notification.get_current_payment_status()
                    if status in ("upcoming", "overdue", "unpaid"):
                        due_dates = notification.get_payment_due_dates()
                        next_idx = notification.get_next_payment_index()

                        if next_idx < len(due_dates):
                            due_date = due_dates[next_idx]
                        else:
                            continue

                        days_left = (due_date - datetime.date.today()).days

                        if days_left > 90:
                            continue

                        notified_90d = getattr(notification, "notified_90d", False)
                        notified_30d = getattr(notification, "notified_30d", False)
                        last_expiry_notification_date = getattr(
                            notification, "last_expiry_notification_date", None
                        )
                        # if True:
                        if days_left == 90 and not notified_90d:
                            logger.info(
                                "Would enqueue 90d notification for %s",
                                str(notification.id),
                            )
                            notification.notified_90d = True
                            job = redis_rq.redis_queue.queue.enqueue(
                                utils.ma_send_emails.send_payment_notification_job,
                                args=[
                                    notification,
                                    "90d",
                                    {"days_left": days_left},
                                    dict(self.settings),
                                ],
                                timeout=600,
                                job_timeout=600,
                            )
                            notification.save()
                            logger.info(
                                "Enqueued job id=%s for 90d notification %s",
                                getattr(job, "id", None),
                                str(notification.id),
                            )

                        elif days_left == 30 and not notified_30d:
                            logger.info(
                                "Would enqueue 30d notification for %s",
                                str(notification.id),
                            )
                            notification.notified_30d = True
                            notification.save()
                            job = redis_rq.redis_queue.queue.enqueue(
                                utils.ma_send_emails.send_payment_notification_job,
                                args=[
                                    notification,
                                    "30d",
                                    {"days_left": days_left},
                                    dict(self.settings),
                                ],
                                timeout=600,
                                job_timeout=600,
                            )
                            logger.info(
                                "Enqueued job id=%s for 30d notification %s",
                                getattr(job, "id", None),
                                str(notification.id),
                            )

                        elif days_left < 0:
                            today_date = datetime.date.today()
                            if (
                                not last_expiry_notification_date
                                or last_expiry_notification_date != today_date
                            ):
                                logger.info(
                                    "Would enqueue expired notification for %s",
                                    str(notification.id),
                                )
                                notification.last_expiry_notification_date = today_date
                                notification.save()
                                job = redis_rq.redis_queue.queue.enqueue(
                                    utils.ma_send_emails.send_payment_notification_job,
                                    args=[
                                        notification,
                                        "expired",
                                        {"days_left": days_left},
                                        dict(self.settings),
                                    ],
                                    timeout=600,
                                    job_timeout=600,
                                )
                                logger.info(
                                    "Enqueued job id=%s for expired notification %s",
                                    getattr(job, "id", None),
                                    str(notification.id),
                                )

                        logger.debug(
                            "Procurement %s: status=%s days_left=%s notified_90d=%s notified_30d=%s last_expiry=%s",
                            str(notification.id),
                            status,
                            days_left,
                            getattr(notification, "notified_90d", False),
                            getattr(notification, "notified_30d", False),
                            getattr(
                                notification, "last_expiry_notification_date", None
                            ),
                        )

                        data = {
                            "action": "process",
                            "type": "notification",
                            "notification_id": str(notification.id),
                            "days_left": days_left,
                        }
                        await self.notification_queue.put(data)
                        await asyncio.sleep(0.01)

                self.quarter += 1
            except Exception as e:
                logger.exception(f"Error in payment notifier: {e}")

    async def process_notification_queue(self):
        logger.debug("start process notification queue")

        while self.running:
            data = await self.notification_queue.get()
            if data["type"] == "notification":
                await self.payment_notifier.process_data(data)

        logger.debug("end process notification queue")

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
        loop = asyncio.get_event_loop()
        loop.set_debug(True)
        loop.run_until_complete(self.set_up())
        item_task = loop.create_task(self.process_item_queue())
        daily_check_item = loop.create_task(self.check_items_daily())
        procurement_queue_task = loop.create_task(self.process_procurement_queue())
        procurement_status_task = loop.create_task(
            self.check_procurement_status_daily()
        )
        payment_notifier_queue_task = loop.create_task(
            self.process_notification_queue()
        )
        payment_notifier_task = loop.create_task(
            self.check_notification_payments_daily()
        )

        try:
            loop.run_forever()
        except Exception as e:
            self.running = False
        finally:
            loop.close()
