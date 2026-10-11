"""Unit tests for the YOUR EXERCISES coaching roster — pure, no DB/LLM."""

from datetime import datetime
from types import SimpleNamespace

from nunzio.llm.context import summarize_roster


def _ws(ex_id, name, day, set_number, reps, weight, unit="lbs", batch=1, duration=None):
    return SimpleNamespace(
        exercise_id=ex_id,
        exercise=SimpleNamespace(name=name),
        set_date=datetime(2026, 10, day, 17, set_number),
        batch_id=batch,
        set_number=set_number,
        reps=reps,
        weight=weight,
        weight_unit=unit,
        duration_minutes=duration,
    )


def test_empty_roster():
    assert summarize_roster([]) == ""


def test_last_session_sets_in_order_and_session_count():
    # newest-first, as the repo returns them
    sets = [
        _ws(1, "Bench Press", 9, 1, 10, 60, batch=4),
        _ws(1, "Bench Press", 9, 1, 10, 55, batch=3),
        _ws(1, "Bench Press", 9, 1, 10, 45, batch=2),
        _ws(1, "Bench Press", 1, 1, 12, 55, batch=1),
    ]
    out = summarize_roster(sets)
    assert "- Bench Press: last Oct 09: 10x45, 10x55, 10x60 lbs (2 sessions)" in out
    assert "12x55" not in out  # older session not shown


def test_most_recent_exercise_first_and_bodyweight():
    sets = [
        _ws(2, "Band Pull Apart", 9, 1, 12, None),
        _ws(1, "Low Row", 5, 1, 12, 55),
    ]
    lines = summarize_roster(sets).splitlines()
    assert lines[1].startswith("- Band Pull Apart: last Oct 09: 12 ")
    assert lines[2].startswith("- Low Row:")


def test_kg_unit_preserved():
    out = summarize_roster([_ws(3, "Shoulder Press", 9, 1, 10, 20, unit="kg")])
    assert "10x20 kg" in out
