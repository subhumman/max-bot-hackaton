from __future__ import annotations
import aiosqlite
from datetime import date, timedelta
from typing import Optional
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS uk (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uk_id INTEGER NOT NULL REFERENCES uk(id),
    name TEXT NOT NULL,
    address TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id INTEGER NOT NULL REFERENCES buildings(id),
    category TEXT NOT NULL,
    type TEXT NOT NULL,
    model TEXT NOT NULL,
    serial TEXT,
    installed_at TEXT NOT NULL,
    service_life_years INTEGER NOT NULL,
    replace_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok'
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    max_user_id INTEGER UNIQUE NOT NULL,
    role TEXT DEFAULT 'owner',
    uk_id INTEGER,
    building_id INTEGER,
    state TEXT,
    data TEXT
);
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    device_id INTEGER NOT NULL REFERENCES devices(id),
    notify_days INTEGER NOT NULL,
    UNIQUE(user_id, device_id, notify_days)
);
CREATE TABLE IF NOT EXISTS analogs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_type TEXT NOT NULL,
    model TEXT NOT NULL,
    specs TEXT,
    UNIQUE(device_type, model)
);
CREATE INDEX IF NOT EXISTS idx_devices_building ON devices(building_id);
CREATE INDEX IF NOT EXISTS idx_devices_status ON devices(status);
"""

def _status_from_replace(replace_at: date) -> str:
    days = (replace_at - date.today()).days
    if days < 0:
        return "overdue"
    if days <= 90:
        return "soon"
    return "ok"

async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

async def get_or_create_user(max_user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM users WHERE max_user_id = ?",
            (max_user_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            return dict(row)
        await db.execute(
            "INSERT INTO users (max_user_id) VALUES (?)",
            (max_user_id,),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM users WHERE max_user_id = ?",
            (max_user_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"User {max_user_id} was inserted but could not be retrieved"
            )
        return dict(row)

async def set_user_building(max_user_id: int, building_id: int, uk_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET building_id = ?, uk_id = ? WHERE max_user_id = ?",
            (building_id, uk_id, max_user_id),
        )
        await db.commit()

async def list_uks() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM uk ORDER BY id")
        return [dict(r) for r in await cur.fetchall()]

async def list_buildings(uk_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM buildings WHERE uk_id = ? ORDER BY id", (uk_id,))
        return [dict(r) for r in await cur.fetchall()]

async def get_building(building_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM buildings WHERE id = ?", (building_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def list_categories(building_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT category, COUNT(*) as cnt FROM devices WHERE building_id = ? GROUP BY category",
            (building_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

async def list_devices(building_id: int, category: str | None = None, status: str | None = None,
                       page: int = 1, per_page: int = 6) -> tuple[list[dict], int]:
    conditions = ["building_id = ?"]
    params: list = [building_id]
    if category:
        conditions.append("category = ?")
        params.append(category)
    if status:
        conditions.append("status = ?")
        params.append(status)
    where = " AND ".join(conditions)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(f"SELECT COUNT(*) as cnt FROM devices WHERE {where}", params)
        row = await cur.fetchone()
        total = row["cnt"] if row else 0
        offset = (page - 1) * per_page
        cur = await db.execute(
            f"""SELECT * FROM devices WHERE {where}
                ORDER BY CASE status WHEN 'overdue' THEN 0 WHEN 'soon' THEN 1 ELSE 2 END, replace_at
                LIMIT ? OFFSET ?""",
            params + [per_page, offset],
        )
        return [dict(r) for r in await cur.fetchall()], total

async def get_device(device_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def get_analogs(device_type: str, limit: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM analogs WHERE device_type = ? LIMIT ?", (device_type, limit)
        )
        return [dict(r) for r in await cur.fetchall()]

async def add_subscription(max_user_id: int, device_id: int, notify_days: int) -> bool:
    user = await get_or_create_user(max_user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO subscriptions (user_id, device_id, notify_days) VALUES (?, ?, ?)",
                (user["id"], device_id, notify_days),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def list_user_subscriptions(max_user_id: int) -> list[dict]:
    user = await get_or_create_user(max_user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT s.*, d.type, d.model, d.replace_at, d.status
               FROM subscriptions s JOIN devices d ON d.id = s.device_id
               WHERE s.user_id = ? ORDER BY s.notify_days""",
            (user["id"],),
        )
        return [dict(r) for r in await cur.fetchall()]

async def devices_for_notification(notify_days: int) -> list[dict]:
    target = (date.today() + timedelta(days=notify_days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if notify_days == 0:
            cur = await db.execute("SELECT * FROM devices WHERE status = 'overdue'")
        else:
            cur = await db.execute("SELECT * FROM devices WHERE replace_at = ?", (target,))
        return [dict(r) for r in await cur.fetchall()]

async def subscriptions_for_device(device_id: int, notify_days: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT s.*, u.max_user_id FROM subscriptions s
               JOIN users u ON u.id = s.user_id
               WHERE s.device_id = ? AND s.notify_days = ?""",
            (device_id, notify_days),
        )
        return [dict(r) for r in await cur.fetchall()]

async def recount_statuses() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, replace_at FROM devices")
        for r in await cur.fetchall():
            status = _status_from_replace(date.fromisoformat(r["replace_at"]))
            await db.execute("UPDATE devices SET status = ? WHERE id = ?", (status, r["id"]))
        await db.commit()

CATEGORY_LABELS = {
    "heat": "🔥 Теплосистема",
    "water": "💧 Водосистема",
    "power": "⚡ Электросистема",
    "pump": "🔧 Насосы",
    "boiler": "🏭 Котельная",
}
STATUS_EMOJI = {"ok": "🟢", "soon": "🟡", "overdue": "🔴"}