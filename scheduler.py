import asyncio, logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import RATE_LIMIT_DELAY
from database import recount_statuses, devices_for_notification, subscriptions_for_device
from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

logger = logging.getLogger("scheduler")
scheduler = AsyncIOScheduler()

async def daily_job(bot):
    logger.info("Daily job started")
    await recount_statuses()
    for days in (90, 30, 7):
        for d in await devices_for_notification(days):
            for s in await subscriptions_for_device(d["id"], days):
                text = (
                    f"⚠️ <b>{d['type']}</b> «{d['model']}»\n"
                    f"Замена через {days} дн.\nДата: {d['replace_at']}"
                )
                kb = InlineKeyboardBuilder()
                kb.row(CallbackButton(text="Открыть карточку", payload=f"dev:{d['id']}"))
                try:
                    await bot.send_message(
                        user_id=s["max_user_id"],
                        text=text,
                        attachments=[kb.as_markup()],
                    )
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                except Exception as e:
                    logger.warning("Notify failed %s: %s", s["max_user_id"], e)
    logger.info("Daily job finished")

def start_scheduler(bot) -> None:
    scheduler.add_job(daily_job, "cron", hour=9, minute=0, args=[bot], id="daily_notify", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started (09:00)")