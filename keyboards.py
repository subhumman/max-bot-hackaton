from maxapi.types import CallbackButton
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from database import CATEGORY_LABELS, STATUS_EMOJI

def uks_kb(uks: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for u in uks:
        kb.row(CallbackButton(text=u["name"], payload=f"uk:{u['id']}"))
    return kb

def buildings_kb(buildings: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for b in buildings:
        kb.row(CallbackButton(text=b["name"], payload=f"bld:{b['id']}"))
    kb.row(CallbackButton(text="◀ Назад к УК", payload="menu:uks"))
    return kb

def main_menu_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(CallbackButton(text="📋 Список устройств", payload="menu:cats"))
    kb.row(CallbackButton(text="⚠️ Что скоро менять", payload="menu:soon"))
    kb.row(CallbackButton(text="🔔 Мои подписки", payload="menu:subs"))
    kb.row(CallbackButton(text="⚙️ Сменить дом", payload="menu:uks"))
    return kb

def categories_kb(cats: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for c in cats:
        label = CATEGORY_LABELS.get(c["category"], c["category"])
        kb.row(CallbackButton(text=f"{label} ({c['cnt']})", payload=f"cat:{c['category']}:1"))
    kb.row(CallbackButton(text="🏠 Меню", payload="menu:main"))
    return kb

def devices_kb(devices: list[dict], category: str, page: int, total: int, per_page: int = 6) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for d in devices:
        emoji = STATUS_EMOJI.get(d["status"], "⚪")
        kb.row(CallbackButton(
            text=f"{emoji} {d['type'][:18]} «{d['model'][:14]}»",
            payload=f"dev:{d['id']}",
        ))
    pages = max(1, (total + per_page - 1) // per_page)
    nav = []
    if page > 1:
        nav.append(CallbackButton(text="◀", payload=f"cat:{category}:{page-1}"))
    nav.append(CallbackButton(text=f"{page}/{pages}", payload="noop"))
    if page < pages:
        nav.append(CallbackButton(text="▶", payload=f"cat:{category}:{page+1}"))
    if nav:
        kb.row(*nav)
    kb.row(CallbackButton(text="◀ Категории", payload="menu:cats"))
    kb.row(CallbackButton(text="🏠 Меню", payload="menu:main"))
    return kb

def device_card_kb(device_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="🔁 Подобрать аналог", payload=f"analog:{device_id}"),
        CallbackButton(text="🔔 Напомнить", payload=f"sub_menu:{device_id}"),
    )
    kb.row(CallbackButton(text="◀ Назад", payload="menu:cats"))
    return kb

def notify_days_kb(device_id: int) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.row(
        CallbackButton(text="90 дней", payload=f"sub:{device_id}:90"),
        CallbackButton(text="30 дней", payload=f"sub:{device_id}:30"),
        CallbackButton(text="7 дней", payload=f"sub:{device_id}:7"),
    )
    kb.row(CallbackButton(text="Все (90+30+7)", payload=f"sub:{device_id}:all"))
    kb.row(CallbackButton(text="◀ К карточке", payload=f"dev:{device_id}"))
    return kb

def soon_kb(devices: list[dict]) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    for d in devices:
        emoji = STATUS_EMOJI.get(d["status"], "⚪")
        kb.row(CallbackButton(
            text=f"{emoji} {d['type'][:18]} — {d['replace_at']}",
            payload=f"dev:{d['id']}",
        ))
    kb.row(CallbackButton(text="🏠 Меню", payload="menu:main"))
    return kb