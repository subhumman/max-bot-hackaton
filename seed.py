import asyncio
import random
from datetime import date, timedelta
import aiosqlite
from config import DB_PATH
from database import init_db, _status_from_replace


TYPES = [
    {"type": "Счётчик ХВС", "models": ["Водоприбор-15", "Бетар СВК-15", "Itron S1"], "life": 12, "category": "water"},
    {"type": "Счётчик ГВС", "models": ["Водоприбор-15Г", "Бетар СВГ-15"], "life": 12, "category": "water"},
    {"type": "Счётчик тепла", "models": ["ТС-100", "Danfoss Sono", "Взлёт ТСР"], "life": 12, "category": "heat"},
    {"type": "Циркуляционный насос", "models": ["Grundfos UPS 25-60", "Wilo Yonos PICO 25/6", "DAB Evosta 2"], "life": 10, "category": "pump"},
    {"type": "Бойлер", "models": ["Bosch TR2000T", "Ariston ABS VLS", "Thermex IF 50"], "life": 12, "category": "heat"},
    {"type": "Автомат в щитке", "models": ["ABB S201 C16", "IEK BA47-29 16A", "Schneider Easy9"], "life": 20, "category": "power"},
    {"type": "Газовый котёл", "models": ["Viessmann Vitopend", "Baxi Eco Four", "Buderus Logamax"], "life": 12, "category": "boiler"},
]

ANALOGS = [
    ("Циркуляционный насос", "Wilo Yonos PICO 25/6-130", "напор 6 м, Dn 25"),
    ("Циркуляционный насос", "DAB Evosta 2 60/130", "напор 6 м"),
    ("Счётчик ХВС", "Водоприбор-15 (новая партия)", "Dn 15"),
    ("Бойлер", "Ariston ABS VLS PRO 50", "50 л"),
    ("Автомат в щитке", "ABB S201 C16", "1P 16A"),
    ("Газовый котёл", "Baxi Eco Four 24", "24 кВт"),
]


async def seed():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        for t in ("subscriptions", "devices", "buildings", "uk", "analogs", "users"):
            await db.execute(f"DELETE FROM {t}")
        await db.commit()

        # 4 УК
        await db.executemany("INSERT INTO uk (name) VALUES (?)", [
            ("УК Северная",),
            ("УК Центральная",),
            ("УК Заречная",),
            ("УК Южная",),
        ])

        # дома с городом
        await db.executemany(
            "INSERT INTO buildings (uk_id, name, address, city) VALUES (?, ?, ?, ?)",
            [
                (1, "ЖК Северный, корп. 1", "ул. Ленина, 15", "Москва"),
                (1, "ЖК Северный, корп. 3", "ул. Ленина, 17", "Москва"),
                (2, "ЖК Центральный, корп. А", "пр. Мира, 42", "Москва"),
                (3, "ЖК Заречный, корп. 2", "ул. Речная, 8", "Казань"),
                (4, "ЖК Южный, корп. 1", "ул. Солнечная, 3", "Казань"),
                (2, "ЖК Парковый", "ул. Садовая, 10", "Санкт-Петербург"),
                (4, "ЖК Морской", "наб. Макарова, 5", "Санкт-Петербург"),
            ],
        )

        # Устройства
        devices = []
        today = date.today()
        for bld_id in range(1, 8):  # 7 домов
            n = 35 if bld_id <= 3 else 12
            for i in range(n):
                t = random.choice(TYPES)
                r = random.random()
                if r < 0.12:
                    years_ago = t["life"] + random.randint(0, 2)
                elif r < 0.28:
                    years_ago = t["life"] - random.uniform(0, 0.2)
                else:
                    years_ago = random.uniform(0.5, t["life"] - 0.5)
                installed = today - timedelta(days=int(years_ago * 365))
                replace_at = installed + timedelta(days=t["life"] * 365)
                status = _status_from_replace(replace_at)
                devices.append((
                    bld_id,
                    t["category"],
                    t["type"],
                    random.choice(t["models"]),
                    f"{t['category'].upper()}-{bld_id}-{i+1:03d}",
                    installed.isoformat(),
                    t["life"],
                    replace_at.isoformat(),
                    status,
                ))

        await db.executemany(
            """INSERT INTO devices
               (building_id, category, type, model, serial, installed_at,
                service_life_years, replace_at, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            devices,
        )

        await db.executemany(
            "INSERT INTO analogs (device_type, model, specs) VALUES (?,?,?)",
            ANALOGS,
        )
        await db.commit()

    print("✅ Сиды загружены (с городами)")


if __name__ == "__main__":
    asyncio.run(seed())