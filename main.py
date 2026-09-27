import asyncio, logging
from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart, Command
from maxapi.types import BotStarted, MessageCreated, MessageCallback, CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN
from database import (
    init_db, get_or_create_user, set_user_building, list_uks, list_buildings,
    get_building, list_categories, list_devices, get_device, get_analogs,
    add_subscription, list_user_subscriptions, CATEGORY_LABELS,
)
from keyboards import (
    uks_kb, buildings_kb, main_menu_kb, categories_kb, devices_kb,
    device_card_kb, notify_days_kb, soon_kb,
)
from handlers.common import get_user_id, get_chat_id, format_device_card, format_device_line
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bot")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    user_id = get_user_id(event)
    chat_id = get_chat_id(event) or user_id
    if user_id:
        await get_or_create_user(user_id)
    await bot.send_message(
        chat_id=chat_id,
        text="Здравствуйте! Я помогу следить за сроком службы оборудования в вашем доме.\n\nВыберите управляющую компанию:",
        attachments=[uks_kb(await list_uks()).as_markup()],
    )

@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    user_id = get_user_id(event)
    if user_id is not None:
        await get_or_create_user(user_id)
    await event.message.answer(
        "Здравствуйте! Я помогу следить за сроком службы оборудования в вашем доме.\n\n"
        "Выберите управляющую компанию:",
        attachments=[uks_kb(await list_uks()).as_markup()],
    )

@dp.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated):
    user_id = get_user_id(event)
    if user_id is None:
        await event.message.answer("Не удалось определить пользователя.")
        return
    user = await get_or_create_user(user_id)
    if not user.get("building_id"):
        await event.message.answer(
            "Сначала выберите дом:",
            attachments=[uks_kb(await list_uks()).as_markup()],
        )
        return
    bld = await get_building(user["building_id"])
    if bld is None:
        await event.message.answer(
            "Выбранный дом не найден. Выберите дом заново:",
            attachments=[uks_kb(await list_uks()).as_markup()],
        )
        return
    await event.message.answer(
        f"Дом: <b>{bld['name']}</b>\nЧто хотите сделать?",
        attachments=[main_menu_kb().as_markup()],
    )

@dp.message_callback()
async def on_callback(event: MessageCallback):
    payload = (
        getattr(event.callback, "payload", None)
        or getattr(event, "payload", "")
        or ""
    )
    if not payload or payload == "noop":
        await event.answer()
        return
    user_id = get_user_id(event)
    if user_id is None:
        await event.answer()
        return
    message = event.message
    if message is None:
        await event.answer()
        return
    parts = payload.split(":")
    action = parts[0]
    try:
        if action == "uk":
            buildings = await list_buildings(int(parts[1]))
            await message.edit(
                text="Выберите дом:",
                attachments=[
                    buildings_kb(buildings).as_markup()
                ],
            )
        elif action == "bld":
            bld = await get_building(int(parts[1]))
            if bld is None:
                await event.answer(notification="Дом не найден")
                return
            await set_user_building(
                user_id,
                bld["id"],
                bld["uk_id"],
            )
            await message.edit(
                text=(
                    f"Дом сохранён: <b>{bld['name']}</b>\n\n"
                    "Что хотите сделать?"
                ),
                attachments=[
                    main_menu_kb().as_markup()
                ],
            )
        elif action == "menu":
            menu = parts[1] if len(parts) > 1 else "main"
            await _menu(event, user_id, menu)
        elif action == "cat":
            category = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 1
            await _cat(
                event,
                user_id,
                category,
                page,
            )
        elif action == "dev":
            d = await get_device(int(parts[1]))
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            await message.edit(
                text=format_device_card(d),
                attachments=[
                    device_card_kb(d["id"]).as_markup()
                ],
            )
        elif action == "analog":
            device_id = int(parts[1])
            d = await get_device(device_id)
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            analogs = await get_analogs(d["type"])
            if not analogs:
                text = (
                    f"Аналоги для «{d['model']}» "
                    "пока в разработке."
                )
            else:
                text = (
                    f"Совместимые аналоги для "
                    f"«{d['model']}»:\n\n"
                    + "\n".join(
                        f"{i}. {a['model']}"
                        + (
                            f" — {a['specs']}"
                            if a.get("specs")
                            else ""
                        )
                        for i, a in enumerate(analogs, 1)
                    )
                )
            kb = InlineKeyboardBuilder()
            kb.row(
                CallbackButton(
                    text="◀ К карточке",
                    payload=f"dev:{device_id}",
                )
            )
            await message.edit(
                text=text,
                attachments=[kb.as_markup()],
            )
        elif action == "sub_menu":
            device_id = int(parts[1])

            await message.edit(
                text="За сколько дней напоминать?",
                attachments=[
                    notify_days_kb(device_id).as_markup()
                ],
            )
        elif action == "sub":
            device_id = int(parts[1])
            days = parts[2]
            d = await get_device(device_id)
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            if days == "all":
                for n in (90, 30, 7):
                    await add_subscription(
                        user_id,
                        device_id,
                        n,
                    )
                msg = "Подписки на 90/30/7 дней установлены."
            else:
                notify_days = int(days)
                ok = await add_subscription(
                    user_id,
                    device_id,
                    notify_days,
                )
                msg = (
                    f"Напоминание за {days} дн. установлено."
                    if ok
                    else "Уже есть."
                )
            await message.edit(
                text=f"{msg}\n\n{format_device_card(d)}",
                attachments=[
                    device_card_kb(device_id).as_markup()
                ],
            )
            await event.answer(notification=msg)
            return
        await event.answer()
    except Exception as e:
        logger.exception(e)
        await event.answer(notification="Ошибка")
        
async def _menu(event: MessageCallback, user_id: int, menu: str):
    user = await get_or_create_user(user_id)
    if menu == "uks":
        message = event.message
        if message is None:
            return
        await message.edit(
            text="Выберите УК:",
            attachments=[
                uks_kb(await list_uks()).as_markup()
            ],
        )
        return
    building_id = user.get("building_id")
    if building_id is None:
        message = event.message
        if message is None:
            return
        await message.edit(
            text="Сначала выберите дом:",
            attachments=[
                uks_kb(await list_uks()).as_markup()
            ],
        )
        return
    bld = await get_building(building_id)
    if bld is None:
        message = event.message
        if message is None:
            return
        await message.edit(
            text="Дом не найден. Выберите дом заново:",
            attachments=[
                uks_kb(await list_uks()).as_markup()
            ],
        )
        return
    message = event.message
    if message is None:
        return
    if menu == "main":
        await message.edit(
            text=f"Дом: <b>{bld['name']}</b>\nЧто хотите сделать?",
            attachments=[
                main_menu_kb().as_markup()
            ],
        )
    elif menu == "cats":
        cats = await list_categories(building_id)
        await message.edit(
            text="Категории оборудования:",
            attachments=[
                categories_kb(cats).as_markup()
            ],
        )
    elif menu == "soon":
        soon, _ = await list_devices(
            building_id,
            status="soon",
            per_page=15,
        )
        overdue, _ = await list_devices(
            building_id,
            status="overdue",
            per_page=15,
        )
        all_crit = overdue + soon
        if not all_crit:
            await message.edit(
                text="✅ Критичных устройств нет.",
                attachments=[
                    main_menu_kb().as_markup()
                ],
            )
        else:
            lines = [
                f"⚠️ Требуют внимания ({len(all_crit)}):\n"
            ]
            lines += [
                format_device_line(d)
                for d in all_crit[:12]
            ]
            await message.edit(
                text="\n".join(lines),
                attachments=[
                    soon_kb(all_crit[:12]).as_markup()
                ],
            )
    elif menu == "subs":
        subs = await list_user_subscriptions(user_id)
        if not subs:
            text = "У вас пока нет подписок."
        else:
            text = (
                "🔔 Ваши подписки:\n\n"
                + "\n".join(
                    f"• {s['type']} «{s['model']}» — "
                    f"за {s['notify_days']} дн. "
                    f"({s['replace_at']})"
                    for s in subs
                )
            )
        await message.edit(
            text=text,
            attachments=[
                main_menu_kb().as_markup()
            ],
        )

async def _cat(event, user_id, category, page):
    user = await get_or_create_user(user_id)
    if not user.get("building_id"):
        return
    devices, total = await list_devices(user["building_id"], category=category, page=page)
    label = CATEGORY_LABELS.get(category, category)
    await event.message.edit(
        text=f"{label}, стр. {page}:" if devices else f"{label}: пусто",
        attachments=[devices_kb(devices, category, page, total).as_markup()],
    )

@dp.message_created(F.message.body.text)
async def on_text(event: MessageCreated):
    await event.message.answer("Используйте кнопки или /start /menu")

async def main():
    await init_db()
    start_scheduler(bot)
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    logger.info("Long polling started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())