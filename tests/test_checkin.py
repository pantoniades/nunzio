"""Unit tests for proactive check-in trigger logic — pure, no DB/LLM/clock."""

from datetime import date

from nunzio.checkin import consistency_trigger
from nunzio.llm.context import rank_lagging_groups

TODAY = date(2026, 7, 13)


def _stats(*, streak=0, days_since_last=None, avg_gap=None):
    return {
        "count_30d": 0,
        "count_90d": 0,
        "avg_gap": avg_gap,
        "streak": streak,
        "days_since_last": days_since_last,
    }


def test_streak_milestone_triggers():
    kind, ref, msg = consistency_trigger(_stats(streak=7), TODAY, None)
    assert kind == "streak"
    assert ref == "streak:7"
    assert "7-day" in msg


def test_non_milestone_streak_no_trigger():
    assert consistency_trigger(_stats(streak=4, days_since_last=0), TODAY, None) is None


def test_nudge_when_overdue_includes_focus():
    kind, ref, msg = consistency_trigger(
        _stats(days_since_last=8, avg_gap=3.0), TODAY, "legs"
    )
    assert kind == "nudge"
    assert ref == f"nudge:{TODAY.isoformat()}"
    assert "8 days" in msg
    assert "legs" in msg


def test_no_nudge_when_recent():
    assert consistency_trigger(_stats(days_since_last=2, avg_gap=3.0), TODAY, None) is None


def test_no_nudge_within_normal_gap():
    # gap 4 days vs avg 3.5 → 4 <= 3.5 * 1.5, not overdue.
    assert consistency_trigger(_stats(days_since_last=4, avg_gap=3.5), TODAY, None) is None


def test_nudge_without_history_avg():
    kind, _ref, msg = consistency_trigger(
        _stats(days_since_last=10, avg_gap=None), TODAY, None
    )
    assert kind == "nudge"
    assert "could use some attention" not in msg  # no focus supplied


def test_rank_lagging_groups_orders_by_volume():
    ranked, untrained = rank_lagging_groups({"chest": 5000, "back": 2000, "legs": 8000})
    assert ranked[0][0] == "back"  # lowest volume first
    assert ranked[-1][0] == "legs"
    assert "shoulders" in untrained
    assert "biceps" in untrained


def test_rank_lagging_groups_all_untrained():
    ranked, untrained = rank_lagging_groups({})
    assert ranked == []
    assert "chest" in untrained
