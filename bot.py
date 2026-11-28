import json
import os
import html
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
WEEKS = ("числитель", "знаменатель")


def other_week(week: str) -> str:
    """Возвращает противоположную неделю (числитель <-> знаменатель)."""
    return "знаменатель" if week == "числитель" else "числитель"


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


def load_session() -> dict:
    with open("session.json", "r", encoding="utf-8") as f:
        return json.load(f)


# Главное меню
def main_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="📅 Расписание", callback_data="schedule")
    kb.button(text="📝 Экзамены", callback_data="exams")
    kb.button(text="✅ Зачёты", callback_data="credits")
    kb.button(text="📋 Вся сессия", callback_data="session")
    kb.adjust(1, 2, 1)
    return kb.as_markup()


# Клавиатура выбора недели
def week_keyboard():
    current = get_current_week()
    kb = InlineKeyboardBuilder()
    kb.button(text=f"📍 Текущая ({current})", callback_data="week:auto")
    kb.button(text=f"➡️ Следующая ({other_week(current)})", callback_data="week:next")
    kb.button(text="Числитель", callback_data="week:числитель")
    kb.button(text="Знаменатель", callback_data="week:знаменатель")
    kb.button(text="🔙 В меню", callback_data="back")
    kb.adjust(1, 1, 2, 1)
    return kb.as_markup()


def week_menu_text() -> str:
    return (
        f"📅 *Расписание занятий*\n"
        f"📍 Сейчас: *{get_current_week()}*\n\n"
        "Выбери неделю 👇"
    )


# Клавиатура дней недели
def day_keyboard(week=None):
    week = week or get_current_week()
    kb = InlineKeyboardBuilder()
    for key, title in DAYS:
        kb.button(text=title, callback_data=f"day:{week}:{key}")
    kb.button(text="🗓 Выбрать неделю", callback_data="weeks")
    kb.button(text="🔙 В меню", callback_data="back")
    kb.adjust(5, 2)
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


# Иконки видов аттестации в сессии
KIND_ICONS = {
    "КР": "📄",
    "КП": "📐",
    "зчО.": "✅",
    "зч.": "✅",
    "Э": "🎯",
    "ЭКЗ.": "🎯",
}


EXAM_KINDS = {"Э", "ЭКЗ."}
CREDIT_KINDS = {"зчО.", "зч."}


def format_session(session: dict, kinds=None, title=None, empty_text=None) -> str:
    """Собирает список сессии: события сгруппированы по датам."""
    group = (session.get("group") or "").strip()
    semester = (session.get("semester") or "").strip()
    items = session.get("items") or []

    if kinds:
        items = [item for item in items if (item.get("kind") or "").strip() in kinds]

    header = title or f"📝 <b>Сессия {html.escape(group)}</b>"
    if semester:
        header += f"\n🎓 {html.escape(semester)}"

    if not items:
        return header + "\n\n" + (empty_text or "✅ Расписание сессии пока не опубликовано")

    blocks = [header]
    current_date = None

    for item in items:
        date = (item.get("date") or "").strip()
        weekday = (item.get("weekday") or "").strip()
        time = (item.get("time") or "").strip()
        subject = (item.get("subject") or "").strip()
        kind = (item.get("kind") or "").strip()
        teacher = (item.get("teacher") or "").strip()
        room = (item.get("room") or "").strip()

        if date != current_date:
            current_date = date
            title = f"{date}, {weekday}" if weekday else date
            blocks.append(f"<b>{html.escape(title)}</b>")

        pair = item.get("pair") or PAIR_BY_START.get(time.split("-")[0])
        clock = f"⏰ <b>{html.escape(time)}</b>" if time else ""
        block = [f"{pair}️⃣ {clock}".strip() if pair else clock]

        if subject:
            title_subject = f"{subject} ({kind})" if kind else subject
            icon = KIND_ICONS.get(kind, "📚")
            block.append(f"   {icon} {html.escape(title_subject)}")
        if teacher:
            block.append(f"   👤 {html.escape(teacher)}")
        if room:
            block.append(f"   🏫 {html.escape(room)}")

        blocks.append("\n".join(line for line in block if line))

    if not kinds and not any((item.get("kind") or "").strip() in EXAM_KINDS for item in items):
        blocks.append("ℹ️ Экзаменов (Э) нет — только защиты курсовых и зачёты с оценкой.")

    if kinds == EXAM_KINDS:
        blocks.append("🎯 ЭКЗ. — экзамен")
    elif kinds == CREDIT_KINDS:
        blocks.append("✅ зчО. — зачёт с оценкой")
    else:
        blocks.append("📄 КР — курсовая работа · 📐 КП — курсовой проект · ✅ зчО. — зачёт с оценкой")

    updated = (session.get("updated") or "").strip()
    source = (session.get("source") or "").strip()
    footer = []
    if source:
        footer.append(f"📌 Источник: {html.escape(source)}")
    if updated:
        footer.append(f"🕓 Обновлено: {html.escape(updated)}")
    if footer:
        blocks.append("\n".join(footer))

    return "\n\n".join(blocks).strip()


def session_view(view: str) -> str:
    """Текст для кнопок «Экзамены», «Зачёты» и «Вся сессия»."""
    session = load_session()
    group = html.escape((session.get("group") or "").strip())

    views = {
        "exams": (EXAM_KINDS, f"📝 <b>Экзамены {group}</b>", "✅ Экзамены не найдены"),
        "credits": (CREDIT_KINDS, f"✅ <b>Зачёты {group}</b>", "✅ Зачёты не найдены"),
    }

    if view in views:
        kinds, title, empty_text = views[view]
        return format_session(session, kinds=kinds, title=title, empty_text=empty_text)

    return format_session(session, title=f"📋 <b>Вся сессия {group}</b>")


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
    await cb.message.edit_text(
        week_menu_text(),
        reply_markup=week_keyboard(),
        parse_mode="Markdown"
    )
    await cb.answer()


async def select_week(cb: CallbackQuery):
    choice = cb.data.split(":", 1)[1]
    current = get_current_week()

    if choice == "auto":
        week = current
    elif choice == "next":
        week = other_week(current)
    elif choice in WEEKS:
        week = choice
    else:
        await cb.answer()
        return

    await cb.message.edit_text(
        f"📅 *Расписание занятий*\n📐 Неделя: *{week}*\n\nВыбери день 👇",
        reply_markup=day_keyboard(week),
        parse_mode="Markdown"
    )
    await cb.answer()


async def back_to_weeks(cb: CallbackQuery):
    await cb.message.edit_text(
        week_menu_text(),
        reply_markup=week_keyboard(),
        parse_mode="Markdown"
    )
    await cb.answer()


async def show_session(cb: CallbackQuery):
    await cb.message.edit_text(
        session_view(cb.data),
        reply_markup=back_keyboard(),
        parse_mode="HTML"
    )
    await cb.answer()


async def set_day(cb: CallbackQuery):
    parts = cb.data.split(":")
    if len(parts) == 3:
        week, day = parts[1], parts[2]
    else:
        week, day = get_current_week(), parts[1]
    if week not in WEEKS:
        week = get_current_week()

    schedule = load_schedule()
    text = format_day(schedule, week, day)

    await cb.message.edit_text(
        text,
        reply_markup=day_keyboard(week),
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
    dp.callback_query.register(back_to_weeks, F.data == "weeks")
    dp.callback_query.register(show_schedule_menu, F.data == "schedule")
    dp.callback_query.register(select_week, F.data.startswith("week:"))
    dp.callback_query.register(show_session, F.data.in_({"exams", "credits", "session"}))
    dp.callback_query.register(set_day, F.data.startswith("day:"))
    dp.message.register(fallback)

    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())