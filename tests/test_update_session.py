import json
import os
import sys

import pytest

import update_session
from update_session import BELLS, GROUP, build_session, describe_semester, split_lesson


def lesson(
    date="21.12.2026",
    weekday="ПОНЕДЕЛЬНИК",
    pair="6",
    subject="Рабочее проектирование жилых зданий (КР)",
    teacher="Кокорина О.Г.",
    room="509/А",
    groups=(GROUP,),
):
    return {
        "S": {
            date: {
                "WEEK_DAY": weekday,
                "PARS": {
                    pair: {
                        "LESSON": subject,
                        "DATE": date,
                        "GROUP": list(groups),
                        "PROFESSOR": [teacher] if teacher else [],
                        "AUDITORIUM": [room] if room else [],
                    }
                },
            }
        }
    }


def test_split_lesson_extracts_known_kind():
    assert split_lesson("Организация строительства (КР)") == ("Организация строительства", "КР")
    assert split_lesson("Инженерные системы (зчО.)") == ("Инженерные системы", "зчО.")


def test_split_lesson_normalizes_exam_kinds():
    assert split_lesson("Организация и управление (экз.)") == (
        "Организация и управление",
        "ЭКЗ.",
    )
    assert split_lesson("Предпроектные исследования (ЭКЗ.)") == (
        "Предпроектные исследования",
        "ЭКЗ.",
    )
    assert split_lesson("Экзамен (Э)") == ("Экзамен", "ЭКЗ.")


def test_split_lesson_keeps_unknown_suffix_in_subject():
    assert split_lesson("Семинар (нечто)") == ("Семинар (нечто)", "")
    assert split_lesson("Без скобок") == ("Без скобок", "")


def test_build_session_maps_fields_and_time():
    session = build_session(lesson())

    item = session["items"][0]
    assert item["date"] == "21.12.2026"
    assert item["weekday"] == "понедельник"
    assert item["pair"] == 6
    assert item["time"] == BELLS[6]
    assert item["subject"] == "Рабочее проектирование жилых зданий"
    assert item["kind"] == "КР"
    assert item["teacher"] == "Кокорина О.Г."
    assert item["room"] == "509/А"


def test_build_session_ignores_other_groups():
    session = build_session(lesson(groups=("3-Аб-6",)))

    assert session["items"] == []


def test_build_session_sorts_by_date_and_pair():
    payload = lesson()
    payload["S"]["28.12.2026"] = {
        "WEEK_DAY": "ПОНЕДЕЛЬНИК",
        "PARS": {
            "4": {"LESSON": "Благоустройство (зчО.)", "GROUP": [GROUP], "PROFESSOR": [], "AUDITORIUM": []},
            "3": {"LESSON": "Благоустройство (КР)", "GROUP": [GROUP], "PROFESSOR": [], "AUDITORIUM": []},
        },
    }

    items = build_session(payload)["items"]

    assert [(item["date"], item["pair"]) for item in items] == [
        ("21.12.2026", 6),
        ("28.12.2026", 3),
        ("28.12.2026", 4),
    ]


@pytest.mark.parametrize(
    "date, weekday",
    [("21.12.2026", "понедельник"), ("26.12.2026", "суббота")],
)
def test_weekday_is_translated_from_caps(date, weekday):
    raw = "ПОНЕДЕЛЬНИК" if weekday == "понедельник" else "СУББОТА"

    session = build_session(lesson(date=date, weekday=raw))

    assert session["items"][0]["weekday"] == weekday


def test_describe_semester_detects_autumn_and_spring():
    assert describe_semester([{"date": "21.12.2026"}]) == "осенний семестр 2026/2027"
    assert describe_semester([{"date": "15.06.2027"}]) == "весенний семестр 2026/2027"
    assert describe_semester([]) == ""


def test_build_session_metadata():
    session = build_session(lesson())

    assert session["group"] == GROUP
    assert session["source"].startswith("https://rasp.spbgasu.ru")


def test_main_writes_session_json(monkeypatch, tmp_path):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(lesson(), ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(update_session, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["update_session.py", str(payload_path)])

    update_session.main()

    written = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert written["group"] == GROUP
    assert written["items"][0]["subject"] == "Рабочее проектирование жилых зданий"


def test_session_json_in_repo_matches_builder_contract():
    with open(os.path.join(update_session.BASE_DIR, "session.json"), encoding="utf-8") as handle:
        session = json.load(handle)

    assert session["group"] == GROUP
    assert isinstance(session["items"], list)
    for item in session["items"]:
        assert {"date", "weekday", "pair", "time", "subject", "kind", "teacher", "room"} <= set(item)
    assert {item["kind"] for item in session["items"]} >= {"КР", "КП", "зчО.", "ЭКЗ."}
