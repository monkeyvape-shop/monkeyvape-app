import asyncio
import html
import json
import os
import time
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

FALLBACK_TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН_ЕСЛИ_ЕГО_НЕТ_В_ENV"
TOKEN = load_token_from_env() or FALLBACK_TOKEN
WEBAPP_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"
TUNNEL_FILE = "tunnel_url.txt"

def load_tunnel_url() -> str:
    if os.path.exists(TUNNEL_FILE):
        try:
            with open(TUNNEL_FILE, "r", encoding="utf-8") as f:
                saved = f.read().strip()
                if saved.startswith("http"):
                    return saved
        except Exception:
            pass
    return "https://nemeses-july-concrete.ngrok-free.dev"

PUBLIC_TUNNEL_URL = load_tunnel_url()

PRIMARY_OWNER_IDS = [7280921605]
DEFAULT_COURIER_IDS = [6658906694, 7280921605, 1335426710]
DB_FILE = "database.db"

ALLOWED_CURRENCIES = ("р.", "₽", "₸", "$", "₴")
ALLOWED_DELIVERY_MODES = ("metro", "districts", "pickup", "free_address")

DEFAULT_DELIVERY_LOCATIONS = [
    "Центральный район",
    "Советский район",
    "Первомайский район"
]

DEFAULT_WELCOME_TEXT = (
    "Здравствуйте, <b>{user}</b>! Добро пожаловать в <b>{brand}</b> 👋\n\n"
    "Актуальное наличие и быстрое оформление заказа.\n"
    "Нажмите кнопку ниже, чтобы открыть каталог:"
)

DEFAULT_UI_THEME = {
    "bg_color": "#0b0f0c",
    "topbar_bg": "#0b0f0c",
    "bottomnav_bg": "#0b0f0c",
    "card_bg": "#131b14",
    "banner_bg": "#132b17",
    "border_color": "#223525",
    "accent_color": "#00ff66",
    "icon_color": "#00ff66",
    "logo_color_1": "#ffffff",
    "logo_color_2": "#00ff66",
    "text_main": "#ffffff",
    "text_secondary": "#9ca3af"
}

DEFAULT_CATEGORIES = [
    {"id": "liquid", "name": "Жидкости"},
    {"id": "pod", "name": "Поды и Вейпы"},
    {"id": "disposable", "name": "Одноразки"},
    {"id": "accessory", "name": "Расходники"}
]

DEFAULT_OPTIONS_BY_CAT = {
    "liquid": ["Кола", "Клубника", "Skittles", "Малина", "Манго"],
    "disposable": ["Кола", "Клубника", "Skittles", "Малина", "Манго"],
    "pod": ["Черный мат", "Градиент", "Серебряный", "Зеленый неон"],
    "accessory": ["0.6 Ом", "0.8 Ом", "1.0 Ом", "1.2 Ом"]
}

def make_default_options_json(category: str) -> str:
    opts = DEFAULT_OPTIONS_BY_CAT.get(category, ["Стандарт"])
    return json.dumps([{"name": o, "available": True} for o in opts], ensure_ascii=False)

INITIAL_PRODUCTS = [
    (1, "ANIMAL LOVE Killer 50mg", "liquid", 17.00, 0.0, "жидкость", "🧪", 1, "", 0, 0, make_default_options_json("liquid")),
    (2, "OGGO Rush 20mg", "liquid", 13.00, 0.0, "жидкость", "🧪", 1, "", 0, 0, make_default_options_json("liquid")),
    (3, "OGGO Cherry 20mg", "liquid", 13.00, 0.0, "жидкость", "🧪", 1, "", 0, 0, make_default_options_json("liquid")),
    (4, "BJORN ZLOY 60mg", "liquid", 13.00, 0.0, "хит", "🧪", 1, "", 0, 0, make_default_options_json("liquid")),
    (5, "XROS 3 Mini Pod Kit", "pod", 55.00, 0.0, "вейп", "⚡", 1, "", 0, 0, make_default_options_json("pod")),
    (6, "Vaporesso XROS Pro", "pod", 85.00, 0.0, "вейп", "⚡", 1, "", 0, 0, make_default_options_json("pod")),
    (7, "Lost Mary BM5000", "disposable", 25.00, 0.0, "одноразка", "💨", 1, "", 0, 0, make_default_options_json("disposable")),
    (8, "Сменный картридж XROS", "accessory", 9.00, 0.0, "расходник", "📦", 1, "", 0, 0, make_default_options_json("accessory")),
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

def normalize_tg_link(raw: str) -> str:
    val = (raw or "").strip()
    if not val:
        return ""
    if val.startswith("@"):
        return f"https://t.me/{val[1:]}"
    if val.startswith("t.me/"):
        return f"https://{val}"
    if val.startswith("http://") or val.startswith("https://"):
        return val
    return f"https://t.me/{val}"

def get_location_label(delivery_mode: str) -> str:
    mapping = {
        "metro": "Станция метро",
        "districts": "Район города",
        "pickup": "Пункт выдачи",
        "free_address": "Адрес доставки"
    }
    return mapping.get(delivery_mode, "Локация")

def format_location_value(station: str, delivery_mode: str) -> str:
    st = (station or "").strip()
    if not st:
        return ""
    if delivery_mode == "metro":
        return st if st.startswith("м.") else f"м. {st}"
    return st

def render_welcome_message(template_text: str, user_first_name: str, brand_name: str) -> str:
    tpl = (template_text or "").strip() or DEFAULT_WELCOME_TEXT
    safe_user = html.escape(user_first_name or "друг")
    safe_brand = html.escape(brand_name or "Monkey Vape")
    return tpl.replace("{user}", safe_user).replace("{brand}", safe_brand)

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

async def get_ui_theme_dict(db) -> dict:
    raw = await get_setting_raw(db, "ui_theme", "")
    theme = dict(DEFAULT_UI_THEME)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for k in DEFAULT_UI_THEME:
                    if k in parsed and str(parsed[k]).strip():
                        theme[k] = str(parsed[k]).strip()
        except Exception:
            pass
    return theme

async def get_shop_brand_name(db) -> str:
    p1 = (await get_setting_raw(db, "logo_part1", "MONKEY")).strip()
    p2 = (await get_setting_raw(db, "logo_part2", "VAPE")).strip()
    full = f"{p1} {p2}".strip()
    return full if full else "Monkey Vape"

async def get_categories_list(db) -> list:
    raw = await get_setting_raw(db, "categories", "")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 0:
                return [{"id": str(c.get("id", "")), "name": str(c.get("name", ""))} for c in data if c.get("id") and c.get("name")]
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False))

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

async def get_all_owner_ids(db) -> list[int]:
    extra = await get_setting_list(db, "extra_owners")
    combined = set(PRIMARY_OWNER_IDS)
    for x in extra:
        try:
            combined.add(int(x))
        except Exception:
            pass
    return list(combined)

async def get_all_courier_ids(db) -> list[int]:
    extra = await get_setting_list(db, "extra_couriers")
    removed_defaults = set()
    for x in await get_setting_list(db, "removed_default_couriers"):
        try:
            removed_defaults.add(int(x))
        except Exception:
            pass
    owners = await get_all_owner_ids(db)
    base_defaults = [cid for cid in DEFAULT_COURIER_IDS if cid not in removed_defaults]
    combined = set(base_defaults + owners)
    for x in extra:
        try:
            combined.add(int(x))
        except Exception:
            pass
    return list(combined)

async def check_is_owner(db, uid: int) -> bool:
    return int(uid) in await get_all_owner_ids(db)

async def check_is_courier(db, uid: int) -> bool:
    return int(uid) in await get_all_courier_ids(db)

def build_personal_url(uid: int, uname: str = "User", is_owner: bool = False, is_courier: bool = False) -> str:
    role = "client"
    if uid in PRIMARY_OWNER_IDS or is_owner:
        role = "owner"
    elif is_courier:
        role = "courier"
    url = f"{WEBAPP_URL}?uid={uid}&uname={quote(uname)}&role={role}"
    if PUBLIC_TUNNEL_URL:
        url += f"&api={quote(PUBLIC_TUNNEL_URL.strip())}"
    return url

def parse_product_options(raw_json: str, category: str) -> list:
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list) and len(parsed) > 0:
                return [{"name": str(x.get("name", "")), "available": bool(x.get("available", True))} for x in parsed if x.get("name")]
        except Exception:
            pass
    return [{"name": o, "available": True} for o in DEFAULT_OPTIONS_BY_CAT.get(category, ["Стандарт"])]

async def notify_stock_subscribers(db, product_id: int, product_title: str, available_options: list[str] = None, all_restocked: bool = False):
    brand_name = await get_shop_brand_name(db)
    async with db.execute("SELECT id, user_id, option_name FROM stock_notifications WHERE product_id = ?", (product_id,)) as cur:
        rows = await cur.fetchall()

    to_delete = []
    for sub_id, uid, opt_name in rows:
        should_notify = False
        if all_restocked and not opt_name:
            should_notify = True
        elif opt_name and available_options and opt_name in available_options:
            should_notify = True
        elif all_restocked and opt_name and (not available_options or opt_name in available_options):
            should_notify = True

        if should_notify:
            to_delete.append(sub_id)
            opt_part = f" • {html.escape(opt_name)}" if opt_name else ""
            try:
                await bot.send_message(
                    uid,
                    f"🔔 <b>Пополнение на витрине {html.escape(brand_name)}!</b>\n\n"
                    f"✨ <b>{html.escape(product_title)}{opt_part}</b> снова в наличии и доступен для заказа.",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    for sub_id in to_delete:
        await db.execute("DELETE FROM stock_notifications WHERE id = ?", (sub_id,))

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
            CREATE TABLE IF NOT EXISTS stock_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product_id INTEGER,
                option_name TEXT DEFAULT ''
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                category TEXT,
                price REAL,
                old_price REAL DEFAULT 0,
                tag TEXT DEFAULT '',
                icon TEXT DEFAULT '🧪',
                available INTEGER DEFAULT 1,
                image_url TEXT DEFAULT '',
                has_discount INTEGER DEFAULT 0,
                low_stock INTEGER DEFAULT 0,
                options_json TEXT DEFAULT ''
            )
        """)
        for col_sql in [
            "ALTER TABLE products ADD COLUMN old_price REAL DEFAULT 0",
            "ALTER TABLE products ADD COLUMN image_url TEXT DEFAULT ''",
            "ALTER TABLE products ADD COLUMN has_discount INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN low_stock INTEGER DEFAULT 0",
            "ALTER TABLE products ADD COLUMN options_json TEXT DEFAULT ''"
        ]:
            try:
                await db.execute(col_sql)
            except Exception:
                pass

        async with db.execute("SELECT COUNT(*) FROM products") as cur:
            row = await cur.fetchone()
            if row and row[0] == 0:
                await db.executemany(
                    """INSERT INTO products (id, title, category, price, old_price, tag, icon, available, image_url, has_discount, low_stock, options_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                delivery_fee REAL DEFAULT 0,
                created_at TEXT DEFAULT '',
                cancelled_by TEXT DEFAULT '',
                claimed_by_id INTEGER DEFAULT 0,
                claimed_by_name TEXT DEFAULT ''
            )
        """)
        for col_sql in [
            "ALTER TABLE orders ADD COLUMN hidden_by_courier INTEGER DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN promo_code TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN delivery_fee REAL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN created_at TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN cancelled_by TEXT DEFAULT ''",
            "ALTER TABLE orders ADD COLUMN claimed_by_id INTEGER DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN claimed_by_name TEXT DEFAULT ''"
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

        default_shop_settings = [
            ("currency", "р."),
            ("delivery_mode", "metro"),
            ("delivery_locations", json.dumps(DEFAULT_DELIVERY_LOCATIONS, ensure_ascii=False)),
            ("splash_emoji", "🐵"),
            ("splash_image", ""),
            ("welcome_text", DEFAULT_WELCOME_TEXT),
            ("min_order_amount", "0"),
            ("delivery_fee", "0"),
            ("free_delivery_threshold", "0"),
        ]
        for s_key, s_val in default_shop_settings:
            await db.execute("INSERT OR IGNORE INTO shop_settings (key, value) VALUES (?, ?)", (s_key, s_val))

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
    delivery_fee: float = 0.0
    created_at: str = ""
    cancelled_by: str = ""

class StatusUpdateSchema(BaseModel):
    order_id: str
    status: str
    cancelled_by: str = ""
    courier_id: int = 0
    courier_name: str = ""

class CourierClaimSchema(BaseModel):
    order_id: str
    courier_id: int
    courier_name: str

class CourierArrivedSchema(BaseModel):
    order_id: str
    courier_id: int = 0
    courier_name: str = ""

class CourierBannerSchema(BaseModel):
    user_id: int
    enabled: bool
    title: str
    desc: str
    badge: str

class AdminBrandingSchema(BaseModel):
    user_id: int
    logo_part1: str
    logo_part2: str = ""
    splash_emoji: str = ""
    splash_image: str | None = None
    welcome_text: str = ""

class AdminLocalizationSchema(BaseModel):
    user_id: int
    currency: str = "р."
    delivery_mode: str = "metro"
    delivery_locations: list = []
    splash_emoji: str = "🐵"
    splash_image: str | None = None
    welcome_text: str = ""
    min_order_amount: float | None = None
    delivery_fee: float | None = None
    free_delivery_threshold: float | None = None

class AdminDeliveryPricingSchema(BaseModel):
    user_id: int
    min_order_amount: float = 0.0
    delivery_fee: float = 0.0
    free_delivery_threshold: float = 0.0

class AdminUiThemeSchema(BaseModel):
    user_id: int
    theme: dict = {}
    reset: bool = False

class AdminChannelsSchema(BaseModel):
    user_id: int
    news_channel_url: str = ""
    reviews_channel_url: str = ""
    support_username: str = "@warat_24"

class AdminCategoryManageSchema(BaseModel):
    user_id: int
    action: str
    id: str = ""
    name: str = ""

class TimeUpdateSchema(BaseModel):
    order_id: str
    time: str

class DeleteOrderSchema(BaseModel):
    order_id: str

class StockNotifySchema(BaseModel):
    user_id: int
    product_id: int
    option_name: str = ""

class ShopOpenNotifySchema(BaseModel):
    user_id: int

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
    old_price: float = 0.0
    tag: str = ""
    icon: str = "🧪"
    available: bool = True
    image_url: str = ""
    has_discount: bool = False
    low_stock: bool = False
    options: list = []

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
        categories = await get_categories_list(db)
        ui_theme = await get_ui_theme_dict(db)
        shop_open_raw = await get_setting_raw(db, "shop_open", "1")
        closed_message = await get_setting_raw(db, "closed_message", "Витрина сейчас на паузе, скоро вернёмся в онлайн.")
        season_effect = await get_setting_raw(db, "season_effect", "none")
        hit_color = await get_setting_raw(db, "hit_color", "#ffcc00")
        logo_part1 = await get_setting_raw(db, "logo_part1", "MONKEY")
        logo_part2 = await get_setting_raw(db, "logo_part2", "VAPE")
        currency = await get_setting_raw(db, "currency", "р.")
        if currency not in ALLOWED_CURRENCIES:
            currency = "р."
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        if delivery_mode not in ALLOWED_DELIVERY_MODES:
            delivery_mode = "metro"
        delivery_locations = await get_setting_list(db, "delivery_locations", DEFAULT_DELIVERY_LOCATIONS)
        splash_emoji = (await get_setting_raw(db, "splash_emoji", "🐵")).strip() or "🐵"
        splash_image = (await get_setting_raw(db, "splash_image", "")).strip()
        welcome_text = await get_setting_raw(db, "welcome_text", DEFAULT_WELCOME_TEXT)
        min_order_amount = float(await get_setting_raw(db, "min_order_amount", "0") or 0)
        delivery_fee = float(await get_setting_raw(db, "delivery_fee", "0") or 0)
        free_delivery_threshold = float(await get_setting_raw(db, "free_delivery_threshold", "0") or 0)

        news_channel_url = await get_setting_raw(db, "news_channel_url", "")
        reviews_channel_url = await get_setting_raw(db, "reviews_channel_url", "")
        support_username = await get_setting_raw(db, "support_username", "@warat_24")
        banner_enabled = await get_setting_raw(db, "banner_enabled", "1") == "1"
        banner_title = await get_setting_raw(db, "banner_title", "СКИДКА НЕДЕЛИ -20%")
        banner_desc = await get_setting_raw(db, "banner_desc", "Популярные товары и новинки уже в каталоге")
        banner_badge = await get_setting_raw(db, "banner_badge", "-20%")
        banned_users = [int(x) for x in await get_setting_list(db, "banned_users")]
        owner_ids = await get_all_owner_ids(db)
        courier_ids = await get_all_courier_ids(db)

        promos = {}
        async with db.execute("SELECT code, discount, discount_type, max_uses, used_count FROM promocodes") as cursor:
            for r in await cursor.fetchall():
                promos[r[0]] = {
                    "discount": float(r[1]),
                    "type": r[2] or "rub",
                    "max_uses": int(r[3] or 0),
                    "used_count": int(r[4] or 0)
                }

        products_list = []
        async with db.execute("""
            SELECT id, title, category, price, old_price, tag, icon, available, image_url, has_discount, low_stock, options_json
            FROM products ORDER BY id ASC
        """) as cursor:
            for pr in await cursor.fetchall():
                cat = pr[2]
                products_list.append({
                    "id": pr[0],
                    "title": pr[1],
                    "category": cat,
                    "price": float(pr[3]),
                    "old_price": float(pr[4] or 0.0),
                    "tag": pr[5] or "",
                    "icon": pr[6] or "🧪",
                    "available": bool(pr[7]),
                    "image_url": pr[8] or "",
                    "has_discount": bool(pr[9]),
                    "low_stock": bool(pr[10]),
                    "options": parse_product_options(pr[11] or "", cat)
                })

        return {
            "shop_open": shop_open_raw == "1",
            "closed_message": closed_message,
            "season_effect": season_effect,
            "hit_color": hit_color,
            "ui_theme": ui_theme,
            "logo_part1": logo_part1,
            "logo_part2": logo_part2,
            "currency": currency,
            "delivery_mode": delivery_mode,
            "delivery_locations": delivery_locations,
            "splash_emoji": splash_emoji,
            "splash_image": splash_image,
            "welcome_text": welcome_text,
            "min_order_amount": min_order_amount,
            "delivery_fee": delivery_fee,
            "free_delivery_threshold": free_delivery_threshold,
            "news_channel_url": news_channel_url,
            "reviews_channel_url": reviews_channel_url,
            "support_username": support_username,
            "categories": categories,
            "banner": {
                "enabled": banner_enabled,
                "title": banner_title,
                "desc": banner_desc,
                "badge": banner_badge
            },
            "time_slots": time_slots,
            "metro_stations": metro_stations,
            "disabled_stations": disabled_stations,
            "disabled_times": disabled_times,
            "promocodes": promos,
            "products": products_list,
            "banned_users": banned_users,
            "owner_ids": owner_ids,
            "courier_ids": courier_ids
        }

@app.post("/api/admin/ui_theme")
async def update_admin_ui_theme(data: AdminUiThemeSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        if data.reset:
            new_theme = dict(DEFAULT_UI_THEME)
        else:
            new_theme = await get_ui_theme_dict(db)
            for k, v in (data.theme or {}).items():
                if k in DEFAULT_UI_THEME and str(v).strip():
                    new_theme[k] = str(v).strip()
        await set_setting_raw(db, "ui_theme", json.dumps(new_theme, ensure_ascii=False))
        await db.commit()
    return {"success": True, "ui_theme": new_theme}

@app.post("/api/admin/branding")
async def update_admin_branding(data: AdminBrandingSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        p1 = data.logo_part1.strip()
        p2 = data.logo_part2.strip()
        if not p1 and not p2:
            raise HTTPException(status_code=400, detail="Logo cannot be empty")
        await set_setting_raw(db, "logo_part1", p1)
        await set_setting_raw(db, "logo_part2", p2)
        if data.splash_emoji.strip():
            await set_setting_raw(db, "splash_emoji", data.splash_emoji.strip())
        if data.splash_image is not None:
            await set_setting_raw(db, "splash_image", data.splash_image.strip())
        if data.welcome_text is not None:
            w_clean = data.welcome_text.strip()
            await set_setting_raw(db, "welcome_text", w_clean if w_clean else DEFAULT_WELCOME_TEXT)
        await db.commit()
    return {"success": True}

@app.post("/api/admin/localization")
async def update_admin_localization(data: AdminLocalizationSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")

        cur = data.currency.strip() if data.currency.strip() in ALLOWED_CURRENCIES else "р."
        dmode = data.delivery_mode.strip() if data.delivery_mode.strip() in ALLOWED_DELIVERY_MODES else "metro"

        clean_locs = []
        seen = set()
        for item in (data.delivery_locations or []):
            name = item.get("name", "") if isinstance(item, dict) else str(item or "")
            name = name.strip()
            if name and name.lower() not in seen:
                seen.add(name.lower())
                clean_locs.append(name)

        emoji = (data.splash_emoji or "").strip() or "🐵"
        w_text = (data.welcome_text or "").strip() or DEFAULT_WELCOME_TEXT

        await set_setting_raw(db, "currency", cur)
        await set_setting_raw(db, "delivery_mode", dmode)
        await set_setting_list(db, "delivery_locations", clean_locs)
        await set_setting_raw(db, "splash_emoji", emoji)
        if data.splash_image is not None:
            await set_setting_raw(db, "splash_image", data.splash_image.strip())
        await set_setting_raw(db, "welcome_text", w_text)

        if data.min_order_amount is not None:
            await set_setting_raw(db, "min_order_amount", str(max(0.0, round(float(data.min_order_amount), 2))))
        if data.delivery_fee is not None:
            await set_setting_raw(db, "delivery_fee", str(max(0.0, round(float(data.delivery_fee), 2))))
        if data.free_delivery_threshold is not None:
            await set_setting_raw(db, "free_delivery_threshold", str(max(0.0, round(float(data.free_delivery_threshold), 2))))

        await db.commit()

    return {
        "success": True,
        "currency": cur,
        "delivery_mode": dmode,
        "delivery_locations": clean_locs,
        "splash_emoji": emoji,
        "welcome_text": w_text
    }

@app.post("/api/admin/delivery_pricing")
async def update_admin_delivery_pricing(data: AdminDeliveryPricingSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        min_amt = max(0.0, round(float(data.min_order_amount or 0.0), 2))
        d_fee = max(0.0, round(float(data.delivery_fee or 0.0), 2))
        free_thr = max(0.0, round(float(data.free_delivery_threshold or 0.0), 2))
        await set_setting_raw(db, "min_order_amount", str(min_amt))
        await set_setting_raw(db, "delivery_fee", str(d_fee))
        await set_setting_raw(db, "free_delivery_threshold", str(free_thr))
        await db.commit()
    return {
        "success": True,
        "min_order_amount": min_amt,
        "delivery_fee": d_fee,
        "free_delivery_threshold": free_thr
    }

@app.post("/api/admin/channels")
async def update_admin_channels(data: AdminChannelsSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        news_url = normalize_tg_link(data.news_channel_url)
        reviews_url = normalize_tg_link(data.reviews_channel_url)
        supp = data.support_username.strip() or "@warat_24"
        if not supp.startswith("@") and not supp.startswith("http"):
            supp = "@" + supp
        await set_setting_raw(db, "news_channel_url", news_url)
        await set_setting_raw(db, "reviews_channel_url", reviews_url)
        await set_setting_raw(db, "support_username", supp)
        await db.commit()
    return {"success": True, "news_channel_url": news_url, "reviews_channel_url": reviews_url, "support_username": supp}

@app.post("/api/admin/manage_category")
async def admin_manage_category(data: AdminCategoryManageSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        cats = await get_categories_list(db)
        if data.action == "add":
            c_name = data.name.strip()
            if not c_name:
                raise HTTPException(status_code=400, detail="Empty category name")
            if not any(c["name"].lower() == c_name.lower() for c in cats):
                new_id = f"cat_{int(time.time() * 1000)}"
                cats.append({"id": new_id, "name": c_name})
        elif data.action == "rename":
            c_id = data.id.strip()
            c_name = data.name.strip()
            if not c_id or not c_name:
                raise HTTPException(status_code=400, detail="Invalid category rename")
            for c in cats:
                if c["id"] == c_id:
                    c["name"] = c_name
        elif data.action == "delete":
            c_id = data.id.strip()
            cats = [c for c in cats if c["id"] != c_id]
        await set_setting_raw(db, "categories", json.dumps(cats, ensure_ascii=False))
        await db.commit()
    return {"success": True, "categories": cats}

@app.post("/api/admin/banner")
async def update_admin_banner(data: CourierBannerSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        await set_setting_raw(db, "banner_enabled", "1" if data.enabled else "0")
        await set_setting_raw(db, "banner_title", data.title.strip())
        await set_setting_raw(db, "banner_desc", data.desc.strip())
        await set_setting_raw(db, "banner_badge", data.badge.strip())
        await db.commit()
    return {"success": True}

@app.post("/api/courier/banner")
async def update_courier_banner(data: CourierBannerSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_courier(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only courier or owner")
        await set_setting_raw(db, "banner_enabled", "1" if data.enabled else "0")
        await set_setting_raw(db, "banner_title", data.title.strip())
        await set_setting_raw(db, "banner_desc", data.desc.strip())
        await set_setting_raw(db, "banner_badge", data.badge.strip())
        await db.commit()
    return {"success": True}

@app.post("/api/subscribe_stock")
async def subscribe_stock(data: StockNotifySchema):
    if not data.user_id:
        raise HTTPException(status_code=400, detail="No user id")
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute(
            "SELECT id FROM stock_notifications WHERE user_id = ? AND product_id = ? AND option_name = ?",
            (data.user_id, data.product_id, data.option_name.strip())
        ) as cur:
            if not await cur.fetchone():
                await db.execute(
                    "INSERT INTO stock_notifications (user_id, product_id, option_name) VALUES (?, ?, ?)",
                    (data.user_id, data.product_id, data.option_name.strip())
                )
                await db.commit()
    return {"success": True}

@app.post("/api/subscribe_shop_open")
async def subscribe_shop_open(data: ShopOpenNotifySchema):
    if not data.user_id:
        raise HTTPException(status_code=400, detail="No user id")
    async with aiosqlite.connect(DB_FILE) as db:
        subs = [int(x) for x in await get_setting_list(db, "shop_open_subscribers")]
        if int(data.user_id) not in subs:
            subs.append(int(data.user_id))
            await set_setting_list(db, "shop_open_subscribers", subs)
            await db.commit()
    return {"success": True}

@app.post("/api/admin/shop_status")
async def admin_shop_status(data: AdminShopStatusSchema):
    notify_uids = []
    brand_name = "Monkey Vape"
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        brand_name = await get_shop_brand_name(db)
        was_open = (await get_setting_raw(db, "shop_open", "1")) == "1"
        await set_setting_raw(db, "shop_open", "1" if data.is_open else "0")
        if data.closed_message.strip():
            await set_setting_raw(db, "closed_message", data.closed_message.strip())

        if data.is_open and not was_open:
            notify_uids = [int(x) for x in await get_setting_list(db, "shop_open_subscribers")]
            if notify_uids:
                await set_setting_list(db, "shop_open_subscribers", [])
        await db.commit()

    for uid in notify_uids:
        try:
            await bot.send_message(
                uid,
                f"🟢 <b>Магазин {html.escape(brand_name)} снова открыт!</b>\n\nТеперь вы можете оформить заказ в каталоге.",
                parse_mode="HTML"
            )
            await asyncio.sleep(0.05)
        except Exception:
            pass
    return {"success": True}

@app.post("/api/admin/appearance")
async def admin_appearance(data: AdminAppearanceSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        season = data.season_effect if data.season_effect in ("none", "winter", "autumn", "spring", "summer", "rain") else "none"
        color = data.hit_color.strip() or "#ffcc00"
        await set_setting_raw(db, "season_effect", season)
        await set_setting_raw(db, "hit_color", color)
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_metro")
async def admin_manage_metro(data: AdminMetroManageSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        if data.line not in ("green", "blue", "red"):
            raise HTTPException(status_code=400, detail="Invalid line")
        st_name = data.station.strip()
        if not st_name:
            raise HTTPException(status_code=400, detail="Empty station")
        metro_map = await get_metro_map(db)
        if data.action == "add":
            if not any(s["name"].lower() == st_name.lower() for s in metro_map[data.line]):
                metro_map[data.line].append({"name": st_name, "line": LINE_NAMES[data.line]})
        elif data.action == "delete":
            metro_map[data.line] = [s for s in metro_map[data.line] if s["name"] != st_name]
        await set_setting_raw(db, "metro_stations", json.dumps(metro_map, ensure_ascii=False))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_time")
async def admin_manage_time(data: AdminTimeManageSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        t_str = data.time.strip()
        if not t_str:
            raise HTTPException(status_code=400, detail="Empty time")
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
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
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
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
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
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        code = data.code.strip().upper()
        dtype = data.discount_type if data.discount_type in ("rub", "percent") else "rub"
        max_uses = max(0, int(data.max_uses or 0))
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
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        code = data.code.strip().upper()
        await db.execute("DELETE FROM promocodes WHERE code = ?", (code,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/save_product")
async def admin_save_product(data: AdminProductSaveSchema):
    clean_opts = [{"name": str(o.get("name", "")).strip(), "available": bool(o.get("available", True))} for o in (data.options or []) if str(o.get("name", "")).strip()]
    if not clean_opts:
        clean_opts = [{"name": o, "available": True} for o in DEFAULT_OPTIONS_BY_CAT.get(data.category, ["Стандарт"])]
    opts_json = json.dumps(clean_opts, ensure_ascii=False)

    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        if data.id and data.id > 0:
            async with db.execute("SELECT available FROM products WHERE id = ?", (data.id,)) as cur:
                old_row = await cur.fetchone()
            was_avail = bool(old_row[0]) if old_row else False

            await db.execute(
                """UPDATE products SET title = ?, category = ?, price = ?, old_price = ?, tag = ?, icon = ?,
                   available = ?, image_url = ?, has_discount = ?, low_stock = ?, options_json = ? WHERE id = ?""",
                (
                    data.title.strip(), data.category, float(data.price), float(data.old_price or 0.0),
                    data.tag.strip(), data.icon.strip() or "🧪", 1 if data.available else 0,
                    data.image_url.strip(), 1 if data.has_discount else 0, 1 if data.low_stock else 0,
                    opts_json, data.id
                )
            )
            avail_opt_names = [o["name"] for o in clean_opts if o["available"]]
            if data.available:
                await notify_stock_subscribers(db, data.id, data.title.strip(), avail_opt_names, all_restocked=(not was_avail))
        else:
            await db.execute(
                """INSERT INTO products (title, category, price, old_price, tag, icon, available, image_url, has_discount, low_stock, options_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.title.strip(), data.category, float(data.price), float(data.old_price or 0.0),
                    data.tag.strip(), data.icon.strip() or "🧪", 1 if data.available else 0,
                    data.image_url.strip(), 1 if data.has_discount else 0, 1 if data.low_stock else 0,
                    opts_json
                )
            )
        await db.commit()
    return {"success": True}

@app.post("/api/admin/toggle_product")
async def admin_toggle_product(data: AdminProductToggleSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        if data.field == "available":
            async with db.execute("SELECT title, available, category, options_json FROM products WHERE id = ?", (data.product_id,)) as cur:
                row = await cur.fetchone()
            await db.execute("UPDATE products SET available = CASE WHEN available = 1 THEN 0 ELSE 1 END WHERE id = ?", (data.product_id,))
            if row and not bool(row[1]):
                opts = parse_product_options(row[3] or "", row[2])
                avail_names = [o["name"] for o in opts if o["available"]]
                await notify_stock_subscribers(db, data.product_id, row[0], avail_names, all_restocked=True)
        elif data.field == "hit":
            await db.execute("UPDATE products SET tag = CASE WHEN tag = 'хит' THEN '' ELSE 'хит' END WHERE id = ?", (data.product_id,))
        elif data.field == "discount":
            await db.execute("UPDATE products SET has_discount = CASE WHEN has_discount = 1 THEN 0 ELSE 1 END WHERE id = ?", (data.product_id,))
        elif data.field == "low_stock":
            await db.execute("UPDATE products SET low_stock = CASE WHEN low_stock = 1 THEN 0 ELSE 1 END WHERE id = ?", (data.product_id,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/delete_product")
async def admin_delete_product(data: AdminProductDeleteSchema):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        await db.execute("DELETE FROM products WHERE id = ?", (data.product_id,))
        await db.execute("DELETE FROM stock_notifications WHERE product_id = ?", (data.product_id,))
        await db.commit()
    return {"success": True}

@app.post("/api/admin/manage_role")
async def admin_manage_role(data: AdminRoleManageSchema):
    tid = int(data.target_id)
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        if data.action == "add_owner":
            owners = [int(x) for x in await get_setting_list(db, "extra_owners")]
            if tid not in owners and tid not in PRIMARY_OWNER_IDS:
                owners.append(tid)
                await set_setting_list(db, "extra_owners", owners)
        elif data.action == "remove_owner":
            if tid in PRIMARY_OWNER_IDS:
                raise HTTPException(status_code=400, detail="Cannot remove primary owner")
            owners = [int(x) for x in await get_setting_list(db, "extra_owners") if int(x) != tid]
            await set_setting_list(db, "extra_owners", owners)
        elif data.action == "add_courier":
            removed_defs = [int(x) for x in await get_setting_list(db, "removed_default_couriers") if int(x) != tid]
            await set_setting_list(db, "removed_default_couriers", removed_defs)
            couriers = [int(x) for x in await get_setting_list(db, "extra_couriers")]
            if tid not in couriers and tid not in DEFAULT_COURIER_IDS:
                couriers.append(tid)
                await set_setting_list(db, "extra_couriers", couriers)
        elif data.action == "remove_courier":
            couriers = [int(x) for x in await get_setting_list(db, "extra_couriers") if int(x) != tid]
            await set_setting_list(db, "extra_couriers", couriers)
            if tid in DEFAULT_COURIER_IDS:
                removed_defs = [int(x) for x in await get_setting_list(db, "removed_default_couriers")]
                if tid not in removed_defs:
                    removed_defs.append(tid)
                    await set_setting_list(db, "removed_default_couriers", removed_defs)
        elif data.action == "ban_user":
            if await check_is_owner(db, tid):
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
    now = datetime.now()
    today_prefix = now.strftime("%d.%m.%Y")
    week_ago = now - timedelta(days=7)

    today_rev = week_rev = total_rev = 0.0
    today_cnt = week_cnt = total_cnt = cancelled_cnt = active_cnt = 0
    item_counts, station_counts, courier_map = {}, {}, {}

    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, user_id):
            raise HTTPException(status_code=403, detail="Only owner")
        async with db.execute("SELECT total, status, created_at, items, station, claimed_by_id, claimed_by_name FROM orders") as cursor:
            rows = await cursor.fetchall()

        for total, status, created_at, items_json, station, c_id, c_name in rows:
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
                c_label = c_name if c_name else (f"ID {c_id}" if c_id else "Без закрепления")
                if c_label not in courier_map:
                    courier_map[c_label] = {"name": c_label, "count": 0, "revenue": 0.0}
                courier_map[c_label]["count"] += 1
                courier_map[c_label]["revenue"] = round(courier_map[c_label]["revenue"] + val, 2)
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
    courier_stats = sorted(courier_map.values(), key=lambda x: x["revenue"], reverse=True)

    return {
        "today_rev": round(today_rev, 2), "today_cnt": today_cnt,
        "week_rev": round(week_rev, 2), "week_cnt": week_cnt,
        "total_rev": round(total_rev, 2), "total_cnt": total_cnt,
        "cancelled_cnt": cancelled_cnt, "active_cnt": active_cnt,
        "top_items": [{"title": k, "qty": v} for k, v in top_items],
        "top_stations": [{"station": k, "count": v} for k, v in top_stations],
        "courier_stats": courier_stats
    }

@app.get("/api/admin/broadcast_history/{user_id}")
async def admin_broadcast_history(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, user_id):
            raise HTTPException(status_code=403, detail="Only owner")
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
    text = data.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, data.user_id):
            raise HTTPException(status_code=403, detail="Only owner")
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
        if shop_open_raw != "1":
            closed_msg = await get_setting_raw(db, "closed_message", "Витрина сейчас на паузе, скоро вернёмся в онлайн.")
            raise HTTPException(status_code=403, detail=closed_msg)

        banned = [int(x) for x in await get_setting_list(db, "banned_users")]
        if int(order.user_id) in banned:
            raise HTTPException(status_code=403, detail="Ваш аккаунт заблокирован в магазине.")

        currency = await get_setting_raw(db, "currency", "р.")
        if currency not in ALLOWED_CURRENCIES:
            currency = "р."
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        if delivery_mode not in ALLOWED_DELIVERY_MODES:
            delivery_mode = "metro"

        min_order_amount = float(await get_setting_raw(db, "min_order_amount", "0") or 0)
        configured_delivery_fee = float(await get_setting_raw(db, "delivery_fee", "0") or 0)
        free_delivery_threshold = float(await get_setting_raw(db, "free_delivery_threshold", "0") or 0)

        items_subtotal = round(sum(float(i.get("price", 0)) * int(i.get("qty", 1)) for i in order.items), 2)
        if min_order_amount > 0 and items_subtotal + 1e-6 < min_order_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Минимальная сумма заказа: {min_order_amount:.2f} {currency}"
            )

        if configured_delivery_fee > 0:
            if free_delivery_threshold > 0 and items_subtotal >= free_delivery_threshold:
                applied_delivery_fee = 0.0
            else:
                applied_delivery_fee = round(configured_delivery_fee, 2)
        else:
            applied_delivery_fee = 0.0

        net_items_total = max(0.0, round(items_subtotal - float(order.discount or 0.0), 2))
        final_total = round(net_items_total + applied_delivery_fee, 2)

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
               (id, user_id, user_name, station, time, total, items, status, time_changed, hidden_by_courier, promo_code, discount, delivery_fee, created_at, cancelled_by, claimed_by_id, claimed_by_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, '', 0, '')""",
            (
                order_id, order.user_id, order.user_name, order.station, order.time,
                final_total, json.dumps(order.items), order.status, order.promo_code, order.discount, applied_delivery_fee, created_at
            )
        )
        all_couriers = await get_all_courier_ids(db)
        all_owners = await get_all_owner_ids(db)
        await db.commit()

    safe_cur = html.escape(currency)
    safe_user = html.escape(order.user_name or "User")
    loc_label = html.escape(get_location_label(delivery_mode))
    loc_value = html.escape(format_location_value(order.station, delivery_mode))
    safe_time = html.escape(order.time or "")
    items_str = "\n".join([f"• {html.escape(str(i['title']))} × {i['qty']} — {(i['price'] * i['qty']):.2f} {safe_cur}" for i in order.items])
    promo_line = f"\n🎟 <b>Промокод:</b> {html.escape(order.promo_code)} (-{order.discount:.2f} {safe_cur})" if order.promo_code else ""
    if applied_delivery_fee > 0:
        deliv_line = f"\n🚚 <b>Доставка:</b> {applied_delivery_fee:.2f} {safe_cur}"
    elif configured_delivery_fee > 0 and free_delivery_threshold > 0:
        deliv_line = f"\n🚚 <b>Доставка:</b> бесплатно (от {free_delivery_threshold:.2f} {safe_cur})"
    else:
        deliv_line = ""

    courier_text = (
        f"🛵 <b>Новый заказ #{html.escape(order_id)}!</b>\n\n"
        f"👤 <b>Покупатель:</b> {safe_user} (<code>{order.user_id}</code>)\n"
        f"📍 <b>{loc_label}:</b> {loc_value}\n"
        f"⏰ <b>Время встречи:</b> {safe_time}\n"
        f"💰 <b>К получению:</b> {final_total:.2f} {safe_cur}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_str}{promo_line}{deliv_line}\n\n"
        f"Откройте вкладку <b>«Курьер»</b> в приложении, чтобы взять заказ в работу."
    )

    for cid in all_couriers:
        try:
            courier_url = build_personal_url(cid, "Courier", is_owner=(cid in all_owners), is_courier=True)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛵 Открыть панель курьера", web_app=WebAppInfo(url=courier_url))]
            ])
            await bot.send_message(cid, courier_text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            print(f"[ERR] Курьер {cid}: {e}")

    user_text = (
        f"✨ <b>Заказ #{html.escape(order_id)} принят!</b>\n"
        f"📅 <b>Оформлен:</b> {html.escape(created_at)}\n\n"
        f"📍 <b>{loc_label}:</b> {loc_value}\n"
        f"⏰ <b>Время встречи:</b> {safe_time}\n\n"
        f"📦 <b>Состав заказа:</b>\n{items_str}{promo_line}{deliv_line}\n\n"
        f"💰 <b>Итого к оплате:</b> {final_total:.2f} {safe_cur}\n\n"
        f"Заказ передан курьеру. Отслеживать статус можно во вкладке <b>«Заказы»</b>."
    )

    if order.user_id:
        try:
            await bot.send_message(order.user_id, user_text, parse_mode="HTML")
        except Exception as e:
            print(f"[ERR] Покупатель {order.user_id}: {e}")

    return {"success": True, "order_id": order_id, "total": final_total, "delivery_fee": applied_delivery_fee}

@app.post("/api/courier/claim_order")
async def courier_claim_order(data: CourierClaimSchema):
    oid = str(data.order_id).strip()
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_courier(db, data.courier_id):
            raise HTTPException(status_code=403, detail="Нет прав курьера")
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        async with db.execute("SELECT user_id, claimed_by_id, claimed_by_name, station, time, status FROM orders WHERE id = ?", (oid,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Заказ не найден")
        buyer_id, current_cid, current_cname, station, time_str, status = row[0], int(row[1] or 0), row[2], row[3], row[4], row[5]
        if status != "active":
            raise HTTPException(status_code=400, detail="Заказ уже завершён")
        if current_cid != 0 and current_cid != int(data.courier_id):
            raise HTTPException(status_code=409, detail=f"Заказ уже взял {current_cname}")

        await db.execute(
            "UPDATE orders SET claimed_by_id = ?, claimed_by_name = ? WHERE id = ?",
            (int(data.courier_id), data.courier_name.strip() or f"Курьер {data.courier_id}", oid)
        )
        await db.commit()

    loc_label = html.escape(get_location_label(delivery_mode))
    loc_value = html.escape(format_location_value(station, delivery_mode))
    if buyer_id and current_cid == 0:
        try:
            await bot.send_message(
                buyer_id,
                f"🛵 <b>Курьер уже везёт ваш заказ #{html.escape(oid)}!</b>\n"
                f"👤 Курьер: {html.escape(data.courier_name)}\n"
                f"📍 {loc_label}: {loc_value} в {html.escape(time_str)}",
                parse_mode="HTML"
            )
        except Exception:
            pass
    return {"success": True}

@app.post("/api/courier/arrived")
async def courier_arrived(data: CourierArrivedSchema):
    oid = str(data.order_id).strip()
    async with aiosqlite.connect(DB_FILE) as db:
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        async with db.execute("SELECT user_id, station, claimed_by_id FROM orders WHERE id = ?", (oid,)) as cur:
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    buyer_id, station, claimed_id = row[0], row[1], int(row[2] or 0)
    if claimed_id != 0 and data.courier_id and claimed_id != int(data.courier_id):
        raise HTTPException(status_code=403, detail="Этот заказ ведёт другой курьер")

    loc_value = html.escape(format_location_value(station, delivery_mode))
    if buyer_id:
        try:
            await bot.send_message(
                buyer_id,
                f"📍 <b>Курьер на месте ({loc_value})!</b>\n"
                f"Заказ #{html.escape(oid)} ожидает вас на месте встречи.",
                parse_mode="HTML"
            )
        except Exception:
            pass
    return {"success": True}

@app.get("/api/orders")
async def get_orders(courier_id: int = 0):
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM orders WHERE hidden_by_courier = 0 ORDER BY rowid DESC") as cursor:
            rows = await cursor.fetchall()
            result = []
            for row in rows:
                c_id = int(row["claimed_by_id"] or 0)
                if courier_id and c_id != 0 and c_id != int(courier_id):
                    continue
                result.append({
                    "id": str(row["id"]), "user_id": row["user_id"], "user_name": row["user_name"],
                    "station": row["station"], "time": row["time"], "total": row["total"],
                    "items": json.loads(row["items"]), "status": row["status"],
                    "time_changed": bool(row["time_changed"]), "hidden_by_courier": bool(row["hidden_by_courier"]),
                    "promo_code": row["promo_code"] or "", "discount": row["discount"] or 0.0,
                    "delivery_fee": row["delivery_fee"] or 0.0,
                    "created_at": row["created_at"] or "", "cancelled_by": row["cancelled_by"] or "",
                    "claimed_by_id": c_id, "claimed_by_name": row["claimed_by_name"] or ""
                })
            return result

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
                "discount": row["discount"] or 0.0, "delivery_fee": row["delivery_fee"] or 0.0,
                "created_at": row["created_at"] or "",
                "cancelled_by": row["cancelled_by"] or "",
                "claimed_by_id": row["claimed_by_id"] or 0, "claimed_by_name": row["claimed_by_name"] or ""
            } for row in await cursor.fetchall()]

@app.post("/api/update_order_status")
async def update_order_status(data: StatusUpdateSchema):
    cancelled_by = data.cancelled_by if data.status == 'cancelled' else ''
    async with aiosqlite.connect(DB_FILE) as db:
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        async with db.execute("SELECT user_id, user_name, station, time, claimed_by_id FROM orders WHERE id = ?", (str(data.order_id),)) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Order not found")

        user_id, user_name, station, time_val, existing_claimed_id = row[0], row[1], row[2], row[3], int(row[4] or 0)

        if cancelled_by != 'client' and existing_claimed_id != 0 and data.courier_id and existing_claimed_id != int(data.courier_id):
            raise HTTPException(status_code=403, detail="Этот заказ закреплён за другим курьером")

        if data.courier_id:
            await db.execute(
                """UPDATE orders SET status = ?, cancelled_by = ?,
                   claimed_by_id = CASE WHEN claimed_by_id = 0 THEN ? ELSE claimed_by_id END,
                   claimed_by_name = CASE WHEN claimed_by_name = '' THEN ? ELSE claimed_by_name END
                   WHERE id = ?""",
                (data.status, cancelled_by, int(data.courier_id), data.courier_name, str(data.order_id))
            )
        else:
            await db.execute("UPDATE orders SET status = ?, cancelled_by = ? WHERE id = ?", (data.status, cancelled_by, str(data.order_id)))
        all_couriers = await get_all_courier_ids(db)
        news_url = await get_setting_raw(db, "news_channel_url", "")
        reviews_url = await get_setting_raw(db, "reviews_channel_url", "")
        await db.commit()

        safe_user = html.escape(user_name or "User")
        loc_value = html.escape(format_location_value(station, delivery_mode))
        if data.status == 'cancelled':
            who_text = "Отменено клиентом" if cancelled_by == 'client' else ("Отменено курьером" if cancelled_by == 'courier' else "Заказ отменён")
            if user_id:
                try:
                    await bot.send_message(user_id, f"❌ Заказ #{html.escape(str(data.order_id))} — <b>{who_text}</b>.", parse_mode="HTML")
                except Exception:
                    pass
            notify_targets = [existing_claimed_id] if (existing_claimed_id != 0 and cancelled_by == 'client') else all_couriers
            for cid in notify_targets:
                if cid:
                    try:
                        await bot.send_message(cid, f"❌ Заказ #{html.escape(str(data.order_id))} ({safe_user}, {loc_value}) — <b>{who_text}</b>.", parse_mode="HTML")
                    except Exception:
                        pass
        elif data.status == 'completed':
            if user_id:
                try:
                    completed_msg = f"🎉 <b>Заказ #{html.escape(str(data.order_id))} успешно выдан! Спасибо, что выбираешь нас.</b>"
                    kb_rows = []
                    if reviews_url:
                        completed_msg += f"\n\n⭐ <b>Будем рады твоему отзыву о заказе:</b>\n{html.escape(reviews_url)}"
                        kb_rows.append([InlineKeyboardButton(text="⭐ Оставить отзыв", url=reviews_url)])
                    if news_url:
                        completed_msg += f"\n\n✈️ <b>Следите за новостями и поступлениями в канале:</b>\n{html.escape(news_url)}"
                        kb_rows.append([InlineKeyboardButton(text="✈️ Канал с новостями", url=news_url)])
                    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows) if kb_rows else None
                    await bot.send_message(user_id, completed_msg, parse_mode="HTML", reply_markup=markup)
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
        delivery_mode = await get_setting_raw(db, "delivery_mode", "metro")
        await db.execute("UPDATE orders SET time = ?, time_changed = 1 WHERE id = ?", (data.time, str(data.order_id)))
        all_couriers = await get_all_courier_ids(db)
        await db.commit()

        async with db.execute("SELECT user_id, user_name, station, claimed_by_id FROM orders WHERE id = ?", (str(data.order_id),)) as cursor:
            row = await cursor.fetchone()
            if row:
                user_id, user_name, station, claimed_id = row[0], row[1], row[2], int(row[3] or 0)
                safe_user = html.escape(user_name or "User")
                loc_label = html.escape(get_location_label(delivery_mode))
                loc_value = html.escape(format_location_value(station, delivery_mode))
                targets = [claimed_id] if claimed_id != 0 else all_couriers
                for cid in targets:
                    try:
                        await bot.send_message(
                            cid,
                            f"⏰ <b>Клиент перенёс время заказа #{html.escape(str(data.order_id))}</b>\n"
                            f"👤 Покупатель: {safe_user} (<code>{user_id}</code>)\n"
                            f"📍 {loc_label}: {loc_value}\n"
                            f"🕒 Новое время: <b>{html.escape(data.time)}</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
    return {"success": True}

@app.get("/api/check_role/{user_id}")
async def check_role(user_id: int):
    async with aiosqlite.connect(DB_FILE) as db:
        if await check_is_owner(db, user_id):
            return {"role": "owner"}
        if await check_is_courier(db, user_id):
            return {"role": "courier"}
    return {"role": "client"}

@dp.message(F.photo)
async def handle_owner_photo_upload(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
    file_id = message.photo[-1].file_id
    base = PUBLIC_TUNNEL_URL.strip().rstrip("/")
    photo_url = f"{base}/api/tg_photo/{file_id}"
    await message.answer(
        f"🖼 <b>Прямая ссылка на фото готова!</b>\n\n"
        f"Можешь выбрать фото прямо из галереи в админ-панели или вставить эту ссылку:\n"
        f"<code>{html.escape(photo_url)}</code>",
        parse_mode="HTML"
    )

@dp.message(F.text.startswith("/seturl"))
async def cmd_set_tunnel_url(message: Message):
    global PUBLIC_TUNNEL_URL
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
    new_url = message.text[7:].strip().rstrip("/")
    if not new_url.startswith("http"):
        await message.answer("Укажи ссылку после команды, например:\n<code>/seturl https://твой-адрес</code>", parse_mode="HTML")
        return
    PUBLIC_TUNNEL_URL = new_url
    try:
        with open(TUNNEL_FILE, "w", encoding="utf-8") as f:
            f.write(new_url)
    except Exception:
        pass
    await message.answer(f"✅ Новый адрес сервера сохранён:\n<code>{html.escape(new_url)}</code>\n\nНажми /start, чтобы обновить кнопку.", parse_mode="HTML")

@dp.message(F.text == "/stats")
async def cmd_owner_stats(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
        currency = html.escape(await get_setting_raw(db, "currency", "р."))
        now = datetime.now()
        today_prefix = now.strftime("%d.%m.%Y")
        week_ago = now - timedelta(days=7)
        today_rev = week_rev = total_rev = 0.0
        today_cnt = week_cnt = total_cnt = active_cnt = 0
        async with db.execute("SELECT total, status, created_at FROM orders") as cursor:
            for total, status, created_at in await cursor.fetchall():
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
                elif status == "active":
                    active_cnt += 1
        async with db.execute("SELECT COUNT(*) FROM users WHERE user_id > 0") as cur:
            u_row = await cur.fetchone()
            subs_cnt = u_row[0] if u_row else 0

    await message.answer(
        f"📊 <b>Аналитика витрины:</b>\n\n"
        f"📅 <b>Сегодня:</b> {today_rev:.2f} {currency} ({today_cnt} зак.)\n"
        f"🗓 <b>За 7 дней:</b> {week_rev:.2f} {currency} ({week_cnt} зак.)\n"
        f"💰 <b>Всего выручка:</b> {total_rev:.2f} {currency} ({total_cnt} зак.)\n"
        f"🛵 <b>Активных заказов:</b> {active_cnt}\n"
        f"👥 <b>Аудитория бота:</b> {subs_cnt} чел.",
        parse_mode="HTML"
    )

@dp.message(F.text == "/open")
async def cmd_owner_open_shop(message: Message):
    notify_uids = []
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
        brand_name = await get_shop_brand_name(db)
        was_open = (await get_setting_raw(db, "shop_open", "1")) == "1"
        await set_setting_raw(db, "shop_open", "1")
        if not was_open:
            notify_uids = [int(x) for x in await get_setting_list(db, "shop_open_subscribers")]
            if notify_uids:
                await set_setting_list(db, "shop_open_subscribers", [])
        await db.commit()

    for uid in notify_uids:
        try:
            await bot.send_message(
                uid,
                f"🟢 <b>Магазин {html.escape(brand_name)} снова открыт!</b>\n\nТеперь вы можете оформить заказ в каталоге.",
                parse_mode="HTML"
            )
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer("🟢 <b>Витрина открыта!</b> Приём заказов возобновлён.", parse_mode="HTML")

@dp.message(F.text.startswith("/close"))
async def cmd_owner_close_shop(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
        await set_setting_raw(db, "shop_open", "0")
        reason = message.text[6:].strip()
        if reason:
            await set_setting_raw(db, "closed_message", reason)
        cur_msg = await get_setting_raw(db, "closed_message", "Витрина сейчас на паузе, скоро вернёмся в онлайн.")
        await db.commit()
    await message.answer(f"🔴 <b>Витрина закрыта!</b>\nСтатус для клиентов: <i>{html.escape(cur_msg)}</i>", parse_mode="HTML")

@dp.message(F.text.startswith("/post"))
async def cmd_post_broadcast(message: Message):
    async with aiosqlite.connect(DB_FILE) as db:
        if not await check_is_owner(db, message.from_user.id):
            return
        async with db.execute("SELECT user_id FROM users WHERE user_id > 0") as cursor:
            rows = await cursor.fetchall()

    inline_text = message.text[5:].strip()
    if not message.reply_to_message and not inline_text:
        await message.answer(
            "📢 <b>Как запустить рассылку:</b>\n\n"
            "1. Отправь боту готовый пост (текст, фото, видео или кружочек).\n"
            "2. Нажми <b>«Ответить» (Reply)</b> на это сообщение и напиши <code>/post</code>.\n\n"
            "<i>Или отправь сразу:</i> <code>/post Текст объявления</code>",
            parse_mode="HTML"
        )
        return

    user_ids = [r[0] for r in rows]
    status_msg = await message.answer(f"⏳ Запускаю рассылку по базе ({len(user_ids)} чел.)...")

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
        f"🚫 Недоступны / заблокировали бота: <b>{failed}</b>",
        parse_mode="HTML"
    )

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    uid = message.from_user.id
    first_name = message.from_user.first_name or "друг"
    uname = f"@{message.from_user.username}" if message.from_user.username else first_name
    now_str = datetime.now().strftime("%d.%m.%Y, %H:%M")

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR REPLACE INTO users (user_id, user_name, joined_at) VALUES (?, ?, ?)",
            (uid, uname, now_str)
        )
        is_own = await check_is_owner(db, uid)
        is_cour = await check_is_courier(db, uid)
        brand_name = await get_shop_brand_name(db)
        welcome_tpl = await get_setting_raw(db, "welcome_text", DEFAULT_WELCOME_TEXT)
        await db.commit()

    personal_url = build_personal_url(uid, uname, is_owner=is_own, is_courier=is_cour)
    try:
        await bot.set_chat_menu_button(
            chat_id=uid,
            menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=personal_url))
        )
    except Exception:
        pass

    welcome_rendered = render_welcome_message(welcome_tpl, first_name, brand_name)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f"🛍 Открыть {brand_name}", web_app=WebAppInfo(url=personal_url))]],
        resize_keyboard=True
    )
    try:
        await message.answer(
            welcome_rendered,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception:
        plain_fallback = (welcome_tpl or DEFAULT_WELCOME_TEXT).replace("{user}", first_name).replace("{brand}", brand_name)
        await message.answer(
            plain_fallback,
            reply_markup=kb
        )

async def main():
    asyncio.create_task(dp.start_polling(bot))
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
