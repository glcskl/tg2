import json
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN. Создай .env и добавь BOT_TOKEN=...")

DAYS = [("пн", "Понедельник"), ("вт", "Вторник"), ("ср", "Среда"), ("чт", "Четверг"), ("пт", "Пятница")]


def get_current_week() -> str:
    """
    Определяет чётность недели.
    С субботы 00:00 уже показывается РАСПИСАНИЕ СЛЕДУЮЩЕЙ недели,
    чтобы в выходные не висело расписание прошедшей недели.
    """
    now = datetime.now()
    if now.weekday() >= 5:  # суббота или воскресенье — берём следующий понедельник
        now = now + timedelta(days=7 - now.weekday())
    week_number = now.isocalendar()[1]
    if week_number % 2 == 0:
        return "числитель"
    else:
        return "знаменатель"


def load_schedule() -> dict:
    with open("schedule.json", "r", encoding="utf-8") as f:
        return json.load(f)


# Главное меню
def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Расписание", callback_data="schedule")
    kb.adjust(1)
    return kb.as_markup()


# Клавиатура дней недели
def day_keyboard():
    kb = InlineKeyboardBuilder()
    for key, title in DAYS:
        kb.button(text=title, callback_data=f"day:{key}")
    kb.button(text="🔙 Назад", callback_data="back")
    kb.adjust(5, 1)
    return kb.as_markup()


# Клавиатура "Назад"
def back_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="back")
    return kb.as_markup()


# Номер пары по времени начала звонка (СПбГАСУ)
PAIR_BY_START = {
    "09:00": 1,
    "10:45": 2,
    "12:30": 3,
    "15:00": 4,
    "16:45": 5,
    "18:30": 6,
    "20:15": 7,
}


def format_day(schedule: dict, week: str, day: str) -> str:
    items = schedule.get(week, {}).get(day, [])
    day_name = dict(DAYS).get(day, day)

    header = f"📅 *{day_name.upper()}*\n📅 Неделя: *{week}*\n"
    if not items:
        return header + "\n✅ Нет пар"

    lines = [header]
    for i, it in enumerate(items, 1):
        time = (it.get("time") or "").strip()
        subject = (it.get("subject") or "").strip()
        kind = (it.get("kind") or "").strip()
        teacher = (it.get("teacher") or "").strip()
        room = (it.get("room") or "").strip()

        num = PAIR_BY_START.get(time.split("-")[0], i)
        title = subject
        if kind:
            kind_emoji = {"лк": "📖", "лб": "🔬", "пр": "✏️"}.get(kind, "📚")
            title = f"{subject} ({kind_emoji} {kind})"

        block = [f"{num}️⃣ ⏰ *{time}*", f"   📚 {title}"]

        if teacher:
            block.append(f"   👤 {teacher}")
        if room:
            block.append(f"   🏫 {room}")

        lines.append("\n".join(block))

    return "\n\n".join(lines).strip()


# Последнее сообщение бота в чате (для самоочистки при новом /start)
_last_bot_message = {}


# Хендлеры
async def start(message: Message):
    chat_id = message.chat.id
    prev = _last_bot_message.pop(chat_id, None)
    if prev:
        try:
            await message.bot.delete_message(chat_id, prev)
        except Exception:
            pass

    week = get_current_week()
    sent = await message.answer(
        f"👋 Привет!\n📅 Текущая неделя: *{week}*\n\nВыбери действие 👇",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )
    _last_bot_message[chat_id] = sent.message_id


async def back_to_main(cb: CallbackQuery):
    week = get_current_week()
    await cb.message.edit_text(
        f"👋 Привет!\n📅 Текущая неделя: *{week}*\n\nВыбери действие 👇",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )
    await cb.answer()


async def show_schedule_menu(cb: CallbackQuery):
    week = get_current_week()
    await cb.message.edit_text(
        f"📅 *Расписание занятий*\n📅 Неделя: *{week}*\n\nВыбери день 👇",
        reply_markup=day_keyboard(),
        parse_mode="Markdown"
    )
    await cb.answer()


async def set_day(cb: CallbackQuery):
    day = cb.data.split(":", 1)[1]

    week = get_current_week()

    schedule = load_schedule()
    text = format_day(schedule, week, day)

    await cb.message.edit_text(
        text,
        reply_markup=day_keyboard(),
        parse_mode="Markdown"
    )
    await cb.answer()


async def fallback(message: Message):
    await message.answer("Напиши /start чтобы открыть меню 🙂")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Регистрируем хендлеры
    dp.message.register(start, F.text.in_({"/start", "start"}))
    dp.callback_query.register(back_to_main, F.data == "back")
    dp.callback_query.register(show_schedule_menu, F.data == "schedule")
    dp.callback_query.register(set_day, F.data.startswith("day:"))
    dp.message.register(fallback)

    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())