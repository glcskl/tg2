import os
import json
import html
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv
from flask import Flask, request


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOTENV_PATH = os.path.join(BASE_DIR, ".env")

if os.path.exists(DOTENV_PATH):
    load_dotenv(DOTENV_PATH)
else:
    load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Нет BOT_TOKEN. Создай .env и добавь BOT_TOKEN=...")

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

app = Flask(__name__)

# ============================================
# SELF-PING MECHANISM (предотвращает засыпание)
# ============================================

def _set_webhook_with_retry(max_attempts: int = 5, delay: int = 30) -> None:
    """Регистрирует webhook с повторными попытками (Render cold start может занять 60+ сек)."""
    if not RENDER_EXTERNAL_URL:
        return
    webhook_url = f"{RENDER_EXTERNAL_URL}/webhook/{BOT_TOKEN}"
    for attempt in range(1, max_attempts + 1):
        try:
            result = tg_request(
                "setWebhook",
                {
                    "url": webhook_url,
                    "allowed_updates": ["message", "callback_query"],
                    "drop_pending_updates": True,
                },
            )
            if result.get("ok"):
                print(f"[Webhook] ✅ Зарегистрирован: {webhook_url}")
                return
            print(f"[Webhook] ⚠️ Попытка {attempt}/{max_attempts}: {result.get('description')}")
        except Exception as e:
            print(f"[Webhook] ⚠️ Попытка {attempt}/{max_attempts}: {e}")
        if attempt < max_attempts:
            print(f"[Webhook] Повтор через {delay} сек...")
            time.sleep(delay)
    print(f"[Webhook] ❌ Не удалось зарегистрировать webhook за {max_attempts} попыток")


def self_ping_worker() -> None:
    """
    Фоновый поток для self-ping.
    Render усыпляет free-сервис через 15 минут.
    Пинг каждые 8 минут держит его активным.
    """
    # Ждём 15 сек, чтобы Flask стартовал
    time.sleep(15)
    _set_webhook_with_retry(max_attempts=5, delay=30)

    # Дополнительная пауза перед началом пингов (cold start)
    time.sleep(30)

    ping_interval = 8 * 60  # 8 минут — безопаснее чем 10

    while True:
        try:
            if RENDER_EXTERNAL_URL:
                resp = requests.get(
                    f"{RENDER_EXTERNAL_URL}/health",
                    timeout=90,  # cold start может занять 60+ сек
                    headers={"User-Agent": "SelfPing/1.0"},
                )
                if resp.status_code == 200:
                    print(f"[Keep-Alive] ✅ Self-ping OK")
                else:
                    print(f"[Keep-Alive] ⚠️ HTTP {resp.status_code}")
        except Exception as e:
            print(f"[Keep-Alive] ❌ {e}")

        time.sleep(ping_interval)


if RENDER_EXTERNAL_URL:
    threading.Thread(target=self_ping_worker, daemon=True).start()
    print(f"[Keep-Alive] 🚀 Self-ping запущен для {RENDER_EXTERNAL_URL}")


# ============================================
# ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ (в памяти; снапшот в users.json делает GitHub Actions)
# ============================================

USERS_SNAPSHOT_URL = "https://raw.githubusercontent.com/glcskl/tg2/main/users.json"

_users_lock = threading.Lock()
_known_users = set()


def _load_known_users() -> None:
    """При старте подгружаем ранее сохранённых пользователей из репозитория."""
    global _known_users
    try:
        resp = requests.get(USERS_SNAPSHOT_URL, timeout=15)
        if resp.status_code == 200:
            with _users_lock:
                _known_users = set(resp.json())
        print(f"[Users] 📂 Загружено пользователей: {len(_known_users)}")
    except Exception as e:
        print(f"[Users] ⚠️ Не удалось загрузить users.json: {e}")


_load_known_users()


def record_user(chat_id) -> None:
    if chat_id is None:
        return
    with _users_lock:
        if chat_id in _known_users:
            return
        _known_users.add(int(chat_id))
    print(f"[Users] ➕ Новый пользователь: {chat_id} (всего: {len(_known_users)})")


# ============================================
# ДАННЫЕ БОТА
# ============================================

DAYS = [("пн", "ПН"), ("вт", "ВТ"), ("ср", "СР"), ("чт", "ЧТ"), ("пт", "ПТ")]
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


def schedule_path() -> str:
    return os.path.join(BASE_DIR, "schedule.json")


def load_schedule() -> dict:
    with open(schedule_path(), "r", encoding="utf-8") as f:
        return json.load(f)


def session_path() -> str:
    return os.path.join(BASE_DIR, "session.json")


def load_session() -> dict:
    with open(session_path(), "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================
# КЛАВИАТУРЫ
# ============================================

def main_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📅 Расписание", "callback_data": "schedule"},
            ],
            [
                {"text": "📝 Экзамены", "callback_data": "exams"},
                {"text": "✅ Зачёты", "callback_data": "credits"},
            ],
            [
                {"text": "📋 Вся сессия", "callback_data": "session"},
            ],
        ]
    }


def week_keyboard() -> dict:
    """Выбор недели: текущая, следующая или конкретный числитель/знаменатель."""
    current = get_current_week()
    return {
        "inline_keyboard": [
            [{"text": f"📍 Текущая ({current})", "callback_data": "week:auto"}],
            [{"text": f"➡️ Следующая ({other_week(current)})", "callback_data": "week:next"}],
            [
                {"text": "Числитель", "callback_data": "week:числитель"},
                {"text": "Знаменатель", "callback_data": "week:знаменатель"},
            ],
            [{"text": "🔙 В меню", "callback_data": "back"}],
        ]
    }


def week_menu_text() -> str:
    return (
        f"📅 *Расписание занятий*\n"
        f"📍 Сейчас: *{get_current_week()}*\n\n"
        "Выбери неделю 👇"
    )


def day_keyboard(week: Optional[str] = None) -> dict:
    week = week or get_current_week()
    days_row = [
        {"text": title, "callback_data": f"day:{week}:{key}"}
        for key, title in DAYS
    ]
    back_row = [
        {"text": "🗓 Выбрать неделю", "callback_data": "weeks"},
        {"text": "🔙 В меню", "callback_data": "back"},
    ]
    return {"inline_keyboard": [days_row, back_row]}


def back_keyboard() -> dict:
    return {
        "inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back"}]]
    }


# ============================================
# ФОРМАТИРОВАНИЕ
# ============================================

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

    header = f"🏛️ *{day_name.upper()}*\n📐 Неделя: *{week}*\n"
    if not items:
        return header + "\n\n✅ Нет пар"

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
            title = f"{subject} ({kind})"

        block = [f"{num}️⃣ ⏰ *{time}*\n   📚 {title}"]
        if teacher:
            block.append(f"   👤 {teacher}")
        if room:
            block.append(f"   🏫 {room}")

        lines.append("\n".join(block))

    return "\n\n".join(lines).strip()


# Виды аттестации для кнопок меню
EXAM_KINDS = {"Э", "ЭКЗ."}
CREDIT_KINDS = {"зчО.", "зч."}

# Иконки видов аттестации в сессии
KIND_ICONS = {
    "КР": "📄",
    "КП": "📐",
    "зчО.": "✅",
    "зч.": "✅",
    "Э": "🎯",
    "ЭКЗ.": "🎯",
}


def format_session(
    session: dict,
    kinds=None,
    title: Optional[str] = None,
    empty_text: Optional[str] = None,
) -> str:
    """Собирает список сессии: события сгруппированы по датам.

    kinds — фильтр по виду аттестации (экзамены, зачёты, вся сессия).
    """
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
        "exams": (
            EXAM_KINDS,
            f"📝 <b>Экзамены {group}</b>",
            "✅ Экзамены не найдены",
        ),
        "credits": (
            CREDIT_KINDS,
            f"✅ <b>Зачёты {group}</b>",
            "✅ Зачёты не найдены",
        ),
    }

    if view in views:
        kinds, title, empty_text = views[view]
        return format_session(session, kinds=kinds, title=title, empty_text=empty_text)

    return format_session(session, title=f"📋 <b>Вся сессия {group}</b>")


# ============================================
# TELEGRAM API
# ============================================

def tg_request(method: str, params: dict) -> dict:
    """Вспомогательная функция для вызова Telegram Bot API."""
    url = TELEGRAM_API_URL + method
    resp = requests.post(url, json=params, timeout=10)
    try:
        return resp.json()
    except Exception:
        return {}


# Последнее сообщение бота в чате (для самоочистки при новом /start)
_last_bot_message = {}


def _remember_message(chat_id, resp) -> None:
    try:
        if isinstance(resp, dict) and resp.get("ok"):
            _last_bot_message[chat_id] = resp["result"]["message_id"]
    except Exception:
        pass


def _cleanup_previous(chat_id) -> None:
    """Удаляем предыдущее сообщение бота в этом чате, если знаем его id."""
    message_id = _last_bot_message.pop(chat_id, None)
    if message_id:
        tg_request("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def handle_message(message: dict) -> None:
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    record_user(chat_id)

    if text in ("/start", "start"):
        _cleanup_previous(chat_id)

        week = get_current_week()
        resp = tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": f"👋 Привет!\n📅 Текущая неделя: *{week}*\n\nВыбери действие 👇",
                "parse_mode": "Markdown",
                "reply_markup": main_keyboard(),
            },
        )
        _remember_message(chat_id, resp)
    else:
        tg_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": "Напиши /start чтобы открыть меню 🙂",
            },
        )


def handle_callback_query(callback_query: dict) -> None:
    data = callback_query.get("data") or ""
    message = callback_query.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    callback_id = callback_query.get("id")

    if not (chat_id and message_id and callback_id):
        return

    record_user(chat_id)

    # Кнопка "Назад"
    if data == "back":
        week = get_current_week()
        tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": f"👋 Привет!\n📅 Текущая неделя: *{week}*\n\nВыбери действие 👇",
                "parse_mode": "Markdown",
                "reply_markup": main_keyboard(),
            },
        )
        tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    # Кнопка "Расписание" — сначала выбираем неделю
    if data in ("schedule", "weeks"):
        tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": week_menu_text(),
                "parse_mode": "Markdown",
                "reply_markup": week_keyboard(),
            },
        )
        tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    # Выбор недели: текущая, следующая или конкретный числитель/знаменатель
    if data.startswith("week:"):
        choice = data.split(":", 1)[1]
        current = get_current_week()

        if choice == "auto":
            week = current
        elif choice == "next":
            week = other_week(current)
        elif choice in WEEKS:
            week = choice
        else:
            tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
            return

        tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": f"📅 *Расписание занятий*\n📐 Неделя: *{week}*\n\nВыбери день 👇",
                "parse_mode": "Markdown",
                "reply_markup": day_keyboard(week),
            },
        )
        tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    # Кнопки "Экзамены", "Зачёты" и "Вся сессия"
    if data in ("exams", "credits", "session"):
        tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": session_view(data),
                "parse_mode": "HTML",
                "reply_markup": back_keyboard(),
            },
        )
        tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    # Выбор дня (новый формат: day:<неделя>:<день>, старый: day:<день>)
    if data.startswith("day:"):
        parts = data.split(":")
        if len(parts) == 3:
            week, day = parts[1], parts[2]
        else:
            week, day = get_current_week(), parts[1]
        if week not in WEEKS:
            week = get_current_week()

        schedule = load_schedule()
        text = format_day(schedule, week, day)

        tg_request(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "Markdown",
                "reply_markup": day_keyboard(week),
            },
        )
        tg_request("answerCallbackQuery", {"callback_query_id": callback_id})
        return

    # На всякий случай отвечаем на любой другой callback
    tg_request("answerCallbackQuery", {"callback_query_id": callback_id})


def handle_update(update: dict) -> None:
    """Роутер для входящих апдейтов Telegram."""
    if "message" in update:
        handle_message(update["message"])
    elif "callback_query" in update:
        handle_callback_query(update["callback_query"])


# ============================================
# ROUTES
# ============================================

@app.get("/")
def index():
    return "Bot is running."


@app.get("/health")
def health():
    """Health check endpoint для мониторинга и self-ping."""
    try:
        session_items = len(load_session().get("items") or [])
    except Exception:
        session_items = 0

    return {
        "status": "ok",
        "service": "tg2-schedule-bot",
        "timestamp": datetime.now().isoformat(),
        "self_ping_enabled": bool(RENDER_EXTERNAL_URL),
        "known_users": len(_known_users),
        "session_items": session_items,
    }


@app.get("/users")
def users_dump():
    """Выгружает список пользователей (для синхронизации GitHub Actions)."""
    if request.args.get("key") != BOT_TOKEN:
        return {"error": "unauthorized"}, 401
    with _users_lock:
        return sorted(_known_users)


@app.post(f"/webhook/{BOT_TOKEN}")
def telegram_webhook():
    update = request.get_json(force=True, silent=True) or {}
    handle_update(update)
    # Telegram достаточно кода 200 без тела
    return "", 200


if __name__ == "__main__":
    # Локальный запуск для отладки (например, через ngrok)
    app.run(host="0.0.0.0", port=8000, debug=True)