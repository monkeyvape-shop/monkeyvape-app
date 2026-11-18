import asyncio
import json
from urllib.parse import quote
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    WebAppInfo, MenuButtonDefault, InlineKeyboardMarkup, InlineKeyboardButton
)

# ----- НАСТРОЙКИ И ТОКЕНЫ -----
TOKEN = "8979467253:AAF8ym1bWsfsMpefad3Eo8B6G9XistJUDlk"
WEBAPP_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"

# РОЛИ ПОЛЬЗОВАТЕЛЕЙ (Telegram ID)
OWNER_IDS = [7280921605] # Владелец (Админ)
COURIER_IDS = [6658906694, 7280921605] # Курьеры и Владелец

DB_FILE = "database.db"

# ----- ИНИЦИАЛИЗАЦИЯ -----
bot = Bot(token=TOKEN)
dp = Dispatcher()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                time_changed INTEGER DEFAULT 0
            )
        """)
        await db.commit()

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

@app.on_event("startup")
async def startup_event():
    await init_db()

@app.post("/api/create_order")
async def create_order(order: OrderSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """INSERT OR REPLACE INTO orders (id, user_id, user_name, station, time, total, items, status, time_changed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
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
    
    try:
        await bot.send_message(order.user_id, user_text, parse_mode="Markdown")
    except Exception:
        pass

    return {"success": True}

@app.get("/api/orders")
async def get_orders():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders ORDER BY rowid DESC") as cursor:
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
                    try:
                        await bot.send_message(user_id, f"❌ Ваш заказ #{data.order_id} был отменён (сохранён в истории заказов).")
                    except Exception:
                        pass
                    for cid in set(COURIER_IDS + OWNER_IDS):
                        try:
                            await bot.send_message(cid, f"❌ Заказ #{data.order_id} ({user_name}, м. {station}) был **отменён**.", parse_mode="Markdown")
                        except Exception:
                            pass
                elif data.status == 'completed':
                    try:
                        await bot.send_message(user_id, f"✅ Ваш заказ #{data.order_id} успешно выполнен! Спасибо за покупку.")
                    except Exception:
                        pass
                    for cid in set(COURIER_IDS + OWNER_IDS):
                        try:
                            await bot.send_message(cid, f"✅ Заказ #{data.order_id} ({user_name}, м. {station}) отмечен как **сделан (выдан)**.", parse_mode="Markdown")
                        except Exception:
                            pass

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
                try:
                    await bot.send_message(user_id, f"⏰ Время встречи для заказа #{data.order_id} (м. {station}) изменено на **{data.time}**.", parse_mode="Markdown")
                except Exception:
                    pass
                for cid in set(COURIER_IDS + OWNER_IDS):
                    try:
                        await bot.send_message(cid, f"⏰ **Изменено время заказа #{data.order_id}**\n👤 Покупатель: {user_name}\n🚇 Станция: м. {station}\n🕒 Новое время: **{data.time}**", parse_mode="Markdown")
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
    personal_url = f"{WEBAPP_URL}?uid={uid}&uname={quote(uname)}"

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
    await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
    asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
