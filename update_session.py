#!/usr/bin/env python3
"""Обновляет session.json из расписания сессии СПбГАСУ.

Забирает JSON с rasp.spbgasu.ru (раздел «Сессия ОФО») и собирает
плоский список событий: дата, пара, время, дисциплина, вид аттестации,
преподаватель и аудитория.

Вид аттестации берётся из подписи в скобках: (КР), (КП), (зчО.), (экз.).
"""

import json
import os
import sys
from datetime import date
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AJAX_URL = "https://rasp.spbgasu.ru/local/components/gasu/raspisanie.csv/ajax.php"
SOURCE_URL = "https://rasp.spbgasu.ru/sessia"
GROUP = "3-Аб-5"

# Расписание звонков СПбГАСУ
BELLS = {
    1: "09:00-10:30",
    2: "10:45-12:15",
    3: "12:30-14:00",
    4: "15:00-16:30",
    5: "16:45-18:15",
    6: "18:30-20:00",
    7: "20:15-21:45",
}

WEEKDAYS = {
    "ПОНЕДЕЛЬНИК": "понедельник",
    "ВТОРНИК": "вторник",
    "СРЕДА": "среда",
    "ЧЕТВЕРГ": "четверг",
    "ПЯТНИЦА": "пятница",
    "СУББОТА": "суббота",
    "ВОСКРЕСЕНЬЕ": "воскресенье",
}

# Виды аттестации, которые встречаются в расписании сессии
KINDS = {"КР", "КП", "зчО.", "зч.", "ЭКЗ."}

# Сайт пишет экзамены по-разному: (экз.), (ЭКЗ.), (Э). Приводим к одному виду.
KIND_ALIASES = {
    "экз.": "ЭКЗ.",
    "экз": "ЭКЗ.",
    "э": "ЭКЗ.",
    "зчо.": "зчО.",
}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def fetch_payload(group: str = GROUP, timeout: int = 60) -> dict:
    """Скачивает JSON сессии для группы."""
    query = urlencode(
        {
            "SERACH": group,
            "FILTER": "GROUPS",
            "GROUP": "",
            "SELECT": "*",
            "ONLY_SESSIA": "Y",
        }
    )
    request = Request(f"{AJAX_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _date_key(value: str):
    """'21.12.2026' -> (2026, 12, 21) для сортировки."""
    day, month, year = (int(part) for part in value.split("."))
    return year, month, day


def split_lesson(lesson: str):
    """'Организация строительства (КР)' -> ('Организация строительства', 'КР')."""
    text = (lesson or "").strip()
    if text.endswith(")") and "(" in text:
        subject, _, kind = text.rpartition("(")
        kind = kind[:-1].strip()
        kind = KIND_ALIASES.get(kind.casefold(), kind)
        if kind in KINDS:
            return subject.strip(), kind
    return text, ""


def describe_semester(items: list) -> str:
    """Определяет подпись семестра по датам событий."""
    if not items:
        return ""
    months = {_date_key(item["date"])[1] for item in items}
    years = {_date_key(item["date"])[0] for item in items}
    year = min(years)
    if months <= {9, 10, 11, 12}:
        return f"осенний семестр {year}/{year + 1}"
    if months <= {1, 2, 3, 4, 5, 6, 7, 8}:
        return f"весенний семестр {year - 1}/{year}"
    return f"{year}/{year + 1} учебный год"


def build_session(payload: dict, group: str = GROUP) -> dict:
    """Собирает session.json из ответа AJAX-эндпоинта."""
    days = payload.get("S") or payload.get("R") or {}
    items = []

    for date_text, day in days.items():
        weekday_raw = (day.get("WEEK_DAY") or "").strip()
        for pair_raw, lesson in (day.get("PARS") or {}).items():
            groups = lesson.get("GROUP") or []
            if groups and group not in groups:
                continue

            subject, kind = split_lesson(lesson.get("LESSON", ""))
            pair = int(pair_raw)
            items.append(
                {
                    "date": date_text.strip(),
                    "weekday": WEEKDAYS.get(weekday_raw, weekday_raw.lower()),
                    "pair": pair,
                    "time": BELLS.get(pair, ""),
                    "subject": subject,
                    "kind": kind,
                    "teacher": ", ".join(lesson.get("PROFESSOR") or []),
                    "room": ", ".join(lesson.get("AUDITORIUM") or []),
                }
            )

    items.sort(key=lambda item: (_date_key(item["date"]), item["pair"]))

    return {
        "group": group,
        "semester": describe_semester(items),
        "source": SOURCE_URL,
        "updated": date.today().isoformat(),
        "items": items,
    }


def main() -> None:
    json_path = sys.argv[1] if len(sys.argv) > 1 else None
    if json_path:
        with open(json_path, encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        print(f"[Session] Скачиваю {SOURCE_URL} ...")
        payload = fetch_payload()

    session = build_session(payload)

    out_path = os.path.join(BASE_DIR, "session.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(session, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"[Session] Готово: {GROUP}, событий: {len(session['items'])} -> {out_path}")


if __name__ == "__main__":
    main()
