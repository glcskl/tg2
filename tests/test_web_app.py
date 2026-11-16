import json
from datetime import datetime

import pytest

import web_app
from web_app import (
    BOT_TOKEN,
    DAYS,
    PAIR_BY_START,
    app,
    day_keyboard,
    format_day,
    format_session,
    get_current_week,
    load_schedule,
    load_session,
    main_keyboard,
)


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.data == b"Bot is running."


def test_health_payload(client):
    response = client.get("/health")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "tg2-schedule-bot"
    assert payload["self_ping_enabled"] is False
    assert isinstance(payload["known_users"], int)
    assert payload["session_items"] == len(load_session()["items"])
    datetime.fromisoformat(payload["timestamp"])


def test_users_requires_key(client):
    assert client.get("/users").status_code == 401
    assert client.get("/users?key=nope").get_json() == {"error": "unauthorized"}


def test_users_dump_returns_sorted_known_users(client):
    web_app.record_user(900)
    web_app.record_user(100)

    response = client.get(f"/users?key={BOT_TOKEN}")

    assert response.status_code == 200
    assert response.get_json() == [100, 900]


def test_webhook_accepts_empty_update(client):
    assert client.post(f"/webhook/{BOT_TOKEN}", json={}).status_code == 200


def _freeze(monkeypatch, moment):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(web_app, "datetime", FixedDatetime)


@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2026, 10, 30, 12, 0), "числитель"),   # пятница, 44-я неделя
        (datetime(2026, 10, 31, 12, 0), "знаменатель"),  # суббота — уже 45-я
        (datetime(2026, 11, 1, 12, 0), "знаменатель"),   # воскресенье — 45-я
        (datetime(2026, 11, 2, 9, 0), "знаменатель"),    # понедельник 45-й
        (datetime(2026, 10, 26, 9, 0), "числитель"),     # понедельник 44-й
    ],
)
def test_current_week_rolls_over_on_weekend(monkeypatch, moment, expected):
    _freeze(monkeypatch, moment)

    assert get_current_week() == expected


def test_schedule_file_covers_both_weeks_and_weekdays():
    schedule = load_schedule()

    assert set(schedule) == {"числитель", "знаменатель"}
    for week in schedule.values():
        assert set(week) == {key for key, _ in DAYS}


def test_format_day_numbers_pairs_by_start_time():
    schedule = {
        "числитель": {
            "пн": [
                {"time": "10:45-12:15", "subject": "Базы данных", "kind": "лк", "teacher": "Иванов И.И.", "room": "101"},
                {"time": "09:00-10:30", "subject": "Физика", "kind": "лб", "teacher": "", "room": ""},
            ]
        }
    }

    text = format_day(schedule, "числитель", "пн")

    assert "🏛️ *ПН*" in text
    assert "2️⃣ ⏰ *10:45-12:15*" in text
    assert "1️⃣ ⏰ *09:00-10:30*" in text
    assert "Базы данных (лк)" in text
    assert "👤 Иванов И.И." in text


def test_format_day_empty_day_says_no_classes():
    assert format_day({}, "числитель", "чт") == "🏛️ *ЧТ*\n📐 Неделя: *числитель*\n\n\n✅ Нет пар"


def test_pair_by_start_is_ordered():
    assert list(PAIR_BY_START.values()) == [1, 2, 3, 4, 5, 6, 7]
    assert list(PAIR_BY_START) == sorted(PAIR_BY_START)


def test_keyboards_structure():
    assert main_keyboard()["inline_keyboard"][0][0]["callback_data"] == "schedule"

    day_rows = day_keyboard()["inline_keyboard"]
    assert [button["callback_data"] for button in day_rows[0]] == [f"day:{key}" for key, _ in DAYS]
    assert day_rows[1][0]["callback_data"] == "back"


def test_main_keyboard_has_exams_button():
    buttons = [button for row in main_keyboard()["inline_keyboard"] for button in row]

    assert [button["callback_data"] for button in buttons] == ["schedule", "exams"]
    assert "Экзамены" in buttons[1]["text"]


def test_session_json_is_valid_and_sorted():
    session = load_session()

    assert session["group"] == "3-Аб-5"
    assert session["items"]

    for item in session["items"]:
        assert {"date", "weekday", "pair", "time", "subject", "kind"} <= set(item)

    keys = [
        (int(item["date"][6:]), int(item["date"][3:5]), int(item["date"][:2]), item["pair"])
        for item in session["items"]
    ]
    assert keys == sorted(keys)


def test_format_session_groups_items_by_date():
    session = {
        "group": "3-Аб-5",
        "semester": "осенний семестр 2026/2027",
        "source": "https://rasp.spbgasu.ru/sessia",
        "updated": "2026-11-16",
        "items": [
            {
                "date": "28.12.2026",
                "weekday": "понедельник",
                "pair": 3,
                "time": "12:30-14:00",
                "subject": "Благоустройство",
                "kind": "КР",
                "teacher": "Шестеров Е.А.",
                "room": "316/А",
            },
            {
                "date": "28.12.2026",
                "weekday": "понедельник",
                "pair": 4,
                "time": "15:00-16:30",
                "subject": "Благоустройство",
                "kind": "зчО.",
                "teacher": "Веретенникова К.В.",
                "room": "314/А",
            },
        ],
    }

    text = format_session(session)

    assert text.count("<b>28.12.2026, понедельник</b>") == 1
    assert "3️⃣ ⏰ <b>12:30-14:00</b>" in text
    assert "4️⃣ ⏰ <b>15:00-16:30</b>" in text
    assert "Благоустройство (КР)" in text
    assert "Благоустройство (зчО.)" in text
    assert "👤 Веретенникова К.В." in text
    assert "🏫 314/А" in text
    assert "Экзаменов (Э) нет" in text
    assert "Источник" in text


def test_format_session_escapes_html_and_drops_exam_note():
    session = {
        "group": "3-Аб-5",
        "items": [
            {
                "date": "10.01.2027",
                "weekday": "воскресенье",
                "pair": 1,
                "time": "09:00-10:30",
                "subject": "A & B <C>",
                "kind": "Э",
                "teacher": "",
                "room": "425*/Г",
            }
        ],
    }

    text = format_session(session)

    assert "A &amp; B &lt;C&gt;" in text
    assert "425*/Г" in text
    assert "Экзаменов (Э) нет" not in text


def test_format_session_without_items():
    text = format_session({"group": "3-Аб-5"})

    assert "Сессия 3-Аб-5" in text
    assert "пока не опубликовано" in text


def test_schedule_json_is_valid_utf8_json():
    with open(web_app.schedule_path(), encoding="utf-8") as handle:
        data = json.load(handle)

    assert "числитель" in data and "знаменатель" in data
