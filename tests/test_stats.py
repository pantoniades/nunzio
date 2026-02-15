"""Tests for stats sub-handlers — consistency computation and helpers."""

from datetime import date, timedelta

from nunzio.core import MessageHandler


TODAY = date.today()


def test_consistency_no_workouts():
    result = MessageHandler._compute_consistency([], [])
    assert result["count_30d"] == 0
    assert result["count_90d"] == 0
    assert result["avg_gap"] is None
    assert result["streak"] == 0
    assert result["days_since_last"] is None


def test_consistency_single_workout_today():
    dates_90 = [TODAY]
    dates_30 = [TODAY]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["count_30d"] == 1
    assert result["count_90d"] == 1
    assert result["avg_gap"] is None  # need >=2 for avg
    assert result["streak"] == 1
    assert result["days_since_last"] == 0


def test_consistency_streak():
    dates_90 = [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=2)]
    dates_30 = dates_90[:]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["streak"] == 3
    assert result["avg_gap"] == 1.0


def test_consistency_broken_streak():
    """Streak broken by a gap — only count consecutive days from today."""
    dates_90 = [TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=5)]
    dates_30 = dates_90[:]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["streak"] == 2  # today + yesterday, then gap


def test_consistency_no_streak_last_workout_days_ago():
    dates_90 = [TODAY - timedelta(days=3)]
    dates_30 = dates_90[:]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["streak"] == 0
    assert result["days_since_last"] == 3


def test_consistency_avg_gap():
    # Workouts every 3 days
    dates_90 = [TODAY - timedelta(days=i * 3) for i in range(5)]
    dates_30 = [d for d in dates_90 if (TODAY - d).days <= 30]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["avg_gap"] == 3.0
    assert result["count_90d"] == 5


def test_consistency_30_vs_90_split():
    dates_90 = [TODAY - timedelta(days=i * 10) for i in range(9)]
    dates_30 = [d for d in dates_90 if (TODAY - d).days <= 30]
    result = MessageHandler._compute_consistency(dates_90, dates_30)
    assert result["count_30d"] == len(dates_30)
    assert result["count_90d"] == 9
