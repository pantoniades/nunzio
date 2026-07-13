"""Proactive check-ins: Nunzio reaches out unprompted via Telegram.

Runs as an in-process job scheduled by the bot's PTB JobQueue (see bot.py). Once
per hour it picks the users whose local time is around the morning check-in hour,
computes the single highest-priority trigger for each (a fresh PR, a streak
milestone, or an inactivity nudge with a suggested focus), and sends one message —
deduped through the `proactive_log` table so the same event is never sent twice.

The trigger computation (`compute_checkin`) is pure of I/O beyond the DB session and
takes `today` explicitly, so it can be unit-tested without patching the clock.
"""

import logging
from datetime import date as date_type, datetime

from .database.connection import db_manager
from .database.models import now_in_tz
from .database.repository import (
    proactive_log_repo,
    user_settings_repo,
    workout_set_repo,
)
from .llm.context import MAIN_GROUPS
from .stats import compute_consistency

logger = logging.getLogger(__name__)

# Local hour (24h) at which a user's daily check-in may fire. The job runs hourly
# and only acts for users whose local time is currently this hour.
CHECKIN_HOUR = 9

# Streak lengths worth celebrating (avoids congratulating every single day).
_STREAK_MILESTONES = {3, 5, 7, 10, 14, 21, 30, 50, 100}

# Only nudge once the gap is both meaningfully long and well past the user's norm.
_MIN_NUDGE_DAYS = 3
_NUDGE_GAP_FACTOR = 1.5


def _as_date(value) -> date_type:
    return value.date() if isinstance(value, datetime) else value


async def _suggest_focus(session, user_id: int) -> str | None:
    """Name the resistance group most in need of work (untrained, else lowest volume)."""
    rows = await workout_set_repo.get_weekly_volume(session, user_id, weeks=4)
    vol: dict[str, float] = {}
    for _yw, mg, v in rows:
        vol[mg] = vol.get(mg, 0.0) + (v or 0.0)
    for g in MAIN_GROUPS:  # an entirely untrained main group wins
        if g not in vol:
            return g
    ranked = sorted(
        ((g, v) for g, v in vol.items() if g in MAIN_GROUPS), key=lambda x: x[1]
    )
    return ranked[0][0] if ranked else None


async def compute_checkin(
    session, user_id: int, today: date_type
) -> tuple[str, str, str] | None:
    """Return (kind, ref_key, message) for the top-priority check-in, or None.

    Priority: a PR logged in the last day > a streak milestone > an inactivity nudge.
    """
    # 1. Fresh PR — congratulate a personal record set on today or yesterday.
    prs = await workout_set_repo.get_all_prs(session, user_id)
    for pr in prs:
        if pr.weight is None:
            continue
        if (today - _as_date(pr.set_date)).days <= 1:
            name = pr.exercise.name if pr.exercise else "that lift"
            reps = f" x {pr.reps}" if pr.reps else ""
            ref = f"pr:{pr.exercise_id}:{pr.weight:g}"
            msg = (
                f"Caught that PR on {name} — {pr.weight:g} {pr.weight_unit}{reps}. "
                f"Strong work. 💪"
            )
            return ("pr", ref, msg)

    # 2 & 3. Consistency-based triggers.
    dates_90 = await workout_set_repo.get_workout_dates(session, user_id, days=90)
    if not dates_90:
        return None
    dates_30 = [d for d in dates_90 if (today - d).days <= 30]
    stats = compute_consistency(dates_90, dates_30, today)

    # A focus suggestion is only needed for the nudge branch; compute lazily.
    if _nudge_due(stats):
        focus = await _suggest_focus(session, user_id)
    else:
        focus = None
    return consistency_trigger(stats, today, focus)


def _nudge_due(stats: dict) -> bool:
    dsl = stats["days_since_last"]
    avg = stats["avg_gap"]
    return (
        stats["streak"] not in _STREAK_MILESTONES
        and dsl is not None
        and dsl >= _MIN_NUDGE_DAYS
        and (avg is None or dsl > avg * _NUDGE_GAP_FACTOR)
    )


def consistency_trigger(
    stats: dict, today: date_type, focus_group: str | None
) -> tuple[str, str, str] | None:
    """Pure streak/nudge decision from consistency stats (unit-testable, no I/O)."""
    streak = stats["streak"]
    if streak in _STREAK_MILESTONES:
        return (
            "streak",
            f"streak:{streak}",
            f"{streak}-day streak and counting — you're on a roll. Keep it going.",
        )

    if _nudge_due(stats):
        dsl = stats["days_since_last"]
        focus_line = f" Your {focus_group} could use some attention." if focus_group else ""
        return (
            "nudge",
            f"nudge:{today.isoformat()}",
            f"It's been {dsl} days since your last session.{focus_line} "
            f"What are you up for today?",
        )

    return None


async def run_checkins(bot, user_ids) -> int:
    """Compute and send at most one check-in per user (whose local time is CHECKIN_HOUR).

    `bot` is a telegram.Bot (or PTB context.bot) exposing async send_message.
    Returns the number of messages actually sent.
    """
    sent = 0
    for user_id in user_ids:
        try:
            async with db_manager.get_session() as session:
                tz = await user_settings_repo.get_timezone(session, user_id)
                local_now = now_in_tz(tz)
                if local_now.hour != CHECKIN_HOUR:
                    continue
                result = await compute_checkin(session, user_id, local_now.date())
                if not result:
                    continue
                kind, ref_key, message = result
                if await proactive_log_repo.already_sent(session, user_id, kind, ref_key):
                    continue

            await bot.send_message(chat_id=user_id, text=message)

            async with db_manager.get_session() as session:
                await proactive_log_repo.create(
                    session,
                    obj_in={"user_id": user_id, "kind": kind, "ref_key": ref_key},
                )
            sent += 1
            logger.info("Sent %s check-in to %s", kind, user_id)
        except Exception:
            logger.warning("Check-in for user %s failed", user_id, exc_info=True)
            continue
    return sent
