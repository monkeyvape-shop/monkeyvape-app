import asyncio
import json
import logging
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

WEBAPP_URL = "https://monkeyvape-shop.github.io/monkeyvape-app/"
ADMIN_ID = 7280921605

IMAGE_PATH = "welcome.png"

user_ids = set()
verified_users = set()  # Множество для проверки подтверждения возраста 18+
total_orders_count = 0

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- КЛАВИАТУРЫ ---

age_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Мне есть 18 лет", callback_data="age_ok")],
        [InlineKeyboardButton(text="❌ Мне нет 18 лет", callback_data="age_fail")],
    ]
)

# Постоянное меню внизу экрана
main_menu_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(
                text="🛍 Открыть каталог (Mini App)",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        ],
        [
            KeyboardButton(text="🔥 Актуальные спецпредложения"),
        ],
        [
            KeyboardButton(text="👨‍💻 Связаться с менеджером"),
        ],
    ],
    resize_keyboard=True,
    is_persistent=True  # Кнопки закрепляются внизу и не пропадают
)


# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_ids.add(message.from_user.id)

    caption_text = (
        "💨 **Добро пожаловать в Monkey Vape Shop!**\n\n"
        "Для доступа к каталогу и оформлению заказов, пожалуйста, подтвердите ваш возраст:"
    )

    if os.path.exists(IMAGE_PATH):
        try:
            photo = FSInputFile(IMAGE_PATH)
            await message.answer_photo(
                photo=photo,
                caption=caption_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=age_keyboard,
            )
            return
        except Exception as e:
            logging.error(f"Ошибка при отправке фото: {e}")

    await message.answer(
        text=caption_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=age_keyboard,
    )


@dp.callback_query(F.data.in_({"age_ok", "age_fail"}))
async def process_age_check(callback: types.CallbackQuery):
    if callback.data == "age_ok":
        user_ids.add(callback.from_user.id)
        verified_users.add(callback.from_user.id)  # Запоминаем, что пользователь подтвердил возраст

        try:
            await callback.message.delete()
        except Exception as e:
            logging.error(f"Не удалось удалить сообщение: {e}")

        # Отправляем сообщение с постоянной нижней клавиатурой
        await callback.message.answer(
            "Спасибо! Доступ разрешен. Выберите нужный пункт в меню ниже 👇",
            reply_markup=main_menu_keyboard,
        )
    else:
        await callback.answer(
            "Извините, доступ к магазину разрешён только лицам старше 18 лет.",
            show_alert=True
        )
        return

    await callback.answer()


@dp.message(Command("stats"))
async def stats_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для просмотра статистики.")
        return

    stats_text = (
        f"📊 **Статистика бота MonkeyVape:**\n\n"
        f"👥 Всего пользователей: `{len(user_ids)}`\n"
        f"🔞 Подтвердили 18+: `{len(verified_users)}`\n"
        f"🛍 Всего оформлено заказов: `{total_orders_count}`\n"
        f"🟢 Статус: Бот работает"
    )
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("broadcast"))
async def broadcast_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    command_args = message.text.split(maxsplit=1)
    if len(command_args) < 2:
        await message.answer("Укажите текст рассылки.\nПример: `/broadcast Всем привет!`", parse_mode=ParseMode.MARKDOWN)
        return

    text_to_send = command_args[1]
    count = 0

    for uid in list(user_ids):
        try:
            await bot.send_message(chat_id=uid, text=text_to_send, parse_mode=ParseMode.MARKDOWN)
            count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")

    await message.answer(f"✅ Рассылка завершена!\nСообщение получили: **{count}** пользователей.", parse_mode=ParseMode.MARKDOWN)


# Обработка данных из Mini App (с проверкой возраста)
@dp.message(F.web_app_data)
async def web_app_data_handler(message: types.Message):
    user_id = message.from_user.id

    # ПРОВЕРКА: Если пользователь не подтверждал возраст, выводим предупреждение
    if user_id not in verified_users:
        await message.answer(
            "❌ **Ошибка оформления заказа!**\n\n"
            "Вам необходимо подтвердить возраст (18+). Введите команду /start и нажмите кнопку подтверждения.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=age_keyboard
        )
        return

    global total_orders_count
    total_orders_count += 1

    try:
        data = json.loads(message.web_app_data.data)
    except json.JSONDecodeError:
        await message.answer("Произошла ошибка при обработке данных заказа.")
        return

    user = message.from_user
    username_str = f"@{user.username}" if user.username else "Юзернейм не установлен"
    user_name = user.full_name

    items_list = "\n".join(
        [f"• {item['name']} — {item['price']}₽" for item in data.get("items", [])]
    )
    total_price = data.get("total", 0)
    metro = data.get("metro", "Не указано")
    time = data.get("time", "Не указано")
    payment = data.get("payment", "Не указано")

    admin_order_text = (
        f"🚨 НОВЫЙ ЗАКАЗ #{total_orders_count}!\n\n"
        f"👤 Покупатель: {user_name}\n"
        f"💬 Юзернейм: {username_str}\n"
        f"🆔 ID: {user.id}\n\n"
        f"📦 Состав заказа:\n{items_list}\n\n"
        f"📍 Метро: {metro}\n"
        f"⏰ Время: {time}\n"
        f"💳 Оплата: {payment}\n\n"
        f"💰 Сумма: {total_price} ₽"
    )

    try:
        await bot.send_message(
            chat_id=ADMIN_ID, text=admin_order_text
        )
    except Exception as e:
        logging.error(f"Не удалось отправить уведомление админу: {e}")

    client_text = (
        f"✅ Ваш заказ успешно принят!\n\n"
        f"Состав заказа:\n{items_list}\n\n"
        f"📍 Метро: {metro} ({time})\n"
        f"Итого: {total_price} ₽\n\n"
        f"Наш менеджер свяжется с вами для подтверждения брони."
    )

    await message.answer(client_text)


@dp.message(F.text == "🔥 Актуальные спецпредложения")
async def show_promos(message: types.Message):
    await message.answer(
        "🔥 **Актуальные спецпредложения:**\n\n1. 3+1 на жидкости!\n2. Скидка 15% на картриджи!",
        parse_mode=ParseMode.MARKDOWN,
    )


@dp.message(F.text == "👨‍💻 Связаться с менеджером")
async def contact_manager(message: types.Message):
    await message.answer(
        "По всем вопросам и для заказа пишите нашему менеджеру: https://t.me/warat_24"
    )


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())