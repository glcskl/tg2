#!/usr/bin/env python3
"""Обновляет schedule.json из официального расписания СПбГАСУ.

Забирает CSV с doc.spbgasu.ru/raspisanie/ и собирает недельный
шаблон (числитель/знаменатель) для заданной группы.

Неделя 1 = числитель, неделя 2 = знаменатель и т.д. (на старте
СПбГАСУ объявляет «Начало занятий — 1 сентября, числитель»).
Если в рамках одной чётности расписание различалось по неделям,
берётся занятие последней (самой свежей) недели этой чётности.
"""

import csv
import json
import os
import sys
from collections import defaultdict
from urllib.request import urlopen

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_URL = "https://doc.spbgasu.ru/raspisanie/Raspisanie_autumn_3-6.csv"
GROUP = "3-Аб-5"

DAY_KEYS = {"1": "пн", "2": "вт", "3": "ср", "4": "чт", "5": "пт"}
DAY_ORDER = {"пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4}

# Расписание звонков СПбГАСУ (doc.spbgasu.ru/oipip_raspisanie/raspisanie_zvonkov.pdf)
BELLS = {
    1: "09:00-10:30",
    2: "10:45-12:15",
    3: "12:30-14:00",
    4: "15:00-16:30",
    5: "16:45-18:15",
    6: "18:30-20:00",
    7: "20:15-21:45",
}

TYPE_MAP = {"л.": "лк", "пр.": "пр", "лаб.": "лб", "лк.": "лк"}


def parse_schedule_rows(fh) -> list:
    rows = list(csv.reader(fh, delimiter=";"))
    return rows


def main() -> None:
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    if csv_path:
        with open(csv_path, encoding="cp1251", errors="replace") as fh:
            rows = fh.readlines()
    else:
        print(f"[Update] Скачиваю {CSV_URL} ...")
        with urlopen(CSV_URL, timeout=60) as resp:
            data = resp.read()
        rows = data.decode("cp1251", errors="replace").splitlines(keepends=True)

    rows = list(csv.reader(rows, delimiter=";"))

    # (день, чётность) -> номер пары -> [(неделя, подпись)]
    data = defaultdict(lambda: defaultdict(list))
    for r in rows[1:]:
        if len(r) <= 11 or r[0].strip() != GROUP:
            continue
        day = DAY_KEYS.get(r[2].strip())
        if not day:
            continue
        les = int(r[3].strip())
        week = int(r[5].strip())
        parity = "числитель" if week % 2 == 1 else "знаменатель"
        sig = (r[9].strip(), r[10].strip(), r[4].strip(), r[7].strip())
        data[(day, parity)][les].append((week, sig))

    result = defaultdict(lambda: defaultdict(list))
    for (day, parity), lesmap in data.items():
        for les, weeklist in sorted(lesmap.items()):
            latest_week = max(w for w, _ in weeklist)
            chosen = [sig for w, sig in weeklist if w == latest_week]
            subs = {}
            for subj, typ, aud, teacher in chosen:
                key = (subj, typ)
                subs.setdefault(key, {"subject": subj, "type": typ, "auds": set(), "teachers": set()})
                subs[key]["auds"].add(aud)
                if teacher:
                    subs[key]["teachers"].add(teacher)
            for v in subs.values():
                result[(day, parity)][les].append({
                    "time": BELLS.get(les, str(les)),
                    "kind": TYPE_MAP.get(v["type"], ""),
                    "subject": v["subject"],
                    "teacher": ", ".join(sorted(v["teachers"])) if v["teachers"] else "",
                    "room": ", ".join(sorted(v["auds"])),
                })

    schedule = {"числитель": {}, "знаменатель": {}}
    for parity in ("числитель", "знаменатель"):
        for day in ("пн", "вт", "ср", "чт", "пт"):
            lessons = []
            for les in sorted(result.get((day, parity), {})):
                lessons.extend(result[(day, parity)][les])
            schedule[parity][day] = lessons

    out_path = os.path.join(BASE_DIR, "schedule.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(schedule, fh, ensure_ascii=False, indent=2)

    total = sum(len(v) for p in schedule.values() for v in p.values())
    print(f"[Update] Готово: {GROUP}, всего пар: {total} -> {out_path}")


if __name__ == "__main__":
    main()