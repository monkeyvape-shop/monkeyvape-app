import asyncio
import html
import json
import os
from datetime import datetime, timedelta
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
    InlineKeyboardMarkup, InlineKeyboardButton,
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

FALLBACK_TOKEN = "ВСТАВЬ_СЮДА_СВОЙ_ТОКЕН_ЕСЛИ_ЕГО_НЕТ_В_ENV"
TOKEN = load_token_from_env() or FALLBACK_TOKEN
WEBAPP_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"
PUBLIC_TUNNEL_URL = "https://relax-indoor-claims-iso.trycloudflare.com"

OWNER_IDS = [7280921605]
DEFAULT_COURIER_IDS = [6658906694, 7280921605, 1335426710]
DB_FILE = "database.db"

INITIAL_PRODUCTS = [
    (1, "ANIMAL LOVE Killer 50mg", "liquid", 17.00, "жидкость", "🧪", 1, "", 0),
    (2, "OGGO Rush 20mg", "liquid", 13.00, "жидкость", "🧪", 1, "", 0),
    (3, "OGGO Cherry 20mg", "liquid", 13.00, "жидкость", "🧪", 1, "", 0),
    (4, "BJORN ZLOY 60mg", "liquid", 13.00, "хит", "🧪", 1, "", 0),
    (5, "XROS 3 Mini Pod Kit", "pod", 55.00, "вейп", "⚡", 1, "", 0),
    (6, "Vaporesso XROS Pro", "pod", 85.00, "вейп", "⚡", 1, "", 0),
    (7, "Lost Mary BM5000", "disposable", 25.00, "одноразка", "💨", 1, "", 0),
    (8, "Сменный картридж XROS", "accessory", 9.00, "расходник", "📦", 1, "", 0),
]

DEFAULT_TIME_SLOTS = ["12:00", "14:30", "16:30", "18:10", "21:00"]

DEFAULT_METRO_STATIONS = {
    "green": [
        {"name": "Юбилейная площадь", "line": "Зеленая ветка"},
        {"name": "Площадь Франтишка Богушевича", "line": "Зеленая ветка"},
        {"name": "Вокзальная", "line": "Зеленая ветка"},
        {"name": "Ковальская Слобода", "line": "Зеленая ветка"},
        {"name": "Аэродромная", "line": "Зеленая ветка"},
        {"name": "Неморшанский Сад", "line": "Зеленая ветка"},
        {"name": "Слуцкий Гостинец", "line": "Зеленая ветка"}
    ],
    "blue": [
        {"name": "Уручье", "line": "Синяя ветка"},
        {"name": "Борисовский тракт", "line": "Синяя ветка"},
        {"name": "Восток", "line": "Синяя ветка"},
        {"name": "Московская", "line": "Синяя ветка"},
        {"name": "Парк Челюскинцев", "line": "Синяя ветка"},
        {"name": "Академия наук", "line": "Синяя ветка"},
        {"name": "Площадь Якуба Коласа", "line": "Синяя ветка"},
        {"name": "Площадь Победы", "line": "Синяя ветка"},
        {"name": "Октябрьская", "line": "Синяя ветка"},
        {"name": "Площадь Ленина", "line": "Синяя ветка"},
        {"name": "Институт культуры", "line": "Синяя ветка"},
        {"name": "Грушевка", "line": "Синяя ветка"},
        {"name": "Михалово", "line": "Синяя ветка"},
        {"name": "Петровщина", "line": "Синяя ветка"},
        {"name": "Малиновка", "line": "Синяя ветка"}
    ],
    "red": [
        {"name": "Каменная Горка", "line": "Красная ветка"},
        {"name": "Кунцевщина", "line": "Красная ветка"},
        {"name": "Спортивная", "line": "Красная ветка"},
        {"name": "Пушкинская", "line": "Красная ветка"},
        {"name": "Молодежная", "line": "Красная ветка"},
        {"name": "Фрунзенская", "line": "Красная ветка"},
        {"name": "Немига", "line": "Красная ветка"},
        {"name": "Купаловская", "line": "Красная ветка"},
        {"name": "Первомайская", "line": "Красная ветка"},
        {"name": "Пролетарская", "line": "Красная ветка"},
        {"name": "Тракторный завод", "line": "Красная ветка"},
        {"name": "Партизанская", "line": "Красная ветка"},
        {"name": "Автозаводская", "line": "Красная ветка"},
        {"name": "Могилевская", "line": "Красная ветка"}
    ]
}

LINE_NAMES = {"green": "Зеленая ветка", "blue": "Синяя ветка", "red": "Красная ветка"}

async def get_setting_raw(db, key: str, default: str = "") -> str:
    async with db.execute("SELECT value FROM shop_settings WHERE key = ?", (key,)) as cursor:
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return row[0]
    return default

async def set_setting_raw(db, key: str, value: str):
    await db.execute("INSERT OR REPLACE INTO shop_settings (key, value) VALUES (?, ?)", (key, value))

async def get_setting_list(db, key: str, default_list=None) -> list:
    raw = await get_setting_raw(db, key, "")
    if not raw:
        return list(default_list) if default_list is not None else []
    try:
        return json.loads(raw)
    except Exception:
        return list(default_list) if default_list is not None else []

async def set_setting_list(db, key: str, values: list):
    await set_setting_raw(db, key, json.dumps(values, ensure_ascii=False))

async def get_metro_map(db) -> dict:
    raw = await get_setting_raw(db, "metro_stations", "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and "green" in data:
                return data
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_METRO_STATIONS))

async def get_all_courier_ids(db) -> list[int]:
    extra = await get_setting_list(db, "extra_couriers")
    combined = set(DEFAULT_COURIER_IDS + OWNER_IDS)
    for x in extra:
        try:
            combined.add(int(x))
        except Exception:
            pass
    return list(combined)

def build_personal_url(uid: int, uname: str = "User", is_courier: bool = False) -> str:
    role = "client"
    if uid in OWNER_IDS:
        role = "owner"
    elif uid in DEFAULT_COURIER_IDS or is_courier:
        role = "courier"
    url = f"{WEBAPP_URL}?uid={uid}&uname={quote(uname)}&role={role}"
    if PUBLIC_TUNNEL_URL:
        url += f"&api={quote(PUBLIC_TUNNEL_URL.strip())}"
    return url

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                user_name TEXT DEFAULT '',
                joined_at TEXT DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                text TEXT,
                sent INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                category TEXT,
                price REAL,
                tag TEXT DEFAULT '',
                icon TEXT DEFAULT '🧪',
                available INTEGER DEFAULT 1,
                image_url TEXT DEFAULT '',
                has_discount INTEGER DEFAULT 0
            )
        """)
        for col_sql in [
            "ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN has_discount INTEGER DEFAULT 0"
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        async with db.execute("SELECT COUNT(*) FROM products") as cur:
            row = await cur.fetchone()
            if row and row[0] == 0:
                await db.executemany(
                    "INSERT INTO products (id, title, category, price, tag, icon, available, image_url, has_discount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    INITIAL_PRODUCTS
                )

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
            INSERT OR IGNORE INTO users (user_id, user_name, joined_at)
            SELECT DISTINCT user_id, user_name, '' FROM orders WHERE user_id > 0
        """)
        await db.execute("CREATE TABLE IF NOT EXISTS shop_settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                discount REAL,
                discount_type TEXT DEFAULT 'rub',
                max_uses INTEGER DEFAULT 0,
                used_count INTEGER DEFAULT 0
            )
        """)
        for p_col in [
            "ALTER TABLE promocodes ADD COLUMN discount_type TEXT DEFAULT 'rub'",
            "ALTER TABLE promocodes ADD COLUMN max_uses INTEGER DEFAULT 0",
            "ALTER TABLE promocodes ADD COLUMN used_count INTEGER DEFAULT 0"
        ]:
            try:
                await db.execute(p_col)
            except Exception:
                pass

        async with db.execute("SELECT COUNT(*) FROM promocodes") as cur:
            row = await cur.fetchone()
            if row and row[0] == 0:
                await db.execute(
                    "INSERT INTO promocodes (code, discount, discount_type, max_uses, used_count) VALUES (?, ?, 'rub', 0, 0)",
                    ("MONKEY3", 3.0)
                )
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

class AdminMetroManageSchema(BaseModel):
    user_id: int
    line: str
    station: str
    action: str

class AdminTimeManageSchema(BaseModel):
    user_id: int
    time: str
    action: str

class AdminAppearanceSchema(BaseModel):
    user_id: int
    season_effect: str = "none"
    hit_color: str = "#ffcc00"

class AdminPromoSaveSchema(BaseModel):
    user_id: int
    code: str
    discount: float
    discount_type: str = "rub"
    max_uses: int = 0

class AdminPromoDeleteSchema(BaseModel):
    user_id: int
    code: str

class AdminBroadcastSchema(BaseModel):
    user_id: int
    text: str

class AdminShopStatusSchema(BaseModel):
    user_id: int
    is_open: bool
    closed_message: str = ""

class AdminProductSaveSchema(BaseModel):
    user_id: int
    id: int = 0
    title: str
    category: str
    price: float
    tag: str = ""
    icon: str = "🧪"
    available: bool = True
    image_url: str = ""
    has_discount: bool = False

class AdminProductToggleSchema(BaseModel):
    user_id: int
    product_id: int
    field: str

class AdminProductDeleteSchema(BaseModel):
    user_id: int
    product_id: int

class AdminRoleManageSchema(BaseModel):
    user_id: int
    target_id: int
    action: str

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

@app.get("/api/tg_photo/{file_id}")
async def get_tg_photo(file_id: str):
    try:
        tg_file = await bot.get_file(file_id)
        file_bytes_io = await bot.download_file(tg_file.file_path)
        return Response(content=file_bytes_io.read(), media_type="image/jpeg")
    except Exception:
        raise HTTPException(status_code=404, detail="Photo not found")

@app.get("/api/shop_config")
async def get_shop_config():
    async with aiosqlite.connect(DB_FILE) as db:
        disabled_stations = await get_setting_list(db, "disabled_stations")
        disabled_times = await get_setting_list(db, "disabled_times")
        time_slots = await get_setting_list(db, "time_slots", DEFAULT_TIME_SLOTS)
        metro_stations = await get_metro_map(db)
        shop_open_raw = await get_setting_raw(db, "shop_open", "1")
        closed_message = await get_setting_raw(db, "closed_message", "Магазин временно закрыт. Попробуйте оформить заказ позже.")
        season_effect = await get_setting_raw(db, "season_effect", "none")
        hit_color = await get_setting_raw(db, "hit_color", "#ffcc00")
        banned_users = [int(x) for x in await get_setting_list(db, "banned_users")]
        courier_ids = await get_all_courier_ids(db)

        promos = {}
        async with db.execute("SELECT code, discount, discount_type, max_uses, used_count FROM promocodes") as cursor:
            rows = await cursor.fetchall()
            for r in rows:
                promos[r[0]] = {
                    "discount": float(r[1]),
                    "type": r[2] or "rub",
                    "max_uses": int(r[3] or 0),
                    "used_count": int(r[4] or 0)
                }

        products_list = []
        async with db.execute("SELECT id, title, category, price, tag, icon, available, image_url, has_discount FROM products ORDER BY id ASC") as cursor:
            p_rows = await cursor.fetchall()
            for pr in p_rows:
                products_list.append({
                    "id": pr[0],
                    "title": pr[1],
                    "category": pr[2],
                    "price": float(pr[3]),
                    "tag": pr[4] or "",
                    "icon": pr[5] or "🧪",
                    "available": bool(pr[6]),
                    "image_url": pr[7] or "",
                    "has_discount": bool(pr[8])
                })

        return {
            "shop_open": shop_open_raw == "1",
            "closed_message": closed_message,
            "season_effect": season_effect,
            "hit_color": hit_color,
            "time_slots": time_slots,
            "metro_stations": metro_stations,
            "disabled_stations": disabled_stations,
            "disabled_times": disabled_times,
            "promocodes": promos,
            "products": products_list,
            "banned_users": banned_users,
            "courier_ids": courier_ids
        }

@app.post("/api/admin/shop_status")
async def admin_shop_status(data: AdminShopStatusSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    async with aiosqlite.connect(DB_FILE) as db:
        await set_setting_raw(db, "shop_open", "1" if data.is_open else "0")
        if data.closed_message.strip():
            await set_setting_raw(db, "closed_message", data.closed_message.strip())
        await db.commit()
    return {"success": True}

@app.post("/api/admin/appearance")
async def admin_appearance(data: AdminAppearanceSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    season = data.season_effect if data.season_effect in ("none", "winter", "autumn", "spring", "summer") else "none"
    color = data.hit_color.strip() or "#ffcc00"
    async with aiosqlite.connect(DB_FILE) as db:
        await set_setting_raw(db, "season_effect", season)
        await set_setting_raw(db, "hit_color", color)
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_metro")
async def admin_manage_metro(data: AdminMetroManageSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    if data.line not in ("green", "blue", "red"):
        raise HTTPException(status_code=400, detail="Invalid line")
    st_name = data.station.strip()
    if not st_name:
        raise HTTPException(status_code=400, detail="Empty station")

    async with aiosqlite.connect(DB_FILE) as db:
        metro_map = await get_metro_map(db)
        if data.action == "add":
            exists = any(s["name"].lower() == st_name.lower() for s in metro_map[data.line])
            if not exists:
                metro_map[data.line].append({"name": st_name, "line": LINE_NAMES[data.line]})
        elif data.action == "delete":
            metro_map[data.line] = [s for s in metro_map[data.line] if s["name"] != st_name]
        await set_setting_raw(db, "metro_stations", json.dumps(metro_map, ensure_ascii=False))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_time")
async def admin_manage_time(data: AdminTimeManageSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    t_str = data.time.strip()
    if not t_str:
        raise HTTPException(status_code=400, detail="Empty time")

    async with aiosqlite.connect(DB_FILE) as db:
        slots = await get_setting_list(db, "time_slots", DEFAULT_TIME_SLOTS)
        if data.action == "add":
            if t_str not in slots:
                slots.append(t_str)
                slots.sort()
        elif data.action == "delete":
            slots = [s for s in slots if s != t_str]
        await set_setting_list(db, "time_slots", slots)
        await db.commit()
    return {"success": True}

@app.post("/api/admin/toggle_station")
async def admin_toggle_station(data: AdminStationToggleSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
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
        raise HTTPException(status_code=403, detail="Only owner")
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
        raise HTTPException(status_code=403, detail="Only owner")
    code = data.code.strip().upper()
    dtype = data.discount_type if data.discount_type in ("rub", "percent") else "rub"
    max_uses = max(0, int(data.max_uses or 0))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """INSERT INTO promocodes (code, discount, discount_type, max_uses, used_count)
               VALUES (?, ?, ?, ?, 0)
               ON CONFLICT(code) DO UPDATE SET
               discount = excluded.discount,
               discount_type = excluded.discount_type,
               max_uses = excluded.max_uses""",
            (code, float(data.discount), dtype, max_uses)
        )
        await db.commit()
    return {"success": True}

@app.post("/api/admin/delete_promo")
async def admin_delete_promo(data: AdminPromoDeleteSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    code = data.code.strip().upper()
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/save_product")
async def admin_save_product(data: AdminProductSaveSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    async with aiosqlite.connect(DB_FILE) as db:
        if data.id and data.id > 0:
            await db.execute(
                """UPDATE products SET title = ?, category = ?, price = ?, tag = ?, icon = ?,
                   available = ?, image_url = ?, has_discount = ? WHERE id = ?""",
                (
                    data.title.strip(), data.category, float(data.price), data.tag.strip(),
                    data.icon.strip() or "🧪", 1 if data.available else 0,
                    data.image_url.strip(), 1 if data.has_discount else 0, data.id
                )
            )
        else:
            await db.execute(
                """INSERT INTO products (title, category, price, tag, icon, available, image_url, has_discount)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.title.strip(), data.category, float(data.price), data.tag.strip(),
                    data.icon.strip() or "🧪", 1 if data.available else 0,
                    data.image_url.strip(), 1 if data.has_discount else 0
                )
            )
        await db.commit()
    return {"success": True}

@app.post("/api/admin/toggle_product")
async def admin_toggle_product(data: AdminProductToggleSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    async with aiosqlite.connect(DB_FILE) as db:
        if data.field == "available":
            await db.execute("UPDATE products SET available = CASE WHEN available = 1 THEN 0 ELSE 1 END WHERE id = ?", (data.product_id,))
        elif data.field == "hit":
            await db.execute("UPDATE products SET tag = CASE WHEN tag = 'хит' THEN '' ELSE 'хит' END WHERE id = ?", (data.product_id,))
        elif data.field == "discount":
            await db.execute("UPDATE products SET has_discount = CASE WHEN has_discount = 1 THEN 0 ELSE 1 END WHERE id = ?", (data.product_id,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/delete_product")
async def admin_delete_product(data: AdminProductDeleteSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("DELETE FROM products WHERE id = ?", (data.product_id,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_role")
async def admin_manage_role(data: AdminRoleManageSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    tid = int(data.target_id)
    async with aiosqlite.connect(DB_FILE) as db:
        if data.action == "add_courier":
            couriers = [int(x) for x in await get_setting_list(db, "extra_couriers")]
            if tid not in couriers and tid not in DEFAULT_COURIER_IDS:
                couriers.append(tid)
                await set_setting_list(db, "extra_couriers", couriers)
        elif data.action == "remove_courier":
            couriers = [int(x) for x in await get_setting_list(db, "extra_couriers") if int(x) != tid]
            await set_setting_list(db, "extra_couriers", couriers)
        elif data.action == "ban_user":
            if tid in OWNER_IDS:
                raise HTTPException(status_code=400, detail="Cannot ban owner")
            banned = [int(x) for x in await get_setting_list(db, "banned_users")]
            if tid not in banned:
                banned.append(tid)
                await set_setting_list(db, "banned_users", banned)
        elif data.action == "unban_user":
            banned = [int(x) for x in await get_setting_list(db, "banned_users") if int(x) != tid]
            await set_setting_list(db, "banned_users", banned)
        await db.commit()
    return {"success": True}

@app.get("/api/admin/stats/{user_id}")
async def admin_stats(user_id: int):
    if user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")

    now = datetime.now()
    today_prefix = now.strftime("%d.%m.%Y")
    week_ago = now - timedelta(days=7)

    today_rev = week_rev = total_rev = 0.0
    today_cnt = week_cnt = total_cnt = cancelled_cnt = active_cnt = 0
    item_counts, station_counts = {}, {}

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT total, status, created_at, items, station FROM orders") as cursor:
            rows = await cursor.fetchall()

        for total, status, created_at, items_json, station in rows:
            val = float(total or 0)
            c_str = created_at or ""
            if status == "completed":
                total_rev += val
                total_cnt += 1
                if c_str.startswith(today_prefix):
                    today_rev += val
                    today_cnt += 1
                try:
                    dt = datetime.strptime(c_str[:10], "%d.%m.%Y")
                    if dt >= week_ago.replace(hour=0, minute=0, second=0, microsecond=0):
                        week_rev += val
                        week_cnt += 1
                except Exception:
                    pass
                if station:
                    station_counts[station] = station_counts.get(station, 0) + 1
                try:
                    for it in json.loads(items_json or "[]"):
                        t = it.get("title", "Товар")
                        q = int(it.get("qty", 1))
                        item_counts[t] = item_counts.get(t, 0) + q
                except Exception:
                    pass
            elif status == "cancelled":
                cancelled_cnt += 1
            elif status == "active":
                active_cnt += 1

    top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    top_stations = sorted(station_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "today_rev": round(today_rev, 2), "today_cnt": today_cnt,
        "week_rev": round(week_rev, 2), "week_cnt": week_cnt,
        "total_rev": round(total_rev, 2), "total_cnt": total_cnt,
        "cancelled_cnt": cancelled_cnt, "active_cnt": active_cnt,
        "top_items": [{"title": k, "qty": v} for k, v in top_items],
        "top_stations": [{"station": k, "count": v} for k, v in top_stations]
    }

@app.get("/api/admin/broadcast_history/{user_id}")
async def admin_broadcast_history(user_id: int):
    if user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE user_id > 0") as cur:
            u_row = await cur.fetchone()
            subscribers_count = u_row[0] if u_row else 0
        history = []
        async with db.execute("SELECT id, created_at, text, sent, failed, total FROM broadcasts ORDER BY id DESC LIMIT 15") as cursor:
            for r in await cursor.fetchall():
                history.append({"id": r[0], "created_at": r[1], "text": r[2], "sent": r[3], "failed": r[4], "total": r[5]})
    return {"subscribers_count": subscribers_count, "history": history}

@app.post("/api/admin/broadcast")
async def admin_broadcast(data: AdminBroadcastSchema):
    if data.user_id not in OWNER_IDS:
        raise HTTPException(status_code=403, detail="Only owner")
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()

    user_ids = [r[0] for r in rows]
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    now_str = datetime.now().strftime("%d.%m.%Y, %H:%M")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO broadcasts (created_at, text, sent, failed, total) VALUES (?, ?, ?, ?, ?)",
            (now_str, text[:300], sent, failed, len(user_ids))
        )
        await db.commit()
    return {"success": True, "sent": sent, "failed": failed, "total": len(user_ids)}

@app.post("/api/create_order")
async def create_order(order: OrderSchema):
    order_id = str(order.id).strip()
    created_at = order.created_at or datetime.now().strftime("%d.%m.%Y, %H:%M")

    async with aiosqlite.connect(DB_FILE) as db:
        shop_open_raw = await get_setting_raw(db, "shop_open", "1")
        if shop_open_raw != "1" and order.user_id not in OWNER_IDS:
            closed_msg = await get_setting_raw(db, "closed_message", "Магазин временно закрыт.")
            raise HTTPException(status_code=403, detail=closed_msg)

        banned = [int(x) for x in await get_setting_list(db, "banned_users")]
        if int(order.user_id) in banned:
            raise HTTPException(status_code=403, detail="Ваш аккаунт заблокирован в магазине.")

        if order.user_id > 0:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, user_name, joined_at) VALUES (?, ?, ?)",
                (order.user_id, order.user_name, created_at)
            )

        if order.promo_code:
            code_up = order.promo_code.strip().upper()
            async with db.execute("SELECT max_uses, used_count FROM promocodes WHERE code = ?", (code_up,)) as cur:
                p_row = await cur.fetchone()
                if p_row:
                    m_uses, u_cnt = int(p_row[0] or 0), int(p_row[1] or 0)
                    if m_uses > 0 and u_cnt >= m_uses:
                        raise HTTPException(status_code=400, detail="Лимит использований промокода исчерпан.")
                    await db.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code_up,))

        await db.execute(
            """INSERT OR REPLACE INTO orders 
               (id, user_id, user_name, station, time, total, items, status, time_changed, hidden_by_courier, promo_code, discount, created_at, cancelled_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, '')""",
            (
                order_id, order.user_id, order.user_name, order.station, order.time,
                order.total, json.dumps(order.items), order.status, order.promo_code, order.discount, created_at
            )
        )
        all_couriers = await get_all_courier_ids(db)
        await db.commit()

    safe_user = html.escape(order.user_name or "User")
    safe_station = html.escape(order.station or "")
    safe_time = html.escape(order.time or "")
    items_str = "\n".join([f"• {html.escape(str(i['title']))} × {i['qty']} — {(i['price'] * i['qty']):.2f} р." for i in order.items])
    promo_line = f"\n🎟 <b>Промокод:</b> {html.escape(order.promo_code)} (-{order.discount:.2f} р.)" if order.promo_code else ""

    courier_text = (
        f"🛵 <b>Новый заказ #{html.escape(order_id)}!</b>\n\n"
        f"👤 <b>Покупатель:</b> {safe_user}\n"
        f"🆔 <b>ID покупателя:</b> <code>{order.user_id}</code>\n"
        f"🚇 <b>Станция:</b> м. {safe_station}\n"
        f"⏰ <b>Время встречи:</b> {safe_time}\n"
        f"💰 <b>Итого:</b> {order.total:.2f} р.\n\n"
        f"📦 <b>Состав:</b>\n{items_str}{promo_line}\n\n"
        f"Зайдите в мини-приложение во вкладку <b>«Курьер»</b> для управления заказом."
    )

    for cid in all_couriers:
        try:
            courier_url = build_personal_url(cid, "Courier", is_courier=True)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛵 Открыть панель курьера", web_app=WebAppInfo(url=courier_url))]
            ])
            await bot.send_message(cid, courier_text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"[ERR] Курьер {cid}: {e}")

    user_text = (
        f"✅ <b>Спасибо за заказ #{html.escape(order_id)}!</b>\n"
        f"📅 <b>Оформлен:</b> {html.escape(created_at)}\n\n"
        f"🚇 <b>Станция метро:</b> м. {safe_station}\n"
        f"⏰ <b>Время встречи:</b> {safe_time}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_str}{promo_line}\n\n"
        f"💰 <b>Итого к оплате:</b> {order.total:.2f} р.\n\n"
        f"Ожидайте курьера. Статус заказа можно отслеживать во вкладке <b>«Заказы»</b>."
    )

    if order.user_id:
        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML")
        except Exception as e:
            print(f"[ERR] Покупатель {order.user_id}: {e}")

    return {"success": True, "order_id": order_id}

@app.get("/api/orders")
async def get_orders():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE hidden_by_courier = 0 ORDER BY rowid DESC") as cursor:
            return [{
                "id": str(row["id"]), "user_id": row["user_id"], "user_name": row["user_name"],
                "station": row["station"], "time": row["time"], "total": row["total"],
                "items": json.loads(row["items"]), "status": row["status"],
                "time_changed": bool(row["time_changed"]), "hidden_by_courier": bool(row["hidden_by_courier"]),
                "promo_code": row["promo_code"] or "", "discount": row["discount"] or 0.0,
                "created_at": row["created_at"] or "", "cancelled_by": row["cancelled_by"] or ""
            } for row in await cursor.fetchall()]

@app.get("/api/user_orders/{user_id}")
async def get_user_orders(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY rowid DESC", (user_id,)) as cursor:
            return [{
                "id": str(row["id"]), "user_id": row["user_id"], "user_name": row["user_name"],
                "station": row["station"], "time": row["time"], "total": row["total"],
                "items": json.loads(row["items"]), "status": row["status"],
                "time_changed": bool(row["time_changed"]), "promo_code": row["promo_code"] or "",
                "discount": row["discount"] or 0.0, "created_at": row["created_at"] or "",
                "cancelled_by": row["cancelled_by"] or ""
            } for row in await cursor.fetchall()]

@app.post("/api/update_order_status")
async def update_order_status(data: StatusUpdateSchema):
    cancelled_by = data.cancelled_by if data.status == 'cancelled' else ''
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET status = ?, cancelled_by = ? WHERE id = ?", (data.status, cancelled_by, str(data.order_id)))
        all_couriers = await get_all_courier_ids(db)
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station, time FROM orders WHERE id = ?", (str(data.order_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station, time = row[0], row[1], row[2], row[3]
                safe_user = html.escape(user_name or "User")
                safe_station = html.escape(station or "")
                if data.status == 'cancelled':
                    who_text = "Отменено клиентом" if cancelled_by == 'client' else ("Отменено курьером" if cancelled_by == 'courier' else "Заказ отменён")
                    if user_id:
                        try:
                            await bot.send_message(user_id, f"❌ Заказ #{html.escape(str(data.order_id))} ({who_text}).")
                        except Exception:
                            pass
                    for cid in all_couriers:
                        try:
                            await bot.send_message(cid, f"❌ Заказ #{html.escape(str(data.order_id))} ({safe_user}, м. {safe_station}) — <b>{who_text}</b>.", parse_mode="HTML")
                        except Exception:
                            pass
                elif data.status == 'completed':
                    if user_id:
                        try:
                            await bot.send_message(user_id, f"✅ Ваш заказ #{html.escape(str(data.order_id))} выдан! Спасибо за покупку.")
                        except Exception:
                            pass
    return {"success": True}

@app.post("/api/delete_completed_order")
async def delete_completed_order(data: DeleteOrderSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET hidden_by_courier = 1 WHERE id = ? AND status IN ('completed', 'cancelled')", (str(data.order_id),))
        await db.commit()
    return {"success": True}

@app.post("/api/update_order_time")
async def update_order_time(data: TimeUpdateSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE orders SET time = ?, time_changed = 1 WHERE id = ?", (data.time, str(data.order_id)))
        all_couriers = await get_all_courier_ids(db)
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station FROM orders WHERE id = ?", (str(data.order_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station = row[0], row[1], row[2]
                safe_user = html.escape(user_name or "User")
                safe_station = html.escape(station or "")
                for cid in all_couriers:
                    try:
                        await bot.send_message(
                            cid,
                            f"⏰ <b>Покупатель изменил время заказа #{html.escape(str(data.order_id))}</b>\n"
                            f"👤 Покупатель: {safe_user} (ID: <code>{user_id}</code>)\n"
                            f"🚇 Станция: м. {safe_station}\n"
                            f"🕒 Новое время: <b>{html.escape(data.time)}</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
    return {"success": True}

@app.get("/api/check_role/{user_id}")
async def check_role(user_id: int):
    if user_id in OWNER_IDS:
        return {"role": "owner"}
    async with aiosqlite.connect(DB_FILE) as db:
        couriers = await get_all_courier_ids(db)
    if user_id in couriers:
        return {"role": "courier"}
    return {"role": "client"}

@dp.message(F.photo)
async def handle_owner_photo_upload(message: Message):
    if message.from_user.id not in OWNER_IDS:
        return
    file_id = message.photo[-1].file_id
    base = PUBLIC_TUNNEL_URL.strip().rstrip("/")
    photo_url = f"{base}/api/tg_photo/{file_id}"
    await message.answer(
        f"🖼 <b>Ссылка на фото для товара готова!</b>\n\n"
        f"Нажми на ссылку ниже, чтобы скопировать её, и вставь в настройках товара в мини-приложении:\n"
        f"<code>{html.escape(photo_url)}</code>",
        parse_mode="HTML"
    )

@dp.message(F.text.startswith("/post"))
async def cmd_post_broadcast(message: Message):
    if message.from_user.id not in OWNER_IDS:
        return
    inline_text = message.text[5:].strip()
    if not message.reply_to_message and not inline_text:
        await message.answer(
            "📢 <b>Как сделать рассылку:</b>\n\n"
            "1. Отправь боту готовый пост (текст, фото, видео или кружочек).\n"
            "2. Нажми <b>«Ответить» (Reply)</b> на это сообщение и напиши <code>/post</code>.\n\n"
            "<i>Либо напиши сразу:</i> <code>/post Текст объявления</code>",
            parse_mode="HTML"
        )
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()

    user_ids = [r[0] for r in rows]
    status_msg = await message.answer(f"⏳ Начинаю рассылку по базе ({len(user_ids)} чел.)...")

    sent = failed = 0
    for uid in user_ids:
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy_to(chat_id=uid)
            else:
                await bot.send_message(uid, inline_text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    post_preview = inline_text or (message.reply_to_message.text or message.reply_to_message.caption or "[Медиа-пост]")
    now_str = datetime.now().strftime("%d.%m.%Y, %H:%M")
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO broadcasts (created_at, text, sent, failed, total) VALUES (?, ?, ?, ?, ?)",
            (now_str, post_preview[:300], sent, failed, len(user_ids))
        )
        await db.commit()

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📨 Доставлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота / недоступны: <b>{failed}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    uid = message.from_user.id
    uname = f"@{message.from_user.username}" if message.from_user.username else (message.from_user.first_name or "User")
    now_str = datetime.now().strftime("%d.%m.%Y, %H:%M")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, user_name, joined_at) VALUES (?, ?, ?)",
            (uid, uname, now_str)
        )
        couriers = await get_all_courier_ids(db)
        await db.commit()

    personal_url = build_personal_url(uid, uname, is_courier=(uid in couriers))
    try:
        await bot.set_chat_menu_button(
            chat_id=uid,
            menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=personal_url))
        )
    except Exception:
        pass

    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛒 Открыть Monkey Vape", web_app=WebAppInfo(url=personal_url))]],
        resize_keyboard=True
    )
    await message.answer(
        "👋 Добро пожаловать в <b>Monkey Vape</b>!\n\nНажми кнопку ниже, чтобы открыть каталог и сделать заказ.",
        reply_markup=kb,
        parse_mode="HTML"
    )

async def main():
    asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
