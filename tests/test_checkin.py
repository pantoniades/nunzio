"""Unit tests for proactive check-in trigger logic — pure, no DB/LLM/clock."""

from datetime import date

from datetime import timedelta

from nunzio.checkin import consistency_trigger, nudge_interval_days
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


def test_no_nudge_day_after_previous_nudge():
    """Nudges never fire on consecutive days."""
    yesterday = date(2026, 7, 12)
    assert consistency_trigger(
        _stats(days_since_last=8, avg_gap=3.0), TODAY, None, last_nudge=yesterday
    ) is None


def test_nudge_every_other_day():
    two_days_ago = date(2026, 7, 11)
    kind, _ref, _msg = consistency_trigger(
        _stats(days_since_last=8, avg_gap=3.0), TODAY, None, last_nudge=two_days_ago
    )
    assert kind == "nudge"


def test_streak_not_blocked_by_recent_nudge():
    kind, _ref, _msg = consistency_trigger(
        _stats(streak=3), TODAY, None, last_nudge=TODAY
    )
    assert kind == "streak"


# --- v0.10: backoff and pause ---

def test_nudge_interval_backs_off_but_never_stops():
    assert [nudge_interval_days(n) for n in range(7)] == [2, 2, 4, 7, 14, 30, 30]
    assert nudge_interval_days(500) == 30


def test_unanswered_nudges_thin_out():
    stats = _stats(days_since_last=20, avg_gap=3.0)

    def due(days_since_nudge: int, unanswered: int) -> bool:
        last = TODAY - timedelta(days=days_since_nudge)
        return consistency_trigger(
            stats, TODAY, None, last_nudge=last, unanswered=unanswered
        ) is not None

    assert due(2, 1)          # second nudge: still every other day
    assert not due(2, 2)      # third waits 4 days
    assert due(4, 2)
    assert not due(6, 3)      # fourth waits a week
    assert due(7, 3)
    assert not due(29, 9)     # long-ignored: monthly, but it does come
    assert due(30, 9)


def test_no_nudge_while_paused():
    stats = _stats(days_since_last=20, avg_gap=3.0)
    assert consistency_trigger(stats, TODAY, None, paused_until=TODAY) is None
    assert consistency_trigger(
        stats, TODAY, None, paused_until=TODAY + timedelta(days=3)
    ) is None
    kind, _ref, _msg = consistency_trigger(
        stats, TODAY, None, paused_until=TODAY - timedelta(days=1)
    )
    assert kind == "nudge"


def test_pause_does_not_block_streak():
    kind, _ref, _msg = consistency_trigger(
        _stats(streak=3), TODAY, None, paused_until=TODAY + timedelta(days=3)
    )
    assert kind == "streak"
