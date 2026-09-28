from datetime import date
from database import STATUS_EMOJI, CATEGORY_LABELS

def get_user_id(event) -> int | None:
    # 1. Callback — самый частый случай после кнопок
    if hasattr(event, "callback") and event.callback:
        user = getattr(event.callback, "user", None)
        if user is not None:
            uid = getattr(user, "user_id", None)
            if uid is not None:
                return int(uid)
    # 2. Message.sender
    if hasattr(event, "message") and event.message:
        sender = getattr(event.message, "sender", None)
        if sender is not None:
            uid = getattr(sender, "user_id", None)
            if uid is not None:
                return int(uid)
    # 3. BotStarted / user
    if hasattr(event, "user") and event.user is not None:
        uid = getattr(event.user, "user_id", None)
        if uid is not None:
            return int(uid)
    # 4. Запасной вариант — chat_id в личке часто = user_id
    if getattr(event, "chat_id", None) is not None:
        return int(event.chat_id)
    return None

def get_chat_id(event) -> int | None:
    if getattr(event, "chat_id", None):
        return event.chat_id
    if hasattr(event, "message") and event.message:
        recipient = getattr(event.message, "recipient", None)
        if recipient and getattr(recipient, "chat_id", None):
            return recipient.chat_id
    return get_user_id(event)

def format_device_card(d: dict) -> str:
    emoji = STATUS_EMOJI.get(d["status"], "⚪")
    days = (date.fromisoformat(d["replace_at"]) - date.today()).days
    if days < 0:
        rest = f"ПРОСРОЧЕН на {abs(days)} дн."
    elif days == 0:
        rest = "Замена сегодня!"
    else:
        rest = f"осталось {days} дн."
    status_map = {"ok": "В норме", "soon": "Скоро менять", "overdue": "ПРОСРОЧЕН"}
    lines = [
        f"{emoji} <b>{d['type']}</b> «{d['model']}»",
        "",
        f"Категория:  {CATEGORY_LABELS.get(d['category'], d['category'])}",
        f"Модель:     {d['model']}",
    ]
    if d.get("serial"):
        lines.append(f"Серийный:   {d['serial']}")
    lines += [
        f"Установлен: {d['installed_at']}",
        f"Срок службы: {d['service_life_years']} лет",
        f"Замена до:  {d['replace_at']}",
        f"Статус:     {status_map.get(d['status'], d['status'])} ({rest})",
    ]
    return "\n".join(lines)

def format_device_line(d: dict) -> str:
    emoji = STATUS_EMOJI.get(d["status"], "⚪")
    days = (date.fromisoformat(d["replace_at"]) - date.today()).days
    extra = f" — ПРОСРОЧЕН {abs(days)} дн." if days < 0 else f" — ост. {days} дн." if days <= 90 else f" — {d['replace_at']}"
    return f"{emoji} {d['type']} «{d['model']}»{extra}"