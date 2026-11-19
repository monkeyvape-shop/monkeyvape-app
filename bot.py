import asyncio
import json
import os
from datetime import datetime
from contextlib import asynccontextmanager
from urllib.parse import quote
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    WebAppInfo, MenuButtonWebApp
)

def load_token_from_env():
    if os.path.exists(".env"):
        try:
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        if "TOKEN" in key.upper():
                            return val.strip().strip('"').strip("'")
        except Exception:
            pass
    return None

# ----- НАСТРОЙКИ И ТОКЕНЫ -----
FALLBACK_TOKEN = "ВСТАВЬ_СЮДА_НОВЫЙ_ТОКЕН_ЕСЛИ_ЕГО_НЕТ_В_ENV"
TOKEN = load_token_from_env() or FALLBACK_TOKEN
WEBAPP_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"

PUBLIC_TUNNEL_URL = "https://shark-highlight-change-frontier.trycloudflare.com"

# РОЛИ ПОЛЬЗОВАТЕЛЕЙ (Telegram ID)
OWNER_IDS = [7280921605] # Владелец (Админ)
COURIER_IDS = [6658906694, 7280921605, 1335426710] # Курьеры и Владелец

DB_FILE = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                user_id INTEGER,
                user_name TEXT,
                station TEXT,
                time TEXT,
                total REAL,
                items TEXT,
                status TEXT DEFAULT 'active',
                time_changed INTEGER DEFAULT 0,
                hidden_by_courier INTEGER DEFAULT 0,
                promo_code TEXT DEFAULT '',
                discount REAL DEFAULT 0,
                created_at TEXT DEFAULT '',
                cancelled_by TEXT DEFAULT ''
            )
        """)
        for col_sql in [
            "ALTER TABLE orders ADD COLUMN hidden_by_courier INTEGER DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN promo_code TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN created_at TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN cancelled_by TEXT DEFAULT ''"
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount REAL
            )
        """)
        async with db.execute("SELECT COUNT(*) FROM promocodes") as cur:
            row = await cur.fetchone()
            if row and row[0] == 0:
                await db.execute("INSERT INTO promocodes (code, discount) VALUES (?, ?)", ("MONKEY3", 3.0))

        await db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_private_network_header(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response

class OrderSchema(BaseModel):
    id: str
    user_id: int
    user_name: str
    items: list
    total: float
    station: str
    time: str
    status: str = "active"
    promo_code: str = ""
    discount: float = 0.0
    created_at: str = ""
    cancelled_by: str = ""

class StatusUpdateSchema(BaseModel):
    order_id: str
    status: str
    cancelled_by: str = ""

class TimeUpdateSchema(BaseModel):
    order_id: str
    time: str

class DeleteOrderSchema(BaseModel):
    order_id: str

class AdminStationToggleSchema(BaseModel):
    user_id: int
    station: str

class AdminTimeToggleSchema(BaseModel):
    user_id: int
    time: str

class AdminPromoSaveSchema(BaseModel):
    user_id: int
    code: str
    discount: float

class AdminPromoDeleteSchema(BaseModel):
    user_id: int
    code: str

async def get_setting_list(db, key: str) -> list:
    async with db.execute("SELECT value FROM shop_settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                return []
    return []

async def set_setting_list(db, key: str, values: list):
    await db.execute(
        "INSERT OR REPLACE INTO shop_settings (key, value) VALUES (?, ?)",
        (key, json.dumps(values))
    )

@app.get("/api/user_avatar/{user_id}")
async def get_user_avatar(user_id: int):
    if not user_id:
        raise HTTPException(status_code=404, detail="No user id")
    try:
        photos = await bot.get_user_profile_photos(user_id=user_id, limit=1)
        if photos.total_count > 0 and photos.photos:
            file_id = photos.photos[0][-1].file_id
            tg_file = await bot.get_file(file_id)
            file_bytes_io = await bot.download_file(tg_file.file_path)
            return Response(content=file_bytes_io.read(), media_type="image/jpeg")
    except Exception:
        pass
    raise HTTPException(status_code=404, detail="Avatar not found")

@app.get("/api/shop_config")
async def get_shop_config():
    async with aiosqlite.connect(DB_FILE) as db:
        disabled_stations = await get_setting_list(db, "disabled_stations")
        disabled_times = await get_setting_list(db, "disabled_times")
        promos = {}
        async with db.execute("SELECT code, discount FROM promocodes") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                promos[r[0]] = r[1]
        return {
            "disabled_stations": disabled_stations,
            "disabled_times": disabled_times,
            "promocodes": promos
        }

@app.post("/api/admin/toggle_station")
async def admin_toggle_station(data: AdminStationToggleSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner can change stations")
    async with aiosqlite.connect(DB_FILE) as db:
        stations = await get_setting_list(db, "disabled_stations")
        if data.station in stations:
            stations.remove(data.station)
        else:
            stations.append(data.station)
        await set_setting_list(db, "disabled_stations", stations)
        await db.commit()
    return {"success": True, "disabled_stations": stations}

@app.post("/api/admin/toggle_time")
async def admin_toggle_time(data: AdminTimeToggleSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner can change times")
    async with aiosqlite.connect(DB_FILE) as db:
        times = await get_setting_list(db, "disabled_times")
        if data.time in times:
            times.remove(data.time)
        else:
            times.append(data.time)
        await set_setting_list(db, "disabled_times", times)
        await db.commit()
    return {"success": True, "disabled_times": times}

@app.post("/api/admin/save_promo")
async def admin_save_promo(data: AdminPromoSaveSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner can manage promos")
    code = data.code.strip().upper()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO promocodes (code, discount) VALUES (?, ?)",
            (code, float(data.discount))
        )
        await db.commit()
    return {"success": True}

@app.post("/api/admin/delete_promo")
async def admin_delete_promo(data: AdminPromoDeleteSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner can manage promos")
    code = data.code.strip().upper()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        await db.commit()
    return {"success": True}

@app.post("/api/create_order")
async def create_order(order: OrderSchema):
    created_at = order.created_at or datetime.now().strftime("%d.%m.%Y, %H:%M")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """INSERT OR REPLACE INTO orders 
               (id, user_id, user_name, station, time, total, items, status, time_changed, hidden_by_courier, promo_code, discount, created_at, cancelled_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, '')""",
            (
                order.id, order.user_id, order.user_name, order.station, order.time,
                order.total, json.dumps(order.items), order.status, order.promo_code, order.discount, created_at
            )
        )
        await db.commit()

    items_str = "\n".join([f"• {i['title']} x{i['qty']} — {(i['price'] * i['qty']):.2f} р." for i in order.items])
    promo_line = f"\n🎟 **Промокод:** {order.promo_code} (-{order.discount:.2f} р.)" if order.promo_code else ""
    
    courier_text = (
        f"🚨 **НОВЫЙ ЗАКАЗ #{order.id}**\n"
        f"📅 **Оформлен:** {created_at}\n\n"
        f"👤 **Покупатель:** {order.user_name} (ID: `{order.user_id}`)\n"
        f"🚇 **Станция:** м. {order.station}\n"
        f"⏰ **Время встречи:** {order.time}\n\n"
        f"📦 **Состав заказа:**\n{items_str}{promo_line}\n\n"
        f"💰 **Итого:** {order.total:.2f} р."
    )

    for cid in set(COURIER_IDS + OWNER_IDS):
        try:
            await bot.send_message(cid, courier_text, parse_mode="Markdown")
        except Exception:
            pass

    user_text = (
        f"✅ **Ваш заказ #{order.id} успешно оформлен!**\n"
        f"📅 **Дата и время заказа:** {created_at}\n\n"
        f"🚇 **Место встречи:** м. {order.station}\n"
        f"⏰ **Время встречи:** {order.time}\n\n"
        f"📦 **Ваш заказ:**\n{items_str}{promo_line}\n\n"
        f"💰 **К оплате (при встрече):** {order.total:.2f} р.\n\n"
        f"Спасибо, что выбрали Monkey Vape! Ожидайте курьера."
    )
    
    if order.user_id:
        try:
            await bot.send_message(order.user_id, user_text, parse_mode="Markdown")
        except Exception:
            pass

    return {"success": True}

@app.get("/api/orders")
async def get_orders():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE hidden_by_courier = 0 ORDER BY rowid DESC") as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_name"],
                    "station": row["station"],
                    "time": row["time"],
                    "total": row["total"],
                    "items": json.loads(row["items"]),
                    "status": row["status"],
                    "time_changed": bool(row["time_changed"]),
                    "hidden_by_courier": bool(row["hidden_by_courier"]),
                    "promo_code": row["promo_code"] or "",
                    "discount": row["discount"] or 0.0,
                    "created_at": row["created_at"] or "",
                    "cancelled_by": row["cancelled_by"] or ""
                })
            return result

@app.get("/api/user_orders/{user_id}")
async def get_user_orders(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY rowid DESC", (user_id,)) as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "user_name": row["user_name"],
                    "station": row["station"],
                    "time": row["time"],
                    "total": row["total"],
                    "items": json.loads(row["items"]),
                    "status": row["status"],
                    "time_changed": bool(row["time_changed"]),
                    "promo_code": row["promo_code"] or "",
                    "discount": row["discount"] or 0.0,
                    "created_at": row["created_at"] or "",
                    "cancelled_by": row["cancelled_by"] or ""
                })
            return result

@app.post("/api/update_order_status")
async def update_order_status(data: StatusUpdateSchema):
    cancelled_by = data.cancelled_by if data.status == 'cancelled' else ''
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "UPDATE orders SET status = ?, cancelled_by = ? WHERE id = ?",
            (data.status, cancelled_by, data.order_id)
        )
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station, time FROM orders WHERE id = ?", (data.order_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station, time = row[0], row[1], row[2], row[3]
                if data.status == 'cancelled':
                    who_text = "Отменено клиентом" if cancelled_by == 'client' else (
                        "Отменено курьером" if cancelled_by == 'courier' else "Заказ отменён"
                    )
                    if user_id:
                        try:
                            await bot.send_message(user_id, f"❌ Заказ #{data.order_id} ({who_text}).")
                        except Exception:
                            pass
                    for cid in set(COURIER_IDS + OWNER_IDS):
                        try:
                            await bot.send_message(cid, f"❌ Заказ #{data.order_id} ({user_name}, м. {station}) — **{who_text}**.", parse_mode="Markdown")
                        except Exception:
                            pass
                elif data.status == 'completed':
                    if user_id:
                        try:
                            await bot.send_message(user_id, f"✅ Ваш заказ #{data.order_id} выдан! Спасибо за покупку.")
                        except Exception:
                            pass

    return {"success": True}

@app.post("/api/delete_completed_order")
async def delete_completed_order(data: DeleteOrderSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        # Удалять крестиком из панели курьера можно и выданные (completed), и отменённые (cancelled) заказы
        await db.execute(
            "UPDATE orders SET hidden_by_courier = 1 WHERE id = ? AND status IN ('completed', 'cancelled')",
            (data.order_id,)
        )
        await db.commit()
    return {"success": True}

@app.post("/api/update_order_time")
async def update_order_time(data: TimeUpdateSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET time = ?, time_changed = 1 WHERE id = ?", (data.time, data.order_id))
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station FROM orders WHERE id = ?", (data.order_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station = row[0], row[1], row[2]
                for cid in set(COURIER_IDS + OWNER_IDS):
                    try:
                        await bot.send_message(
                            cid,
                            f"⏰ **Покупатель изменил время заказа #{data.order_id}**\n"
                            f"👤 Покупатель: {user_name}\n"
                            f"🚇 Станция: м. {station}\n"
                            f"🕒 Новое время: **{data.time}**",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass

    return {"success": True}

@app.get("/api/check_role/{user_id}")
async def check_role(user_id: int):
    if user_id in OWNER_IDS:
        return {"role": "owner"}
    elif user_id in COURIER_IDS:
        return {"role": "courier"}
    return {"role": "client"}

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "User")
    
    role = "client"
    if uid in OWNER_IDS:
        role = "owner"
    elif uid in COURIER_IDS:
        role = "courier"

    personal_url = f"{WEBAPP_URL}?uid={uid}&uname={quote(uname)}&role={role}"
    if PUBLIC_TUNNEL_URL:
        personal_url += f"&api={quote(PUBLIC_TUNNEL_URL)}"

    try:
        await bot.set_chat_menu_button(
            chat_id=uid,
            menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=personal_url))
        )
    except Exception:
        pass

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Открыть Monkey Vape", web_app=WebAppInfo(url=personal_url))]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "👋 Добро пожаловать в **Monkey Vape**!\n\nНажми кнопку ниже, чтобы открыть каталог и сделать заказ.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

async def main():
    asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
