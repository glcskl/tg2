import json
import os
import sys

import pytest

import update_schedule
from update_schedule import BELLS, GROUP, TYPE_MAP, build_schedule


def row(
    day=1,
    lesson=1,
    week=1,
    subject="Математика",
    kind="л.",
    room="101",
    teacher="Иванов И.И.",
    group=GROUP,
):
    fields = [""] * 12
    fields[0] = group
    fields[2] = str(day)
    fields[3] = str(lesson)
    fields[4] = room
    fields[5] = str(week)
    fields[7] = teacher
    fields[9] = subject
    fields[10] = kind
    return fields


def lesson_of(schedule, parity, day="пн", index=0):
    return schedule[parity][day][index]


def test_schedule_always_has_both_parities_and_all_weekdays():
    schedule = build_schedule([])

    assert set(schedule) == {"числитель", "знаменатель"}
    for week in schedule.values():
        assert list(week) == ["пн", "вт", "ср", "чт", "пт"]
        assert all(items == [] for items in week.values())


def test_odd_week_goes_to_numerator_even_week_to_denominator():
    schedule = build_schedule([row(week=1), row(week=2, day=2)])

    assert len(schedule["числитель"]["пн"]) == 1
    assert len(schedule["знаменатель"]["вт"]) == 1


def test_other_groups_are_ignored():
    schedule = build_schedule([row(group="3-Аб-6")])

    assert schedule["числитель"]["пн"] == []


def test_unknown_weekday_and_short_rows_are_skipped():
    saturday = row(day=6)
    short = ["3-Аб-5"] * 5

    schedule = build_schedule([saturday, short])

    assert schedule["числитель"]["пн"] == []


@pytest.mark.parametrize("lesson, time", [(1, "09:00-10:30"), (3, "12:30-14:00"), (7, "20:15-21:45")])
def test_lesson_time_comes_from_bells(lesson, time):
    schedule = build_schedule([row(lesson=lesson)])

    assert lesson_of(schedule, "числитель")["time"] == time


def test_unknown_lesson_keeps_its_number_as_time():
    schedule = build_schedule([row(lesson=9)])

    assert lesson_of(schedule, "числитель")["time"] == "9"


@pytest.mark.parametrize("raw, kind", [("л.", "лк"), ("лаб.", "лб"), ("пр.", "пр"), ("лк.", "лк"), ("нечто", "")])
def test_lesson_type_is_mapped(raw, kind):
    schedule = build_schedule([row(kind=raw)])

    assert lesson_of(schedule, "числитель")["kind"] == kind
    assert set(TYPE_MAP.values()) <= {"лк", "лб", "пр"}


def test_latest_week_wins_within_the_same_parity():
    schedule = build_schedule(
        [
            row(week=1, subject="Старая тема"),
            row(week=3, subject="Новая тема"),
            row(week=5, subject="Самая свежая"),
        ]
    )

    lessons = schedule["числитель"]["пн"]
    assert [lesson["subject"] for lesson in lessons] == ["Самая свежая"]


def test_same_subject_and_type_merges_rooms_and_teachers():
    schedule = build_schedule(
        [
            row(room="101", teacher="Иванов И.И."),
            row(room="205", teacher="Петров П.П."),
            row(room="101", teacher="Петров П.П."),
        ]
    )

    lessons = schedule["числитель"]["пн"]
    assert len(lessons) == 1
    assert lessons[0]["room"] == "101, 205"
    assert lessons[0]["teacher"] == "Иванов И.И., Петров П.П."


def test_different_types_of_same_subject_stay_separate():
    schedule = build_schedule([row(kind="л."), row(kind="лаб.")])

    assert [lesson["kind"] for lesson in schedule["числитель"]["пн"]] == ["лк", "лб"]


def test_lessons_are_ordered_by_number():
    schedule = build_schedule(
        [
            row(lesson=3, subject="Третья"),
            row(lesson=1, subject="Первая"),
            row(lesson=2, subject="Вторая"),
        ]
    )

    assert [lesson["subject"] for lesson in schedule["числитель"]["пн"]] == ["Первая", "Вторая", "Третья"]


def test_missing_teacher_becomes_empty_string():
    schedule = build_schedule([row(teacher="")])

    assert lesson_of(schedule, "числитель")["teacher"] == ""


def test_all_bells_are_ordered():
    assert list(BELLS) == sorted(BELLS)
    assert list(BELLS) == list(range(1, 8))


def test_main_writes_schedule_json(monkeypatch, tmp_path):
    csv_path = tmp_path / "raspisanie.csv"
    csv_path.write_text(
        ";".join([""] * 12) + "\n" + ";".join(row(subject="Базы данных")) + "\n",
        encoding="cp1251",
    )
    monkeypatch.setattr(update_schedule, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["update_schedule.py", str(csv_path)])

    update_schedule.main()

    written = json.loads((tmp_path / "schedule.json").read_text(encoding="utf-8"))
    assert written["числитель"]["пн"][0]["subject"] == "Базы данных"


def test_schedule_json_in_repo_matches_builder_contract():
    with open(os.path.join(update_schedule.BASE_DIR, "schedule.json"), encoding="utf-8") as handle:
        schedule = json.load(handle)

    assert set(schedule) == {"числитель", "знаменатель"}
    for week in schedule.values():
        assert set(week) == {"пн", "вт", "ср", "чт", "пт"}
