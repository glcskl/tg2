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
    get_current_week,
    load_schedule,
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


def test_schedule_json_is_valid_utf8_json():
    with open(web_app.schedule_path(), encoding="utf-8") as handle:
        data = json.load(handle)

    assert "числитель" in data and "знаменатель" in data
