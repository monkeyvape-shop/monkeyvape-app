import asyncio
import json
import os
from contextlib import asynccontextmanager
from urllib.parse import quote
import uvicorn
from fastapi import FastAPI
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

# Если используешь туннель (ngrok / localtunnel) для заказов с телефона, укажи его тут:
PUBLIC_TUNNEL_URL = ""  # Например: "https://xxxx.ngrok-free.app"

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
                hidden_by_courier INTEGER DEFAULT 0
            )
        """)
        try:
            await db.execute("ALTER TABLE orders ADD COLUMN hidden_by_courier INTEGER DEFAULT 0")
        except Exception:
            pass
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

class OrderSchema(BaseModel):
    id: str
    user_id: int
    user_name: str
    items: list
    total: float
    station: str
    time: str
    status: str = "active"

class StatusUpdateSchema(BaseModel):
    order_id: str
    status: str

class TimeUpdateSchema(BaseModel):
    order_id: str
    time: str

class DeleteOrderSchema(BaseModel):
    order_id: str

@app.post("/api/create_order")
async def create_order(order: OrderSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """INSERT OR REPLACE INTO orders (id, user_id, user_name, station, time, total, items, status, time_changed, hidden_by_courier)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
            (order.id, order.user_id, order.user_name, order.station, order.time, order.total, json.dumps(order.items), order.status)
        )
        await db.commit()

    items_str = "\n".join([f"• {i['title']} x{i['qty']} — {(i['price'] * i['qty']):.2f} р." for i in order.items])
    
    courier_text = (
        f"🚨 **НОВЫЙ ЗАКАЗ #{order.id}**\n\n"
        f"👤 **Покупатель:** {order.user_name} (ID: `{order.user_id}`)\n"
        f"🚇 **Станция:** м. {order.station}\n"
        f"⏰ **Время:** {order.time}\n\n"
        f"📦 **Состав заказа:**\n{items_str}\n\n"
        f"💰 **Итого:** {order.total:.2f} р."
    )

    for cid in set(COURIER_IDS + OWNER_IDS):
        try:
            await bot.send_message(cid, courier_text, parse_mode="Markdown")
        except Exception:
            pass

    user_text = (
        f"✅ **Ваш заказ #{order.id} успешно оформлен!**\n\n"
        f"🚇 **Место встречи:** м. {order.station}\n"
        f"⏰ **Время:** {order.time}\n\n"
        f"📦 **Ваш заказ:**\n{items_str}\n\n"
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
                    "hidden_by_courier": bool(row["hidden_by_courier"])
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
                    "time_changed": bool(row["time_changed"])
                })
            return result

@app.post("/api/update_order_status")
async def update_order_status(data: StatusUpdateSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET status = ? WHERE id = ?", (data.status, data.order_id))
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station, time FROM orders WHERE id = ?", (data.order_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station, time = row[0], row[1], row[2], row[3]
                if data.status == 'cancelled':
                    if user_id:
                        try:
                            await bot.send_message(user_id, f"❌ Ваш заказ #{data.order_id} был отменён.")
                        except Exception:
                            pass
                    for cid in set(COURIER_IDS + OWNER_IDS):
                        try:
                            await bot.send_message(cid, f"❌ Заказ #{data.order_id} ({user_name}, м. {station}) был **отменён**.", parse_mode="Markdown")
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
        # Удалять (скрывать у курьера) можно ТОЛЬКО выполненные заказы (status = 'completed')
        await db.execute(
            "UPDATE orders SET hidden_by_courier = 1 WHERE id = ? AND status = 'completed'",
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

    # Обновляем и нижнюю кнопку клавиатуры, и синюю кнопку меню чата для этого пользователя
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
