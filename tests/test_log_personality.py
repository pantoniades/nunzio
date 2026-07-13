"""Tests for _generate_log_comment heuristic personality in log responses."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from nunzio.core import MessageHandler


def _ws(exercise_id, weight=None, set_date=None, **kw):
    """Create a fake WorkoutSet-like object."""
    return SimpleNamespace(
        exercise_id=exercise_id,
        weight=weight,
        set_date=set_date or datetime(2026, 2, 14, 10, 0),
        **kw,
    )


NOW = datetime(2026, 2, 14, 12, 0)


def test_pr_detected():
    logged = [{"exercise_id": 1, "name": "Bench Press", "weight": 200.0, "reps": 5, "notes": None, "is_cardio": False}]
    history = [_ws(1, weight=185.0)]
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "New PR on Bench Press!"


def test_first_time():
    logged = [{"exercise_id": 99, "name": "Dumbbell Flyes", "weight": 30.0, "reps": 10, "notes": None, "is_cardio": False}]
    history = []  # no history at all
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "First time logging Dumbbell Flyes."


def test_gap_detected():
    old_date = NOW - timedelta(days=5)
    logged = [{"exercise_id": 1, "name": "Squat", "weight": 225.0, "reps": 5, "notes": None, "is_cardio": False}]
    history = [_ws(1, weight=225.0, set_date=old_date)]
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "Back at it after 5 days."


def test_weight_increase():
    yesterday = NOW - timedelta(days=1)
    logged = [{"exercise_id": 1, "name": "Squat", "weight": 230.0, "reps": 5, "notes": None, "is_cardio": False}]
    history = [_ws(1, weight=225.0, set_date=yesterday)]
    # Not a PR since it's also a weight increase, but PR checks max_historical > 0 and max_current > max_historical
    # 230 > 225 → PR triggers first
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "New PR on Squat!"


def test_weight_increase_not_pr():
    """Weight went up vs most recent, but not a PR (historical max is higher)."""
    yesterday = NOW - timedelta(days=1)
    logged = [{"exercise_id": 1, "name": "Squat", "weight": 230.0, "reps": 5, "notes": None, "is_cardio": False}]
    history = [
        _ws(1, weight=225.0, set_date=yesterday),
        _ws(1, weight=250.0, set_date=NOW - timedelta(days=30)),
    ]
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "Moving up in weight on Squat."


def test_pain_notes():
    yesterday = NOW - timedelta(days=1)
    logged = [{"exercise_id": 1, "name": "Bench Press", "weight": 135.0, "reps": 10, "notes": "shoulder pain", "is_cardio": False}]
    history = [_ws(1, weight=135.0, set_date=yesterday)]
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "Take it easy if the pain persists."


def test_no_comment():
    """Same weight, recent session, no notes → no comment."""
    yesterday = NOW - timedelta(days=1)
    logged = [{"exercise_id": 1, "name": "Bench Press", "weight": 135.0, "reps": 10, "notes": None, "is_cardio": False}]
    history = [_ws(1, weight=135.0, set_date=yesterday)]
    assert MessageHandler._generate_log_comment(logged, history, NOW) is None


def test_pr_priority_over_weight_increase():
    """PR should fire before weight increase."""
    yesterday = NOW - timedelta(days=1)
    logged = [{"exercise_id": 1, "name": "Bench Press", "weight": 200.0, "reps": 5, "notes": None, "is_cardio": False}]
    history = [_ws(1, weight=185.0, set_date=yesterday)]
    result = MessageHandler._generate_log_comment(logged, history, NOW)
    assert result == "New PR on Bench Press!"


def test_cardio_skips_weight_checks():
    """Cardio sets shouldn't trigger weight-based comments."""
    logged = [{"exercise_id": 2, "name": "Running", "weight": None, "reps": None, "notes": None, "is_cardio": True}]
    history = []
    # First time still triggers
    assert MessageHandler._generate_log_comment(logged, history, NOW) == "First time logging Running."


def test_empty_logged_sets():
    assert MessageHandler._generate_log_comment([], [], NOW) is None


def _logged(exercise_id, name, **kw):
    base = {
        "exercise_id": exercise_id,
        "name": name,
        "set_number": 1,
        "weight": None,
        "reps": None,
        "unit": "lbs",
        "duration_minutes": None,
        "distance": None,
        "notes": None,
        "is_cardio": False,
    }
    base.update(kw)
    return base


def test_log_comment_summary_strength_with_history():
    logged = [_logged(1, "Bench Press", weight=200.0, reps=5)]
    history = [
        _ws(1, weight=185.0, reps=5, weight_unit="lbs", duration_minutes=None),
    ]
    summary = MessageHandler._log_comment_summary(
        logged, history, "New PR on Bench Press!"
    )
    assert "JUST LOGGED:" in summary
    assert "Bench Press" in summary
    assert "200" in summary
    assert "PRIOR HISTORY:" in summary
    assert "185" in summary
    assert "SIGNAL: New PR on Bench Press!" in summary


def test_log_comment_summary_first_time_has_no_prior():
    logged = [_logged(9, "Arnold Press", weight=30.0, reps=10)]
    summary = MessageHandler._log_comment_summary(
        logged, [], "First time logging Arnold Press."
    )
    assert "JUST LOGGED:" in summary
    assert "PRIOR HISTORY:" not in summary
    assert "SIGNAL: First time logging Arnold Press." in summary


def test_log_comment_summary_cardio():
    logged = [_logged(2, "Elliptical", is_cardio=True, duration_minutes=21, distance=1.44)]
    summary = MessageHandler._log_comment_summary(
        logged, [], "Back at it after 100 days."
    )
    assert "Elliptical" in summary
    assert "21 min" in summary
