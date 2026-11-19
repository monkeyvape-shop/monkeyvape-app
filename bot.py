import asyncio
import json
import os
import random
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import uvicorn
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ==========================================
# НАСТРОЙКИ БОТА И ССЫЛОК
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8939868585:AAHCaci6_2Uw5s5JKeGXqKsjnfBIuD5-wPw")
GITHUB_PAGES_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"  # <-- Вставь свою ссылку GitHub Pages
PUBLIC_TUNNEL_URL = "https://71d4e6cca1af10.app.lhr.life"         # <-- Актуальная ссылка туннеля

# РОЛИ ПОЛЬЗОВАТЕЛЕЙ (Telegram ID)
OWNER_IDS = [7280921605]  # Владелец (Админ)
COURIER_IDS = [6658906694, 7280921605, 1335426710]  # Курьеры и Владелец

DB_FILE = "database.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# БАЗА ДАННЫХ SQLITE
# ==========================================
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            user_name TEXT,
            items TEXT,
            total REAL,
            station TEXT,
            time TEXT,
            status TEXT DEFAULT 'active',
            time_changed INTEGER DEFAULT 0,
            promo_code TEXT DEFAULT '',
            discount REAL DEFAULT 0.0,
            created_at TEXT DEFAULT '',
            cancelled_by TEXT DEFAULT '',
            hidden_by_courier INTEGER DEFAULT 0
        )
    """)

    # Автоматическое добавление недостающих колонок, если база осталась от старой версии
    cur.execute("PRAGMA table_info(orders)")
    existing_cols = {row["name"] for row in cur.fetchall()}
    migrations = {
        "time_changed": "INTEGER DEFAULT 0",
        "promo_code": "TEXT DEFAULT ''",
        "discount": "REAL DEFAULT 0.0",
        "created_at": "TEXT DEFAULT ''",
        "cancelled_by": "TEXT DEFAULT ''",
        "hidden_by_courier": "INTEGER DEFAULT 0",
    }
    for col, col_type in migrations.items():
        if col not in existing_cols:
            cur.execute(f"ALTER TABLE orders ADD COLUMN {col} {col_type}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    defaults = {
        "disabled_stations": json.dumps([]),
        "disabled_times": json.dumps([]),
        "promocodes": json.dumps({"MONKEY3": 3.0}),
    }
    for k, v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    conn.commit()
    conn.close()


def get_setting(key: str, default: Any):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return default
    try:
        return json.loads(row["value"])
    except Exception:
        return default


def set_setting(key: str, value: Any):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def row_to_order_dict(row: sqlite3.Row) -> Dict[str, Any]:
    try:
        items_parsed = json.loads(row["items"]) if row["items"] else []
    except Exception:
        items_parsed = []
    return {
        "id": str(row["id"]),
        "user_id": int(row["user_id"] or 0),
        "user_name": row["user_name"] or "User",
        "items": items_parsed,
        "total": float(row["total"] or 0.0),
        "station": row["station"] or "",
        "time": row["time"] or "",
        "status": row["status"] or "active",
        "time_changed": bool(row["time_changed"]),
        "promo_code": row["promo_code"] or "",
        "discount": float(row["discount"] or 0.0),
        "created_at": row["created_at"] or "",
        "cancelled_by": row["cancelled_by"] or "",
        "hidden_by_courier": bool(row["hidden_by_courier"]),
    }


def get_user_role(user_id: int) -> str:
    if user_id in OWNER_IDS:
        return "owner"
    if user_id in COURIER_IDS:
        return "courier"
    return "customer"


def build_webapp_url(user_id: int, uname: str = "User") -> str:
    role = get_user_role(user_id)
    base = GITHUB_PAGES_URL.rstrip("/")
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}uid={user_id}&uname={quote(uname)}&role={role}"
    if PUBLIC_TUNNEL_URL:
        url += f"&api={quote(PUBLIC_TUNNEL_URL.rstrip('/'))}"
    return url


# ==========================================
# МОДЕЛИ ЗАПРОСОВ API
# ==========================================
class OrderCreate(BaseModel):
    id: Optional[str] = None
    user_id: int = 0
    user_name: str = "User"
    items: List[Dict[str, Any]] = []
    total: float = 0.0
    station: str = ""
    time: str = ""
    status: str = "active"
    time_changed: bool = False
    promo_code: str = ""
    discount: float = 0.0
    created_at: str = ""
    cancelled_by: str = ""


class OrderStatusUpdate(BaseModel):
    order_id: str
    status: str
    cancelled_by: str = ""


class OrderTimeUpdate(BaseModel):
    order_id: str
    time: str


class OrderDeleteCourier(BaseModel):
    order_id: str


class AdminPromoSave(BaseModel):
    user_id: int
    code: str
    discount: float


class AdminPromoDelete(BaseModel):
    user_id: int
    code: str


class AdminStationToggle(BaseModel):
    user_id: int
    station: str


class AdminTimeToggle(BaseModel):
    user_id: int
    time: str


# ==========================================
# ЭНДПОИНТЫ FASTAPI
# ==========================================
@app.get("/api/shop_config")
async def api_shop_config():
    return {
        "disabled_stations": get_setting("disabled_stations", []),
        "disabled_times": get_setting("disabled_times", []),
        "promocodes": get_setting("promocodes", {"MONKEY3": 3.0}),
    }


@app.get("/api/check_role/{user_id}")
async def api_check_role(user_id: int):
    return {"role": get_user_role(user_id)}


@app.get("/api/user_avatar/{user_id}")
async def api_user_avatar(user_id: int):
    if not user_id or user_id <= 0:
        return Response(status_code=404)
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if not photos.photos:
            return Response(status_code=404)
        file_id = photos.photos[0][-1].file_id
        tg_file = await bot.get_file(file_id)
        file_bytes = await bot.download_file(tg_file.file_path)
        return Response(content=file_bytes.read(), media_type="image/jpeg")
    except Exception:
        return Response(status_code=404)


@app.post("/api/create_order")
async def api_create_order(order: OrderCreate):
    # Сохраняем ТОТ ЖЕ номер заказа, который сформировал телефон
    order_id = str(order.id).strip() if order.id else str(random.randint(10000, 99999))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO orders
        (id, user_id, user_name, items, total, station, time, status, time_changed, promo_code, discount, created_at, cancelled_by, hidden_by_courier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """,
        (
            order_id,
            int(order.user_id),
            order.user_name,
            json.dumps(order.items, ensure_ascii=False),
            float(order.total),
            order.station,
            order.time,
            order.status or "active",
            1 if order.time_changed else 0,
            order.promo_code or "",
            float(order.discount or 0.0),
            order.created_at or "",
            order.cancelled_by or "",
        ),
    )
    conn.commit()
    conn.close()

    items_lines = "\n".join(
        [
            f"• {i.get('title', 'Товар')} × {i.get('qty', 1)} — {float(i.get('price', 0)) * int(i.get('qty', 1)):.2f} р."
            for i in order.items
        ]
    )
    promo_line = (
        f"🎟 <b>Промокод:</b> {order.promo_code} (-{float(order.discount):.2f} р.)\n"
        if order.promo_code
        else ""
    )

    # 1. Отправка благодарности и чека покупателю в личные сообщения бота
    if order.user_id and int(order.user_id) > 0:
        customer_msg = (
            f"✅ <b>Спасибо за заказ #{order_id}!</b>\n\n"
            f"📦 <b>Состав заказа:</b>\n{items_lines}\n\n"
            f"{promo_line}"
            f"💰 <b>Итого к оплате:</b> {float(order.total):.2f} р.\n"
            f"🚇 <b>Станция метро:</b> м. {order.station}\n"
            f"⏰ <b>Время встречи:</b> {order.time}\n\n"
            f"Отслеживать статус или перенести время встречи можно во вкладке <b>«Заказы»</b> в приложении."
        )
        try:
            await bot.send_message(chat_id=int(order.user_id), text=customer_msg, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки сообщения покупателю {order.user_id}: {e}")

    # 2. Уведомление всем курьерам (включая владельца, если он в COURIER_IDS)
    courier_msg = (
        f"🛵 <b>Новый заказ #{order_id}!</b>\n\n"
        f"👤 <b>Покупатель:</b> {order.user_name}\n"
        f"🆔 <b>ID покупателя:</b> <code>{order.user_id}</code>\n"
        f"🚇 <b>Станция:</b> м. {order.station}\n"
        f"⏰ <b>Время встречи:</b> {order.time}\n"
        f"💰 <b>Итого:</b> {float(order.total):.2f} р.\n\n"
        f"📦 <b>Состав:</b>\n{items_lines}\n\n"
        f"Зайдите в мини-приложение во вкладку <b>«Курьер»</b> для управления заказом."
    )
    for cid in COURIER_IDS:
        try:
            url = build_webapp_url(cid, "Courier")
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🛵 Открыть панель курьера", web_app=WebAppInfo(url=url))]
                ]
            )
            await bot.send_message(chat_id=cid, text=courier_msg, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"Ошибка отправки уведомления курьеру {cid}: {e}")

    return {"status": "ok", "order_id": order_id}


@app.get("/api/orders")
async def api_get_all_orders():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY rowid DESC")
    rows = cur.fetchall()
    conn.close()
    return [row_to_order_dict(r) for r in rows]


@app.get("/api/user_orders/{user_id}")
async def api_get_user_orders(user_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY rowid DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [row_to_order_dict(r) for r in rows]


@app.post("/api/update_order_status")
async def api_update_order_status(data: OrderStatusUpdate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (data.order_id,))
    row = cur.fetchone()

    cur.execute(
        "UPDATE orders SET status = ?, cancelled_by = ? WHERE id = ?",
        (data.status, data.cancelled_by or "", data.order_id),
    )
    conn.commit()
    conn.close()

    if row:
        uid = int(row["user_id"] or 0)
        if data.cancelled_by == "courier" and uid > 0:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=f"❌ <b>Заказ #{data.order_id} был отменён курьером.</b>\nЕсли у вас есть вопросы, напишите менеджеру @warat_24.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        elif data.status == "completed" and uid > 0:
            try:
                await bot.send_message(
                    chat_id=uid,
                    text=f"✅ <b>Заказ #{data.order_id} успешно выдан!</b> Спасибо за покупку в Monkey Vape.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        elif data.cancelled_by == "client":
            for cid in COURIER_IDS:
                try:
                    await bot.send_message(
                        chat_id=cid,
                        text=f"⚠️ Покупатель <b>{row['user_name']}</b> (ID: <code>{uid}</code>) отменил заказ <b>#{data.order_id}</b>.",
                        parse_mode="HTML",
                    )
                except Exception:
                    pass

    return {"status": "ok"}


@app.post("/api/update_order_time")
async def api_update_order_time(data: OrderTimeUpdate):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders WHERE id = ?", (data.order_id,))
    row = cur.fetchone()

    cur.execute(
        "UPDATE orders SET time = ?, time_changed = 1 WHERE id = ?",
        (data.time, data.order_id),
    )
    conn.commit()
    conn.close()

    if row:
        for cid in COURIER_IDS:
            try:
                await bot.send_message(
                    chat_id=cid,
                    text=f"⏰ Покупатель <b>{row['user_name']}</b> (ID: <code>{row['user_id']}</code>) перенёс время заказа <b>#{data.order_id}</b> на <b>{data.time}</b>.",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    return {"status": "ok"}


@app.post("/api/delete_completed_order")
async def api_delete_completed_order(data: OrderDeleteCourier):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE orders SET hidden_by_courier = 1 WHERE id = ?", (data.order_id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


@app.post("/api/admin/save_promo")
async def api_admin_save_promo(data: AdminPromoSave):
    if data.user_id not in OWNER_IDS:
        return Response(status_code=403)
    promos = get_setting("promocodes", {})
    promos[data.code.strip().upper()] = float(data.discount)
    set_setting("promocodes", promos)
    return {"status": "ok", "promocodes": promos}


@app.post("/api/admin/delete_promo")
async def api_admin_delete_promo(data: AdminPromoDelete):
    if data.user_id not in OWNER_IDS:
        return Response(status_code=403)
    promos = get_setting("promocodes", {})
    promos.pop(data.code.strip().upper(), None)
    set_setting("promocodes", promos)
    return {"status": "ok", "promocodes": promos}


@app.post("/api/admin/toggle_station")
async def api_admin_toggle_station(data: AdminStationToggle):
    if data.user_id not in OWNER_IDS:
        return Response(status_code=403)
    stations = get_setting("disabled_stations", [])
    if data.station in stations:
        stations.remove(data.station)
    else:
        stations.append(data.station)
    set_setting("disabled_stations", stations)
    return {"status": "ok", "disabled_stations": stations}


@app.post("/api/admin/toggle_time")
async def api_admin_toggle_time(data: AdminTimeToggle):
    if data.user_id not in OWNER_IDS:
        return Response(status_code=403)
    times = get_setting("disabled_times", [])
    if data.time in times:
        times.remove(data.time)
    else:
        times.append(data.time)
    set_setting("disabled_times", times)
    return {"status": "ok", "disabled_times": times}


# ==========================================
# КОМАНДЫ TELEGRAM БОТА
# ==========================================
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "User")
    personal_url = build_webapp_url(uid, uname)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛍️ Открыть Monkey Vape", web_app=WebAppInfo(url=personal_url))]
        ]
    )

    await message.answer(
        "👋 Добро пожаловать в **MONKEY VAPE**!\n\nНажми кнопку ниже, чтобы открыть каталог и сделать заказ.",
        parse_mode="Markdown",
        reply_markup=kb,
    )


async def main():
    init_db()
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await asyncio.gather(
        server.serve(),
        dp.start_polling(bot),
    )


if __name__ == "__main__":
    asyncio.run(main())
