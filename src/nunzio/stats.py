"""Pure statistics helpers shared by stats handlers and coaching context.

No DB or LLM dependencies — operates on plain date lists so it can be reused
without risking import cycles between core.py and llm/context.py.
"""

from datetime import date as date_type, timedelta


def compute_consistency(
    dates_90: list, dates_30: list, today: date_type | None = None
) -> dict:
    """Compute consistency metrics from workout date lists.

    Returns dict with count_30d, count_90d, avg_gap, streak, days_since_last.
    `today` should be the user's local date; falls back to the server-local date.
    """
    if today is None:
        today = date_type.today()
    count_30d = len(dates_30)
    count_90d = len(dates_90)

    avg_gap = None
    if count_90d >= 2:
        sorted_dates = sorted(dates_90)
        gaps = [
            (sorted_dates[i + 1] - sorted_dates[i]).days
            for i in range(len(sorted_dates) - 1)
        ]
        avg_gap = sum(gaps) / len(gaps)

    # Current streak: count consecutive days working backwards from today
    streak = 0
    if dates_90:
        sorted_dates = sorted(dates_90, reverse=True)
        expected = today
        for d in sorted_dates:
            if d == expected:
                streak += 1
                expected = expected - timedelta(days=1)
            elif d < expected:
                break

    days_since_last = (today - max(dates_90)).days if dates_90 else None

    return {
        "count_30d": count_30d,
        "count_90d": count_90d,
        "avg_gap": avg_gap,
        "streak": streak,
        "days_since_last": days_since_last,
    }
