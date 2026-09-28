import asyncio
import logging

from config import UK_ADMIN_PASSWORD

from maxapi import Bot, Dispatcher, F
from maxapi.filters.command import CommandStart, Command
from maxapi.types import (
    BotStarted,
    MessageCreated,
    MessageCallback,
    CallbackButton,
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

BOT_TOKEN = "f9LHodD0cOLgvKhku0FDBFIifaz1ycD1XKRBTRt5TDdxrjgeff39sS8sv9RaLkbfGc74cQieBtyouZoo1IAK"
bot = Bot(token=BOT_TOKEN)

from database import (
    init_db,
    get_or_create_user,
    set_user_building,
    list_cities,
    list_uks_by_city,
    list_buildings,
    get_building,
    list_categories,
    list_devices,
    get_device,
    get_analogs,
    add_subscription,
    list_user_subscriptions,
    set_user_role,
    get_uk_summary, 
    list_critical_by_uk,
    STATUS_EMOJI,
    CATEGORY_LABELS,
)
from keyboards import (
    cities_kb,
    uks_kb,
    buildings_kb,
    main_menu_kb,
    categories_kb,
    devices_kb,
    device_card_kb,
    notify_days_kb,
    soon_kb,
    role_kb,
)
from handlers.common import (
    get_user_id,
    get_chat_id,
    format_device_card,
    format_device_line,
)
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("bot")

dp = Dispatcher()


# Старт

@dp.bot_started()
async def on_bot_started(event: BotStarted):
    user_id = get_user_id(event)
    chat_id = get_chat_id(event) or user_id
    if user_id:
        await get_or_create_user(user_id)
    cities = await list_cities()
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "Здравствуйте! Я помогу следить за сроком службы "
            "оборудования в вашем доме.\n\n"
            "Сначала выберите город:"
        ),
        attachments=[cities_kb(cities).as_markup()],
    )


@dp.message_created(CommandStart())
async def cmd_start(event: MessageCreated):
    user_id = get_user_id(event)
    if user_id is not None:
        await get_or_create_user(user_id)
    cities = await list_cities()
    await event.message.answer(
        "Здравствуйте! Я помогу следить за сроком службы "
        "оборудования в вашем доме.\n\n"
        "Сначала выберите город:",
        attachments=[cities_kb(cities).as_markup()],
    )


@dp.message_created(Command("menu"))
async def cmd_menu(event: MessageCreated):
    user_id = get_user_id(event)
    if user_id is None:
        await event.message.answer("Не удалось определить пользователя.")
        return
    user = await get_or_create_user(user_id)
    if not user.get("building_id"):
        cities = await list_cities()
        await event.message.answer(
            "Сначала выберите город:",
            attachments=[cities_kb(cities).as_markup()],
        )
        return
    bld = await get_building(user["building_id"])
    if bld is None:
        cities = await list_cities()
        await event.message.answer(
            "Выбранный дом не найден. Выберите город заново:",
            attachments=[cities_kb(cities).as_markup()],
        )
        return
    await event.message.answer(
        f"Дом: <b>{bld['name']}</b>\nЧто хотите сделать?",
        attachments=[main_menu_kb().as_markup()],
    )


# Колбеки

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

    parts = payload.split(":")
    action = parts[0]
    logger.info("callback payload=%s user=%s", payload, user_id)

    try:
        # Из города в ук
        if action == "city":
            city = ":".join(parts[1:])
            uks = await list_uks_by_city(city)
            logger.info("city=%s uks=%s", city, [u["name"] for u in uks])

            if not uks:
                await event.edit(
                    text=f"В городе «{city}» пока нет УК в базе.",
                    attachments=[cities_kb(await list_cities()).as_markup()],
                )
            else:
                await event.edit(
                    text=f"Город: {city}\nВыберите управляющую компанию:",
                    attachments=[uks_kb(uks, city).as_markup()],
                )
            return

        # Из ук в дом 
        if action == "uk":
            uk_id = int(parts[1])
            city = ":".join(parts[2:]) if len(parts) > 2 else None
            buildings = await list_buildings(uk_id, city=city)
            logger.info("uk=%s city=%s buildings=%s", uk_id, city, len(buildings))

            if not buildings:
                text = "У этой УК в выбранном городе пока нет домов."
                if city:
                    uks = await list_uks_by_city(city)
                    await event.edit(
                        text=text,
                        attachments=[uks_kb(uks, city).as_markup()],
                    )
                else:
                    await event.edit(
                        text=text,
                        attachments=[cities_kb(await list_cities()).as_markup()],
                    )
            else:
                await event.edit(
                    text="Выберите дом (ЖК):",
                    attachments=[buildings_kb(buildings, city or "", uk_id).as_markup()],
                )
            return

        # дом выбран
        if action == "bld":
            bld = await get_building(int(parts[1]))
            if bld is None:
                await event.answer(notification="Дом не найден")
                return
            await set_user_building(user_id, bld["id"], bld["uk_id"])
            await event.edit(
                text=f"Дом сохранён: {bld['name']}\n\nКто вы?",
                attachments=[role_kb().as_markup()],
            )
            return

        # выбор роли 
        if action == "role":
            role_action = parts[1]

            if role_action == "owner":
                user = await get_or_create_user(user_id)
                await set_user_role(user_id, "owner", uk_id=user.get("uk_id"))
                bld = None
                if user.get("building_id"):
                    bld = await get_building(user["building_id"])
                name = bld["name"] if bld else "дом"
                await event.edit(
                    text=f"Роль: Собственник\nДом: {name}\n\nЧто хотите сделать?",
                    attachments=[main_menu_kb("owner").as_markup()],
                )
                return

            if role_action == "uk_admin_request":
                # ждём пароль — ставим временную роль
                user = await get_or_create_user(user_id)
                await set_user_role(user_id, "pending_uk", uk_id=user.get("uk_id"))
                await event.edit(
                    text=(
                        "Введите пароль диспетчера УК.\n"
                        "Напишите его обычным сообщением в этот чат."
                    ),
                    attachments=[],
                )
                return

        # менюшка 
        if action == "menu":
            menu = parts[1] if len(parts) > 1 else "main"
            await _menu(event, user_id, menu)
            return

        # категория ъ
        if action == "cat":
            category = parts[1]
            page = int(parts[2]) if len(parts) > 2 else 1
            await _cat(event, user_id, category, page)
            return

        # карточка устройства 
        if action == "dev":
            d = await get_device(int(parts[1]))
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            await event.edit(
                text=format_device_card(d),
                attachments=[device_card_kb(d["id"]).as_markup()],
            )
            return

        # аналоги 
        if action == "analog":
            device_id = int(parts[1])
            d = await get_device(device_id)
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            analogs = await get_analogs(d["type"])
            if not analogs:
                text = f"Аналоги для «{d['model']}» пока в разработке."
            else:
                text = (
                    f"Совместимые аналоги для «{d['model']}»:\n\n"
                    + "\n".join(
                        f"{i}. {a['model']}"
                        + (f" — {a['specs']}" if a.get("specs") else "")
                        for i, a in enumerate(analogs, 1)
                    )
                )
            kb = InlineKeyboardBuilder()
            kb.row(CallbackButton(text="◀ К карточке", payload=f"dev:{device_id}"))
            await event.edit(text=text, attachments=[kb.as_markup()])
            return

        # меню подписки
        if action == "sub_menu":
            device_id = int(parts[1])
            await event.edit(
                text="За сколько дней напоминать?",
                attachments=[notify_days_kb(device_id).as_markup()],
            )
            return

        # сама подписка
        if action == "sub":
            device_id = int(parts[1])
            days = parts[2]
            d = await get_device(device_id)
            if d is None:
                await event.answer(notification="Устройство не найдено")
                return
            if days == "all":
                for n in (90, 30, 7):
                    await add_subscription(user_id, device_id, n)
                msg = "Подписки на 90/30/7 дней установлены."
            else:
                ok = await add_subscription(user_id, device_id, int(days))
                msg = (
                    f"Напоминание за {days} дн. установлено."
                    if ok
                    else "Уже есть."
                )
            await event.edit(
                text=f"{msg}\n\n{format_device_card(d)}",
                attachments=[device_card_kb(device_id).as_markup()],
            )
            return

        await event.answer()

    except Exception as e:
        logger.exception(e)
        await event.answer(notification="Ошибка")

# вспомогательные функции

async def _menu(event: MessageCallback, user_id: int, menu: str):
    if menu in ("cities", "uks"):
        cities = await list_cities()
        await event.edit(
            text="Выберите город:",
            attachments=[cities_kb(cities).as_markup()],
        )
        return

    user = await get_or_create_user(user_id)
    role = user.get("role") or "owner"
    building_id = user.get("building_id")

    if building_id is None:
        cities = await list_cities()
        await event.edit(
            text="Сначала выберите город:",
            attachments=[cities_kb(cities).as_markup()],
        )
        return

    bld = await get_building(building_id)
    if bld is None:
        cities = await list_cities()
        await event.edit(
            text="Дом не найден. Выберите город заново:",
            attachments=[cities_kb(cities).as_markup()],
        )
        return

    if menu == "main":
        await event.edit(
            text=f"Дом: {bld['name']}\nЧто хотите сделать?",
            attachments=[main_menu_kb(role).as_markup()],
        )

    elif menu == "cats":
        cats = await list_categories(building_id)
        await event.edit(
            text="Категории оборудования:",
            attachments=[categories_kb(cats).as_markup()],
        )

    elif menu == "soon":
        soon, _ = await list_devices(building_id, status="soon", per_page=15)
        overdue, _ = await list_devices(building_id, status="overdue", per_page=15)
        all_crit = overdue + soon
        if not all_crit:
            await event.edit(
                text="✅ Критичных устройств нет.",
                attachments=[main_menu_kb(role).as_markup()],
            )
        else:
            lines = [f"⚠️ Требуют внимания ({len(all_crit)}):\n"]
            lines += [format_device_line(d) for d in all_crit[:12]]
            await event.edit(
                text="\n".join(lines),
                attachments=[soon_kb(all_crit[:12]).as_markup()],
            )

    elif menu == "subs":
        subs = await list_user_subscriptions(user_id)
        if not subs:
            text = "У вас пока нет подписок."
        else:
            text = "🔔 Ваши подписки:\n\n" + "\n".join(
                f"• {s['type']} «{s['model']}» — за {s['notify_days']} дн. ({s['replace_at']})"
                for s in subs
            )
        await event.edit(
            text=text,
            attachments=[main_menu_kb(role).as_markup()],
        )

    elif menu == "uk_summary":
        if role != "uk_admin" or not user.get("uk_id"):
            await event.edit(
                text="Сводка доступна только диспетчеру УК.",
                attachments=[main_menu_kb("owner").as_markup()],
            )
            return

        summary = await get_uk_summary(user["uk_id"])
        critical = await list_critical_by_uk(user["uk_id"])

        text = (
            f"📊 Сводка по УК\n\n"
            f"🔴 Просрочено: {summary['overdue']}\n"
            f"🟡 Скоро менять: {summary['soon']}\n"
            f"🟢 В норме: {summary['ok']}\n"
        )
        if critical:
            text += "\nКритичные:\n"
            for d in critical[:10]:
                emoji = STATUS_EMOJI.get(d["status"], "⚪")
                text += (
                    f"{emoji} {d.get('building_name', '')}: "
                    f"{d['type']} «{d['model']}» — {d['replace_at']}\n"
                )

        await event.edit(
            text=text,
            attachments=[main_menu_kb("uk_admin").as_markup()],
        )


async def _cat(event, user_id, category, page):
    user = await get_or_create_user(user_id)
    if not user.get("building_id"):
        return
    devices, total = await list_devices(
        user["building_id"], category=category, page=page
    )
    label = CATEGORY_LABELS.get(category, category)
    await event.edit(
        text=f"{label}, стр. {page}:" if devices else f"{label}: пусто",
        attachments=[devices_kb(devices, category, page, total).as_markup()],
    )


@dp.message_created(F.message.body.text)
async def on_text(event: MessageCreated):
    user_id = get_user_id(event)
    if user_id is None:
        return

    if event.message is None or event.message.body is None:
        return

    raw = event.message.body.text
    text = (raw or "").strip()

    user = await get_or_create_user(user_id)

    # Ожидаем пароль диспетчера УК
    if user.get("role") == "pending_uk":
        if text == UK_ADMIN_PASSWORD:
            await set_user_role(user_id, "uk_admin", uk_id=user.get("uk_id"))
            await event.message.answer(
                "✅ Доступ диспетчера УК открыт.\n\nЧто хотите сделать?",
                attachments=[main_menu_kb("uk_admin").as_markup()],
            )
        else:
            await event.message.answer(
                "❌ Неверный пароль.\n"
                "Попробуйте ещё раз или нажмите /start и выберите «Собственник»."
            )
        return

    await event.message.answer("Используйте кнопки или команды /start /menu")


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