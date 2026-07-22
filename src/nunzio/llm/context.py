"""Coaching context assembly — pulls history, guidance, and principles into a prompt block."""

from collections import OrderedDict

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import now_in_tz
from ..database.repository import (
    body_weight_repo,
    exercise_repo,
    message_log_repo,
    training_principle_repo,
    workout_set_repo,
)
from ..stats import compute_consistency
from .schemas import UserIntent

CARDIO_GROUPS = {"cardio"}
# Primary resistance-training groups used for lagging-group detection.
MAIN_GROUPS = ("chest", "back", "shoulders", "legs", "biceps", "triceps", "core")


async def build_coaching_context(
    session: AsyncSession,
    intent: UserIntent,
    message: str,
    user_id: int,
    user_tz: str = "America/New_York",
) -> str:
    """Assemble exercise history, guidance, and training principles into a prompt-ready string."""

    sections: list[str] = []
    matched_exercises = []
    has_cardio = False

    # 1. Resolve mentioned exercises via fuzzy search
    for name in intent.mentioned_exercises:
        candidates = await exercise_repo.search(session, name, limit=1)
        if candidates:
            matched_exercises.append(candidates[0])

    # 2. If muscle groups mentioned, pull exercises for those groups
    for group in intent.mentioned_muscle_groups:
        group_exercises = await exercise_repo.get_by_muscle_group(session, group)
        for ex in group_exercises:
            if ex.id not in {e.id for e in matched_exercises}:
                matched_exercises.append(ex)

    # 3. Check for cardio
    for ex in matched_exercises:
        if ex.muscle_group in CARDIO_GROUPS:
            has_cardio = True
            break
    # Also check intent muscle groups
    if set(intent.mentioned_muscle_groups) & CARDIO_GROUPS:
        has_cardio = True

    # 4. Training principles (all, by priority; cardio pulled in above the rest if relevant)
    principles = await training_principle_repo.get_all_by_priority(session, limit=20)
    if has_cardio:
        cardio_principles = await training_principle_repo.get_by_category(
            session, "cardio"
        )
        existing_ids = {p.id for p in principles}
        for cp in cardio_principles:
            if cp.id not in existing_ids:
                principles.append(cp)

    if principles:
        principle_lines = ["TRAINING PRINCIPLES:"]
        for p in principles:
            principle_lines.append(f"[{p.category}] {p.title}: {p.content}")
        sections.append("\n".join(principle_lines))

    # 5. Consistency snapshot — how often / how recently the user is training
    consistency_section = await _build_consistency_section(session, user_id, user_tz)
    if consistency_section:
        sections.append(consistency_section)

    # 6. Weekly volume trend by muscle group
    volume_section = await _build_volume_section(session, user_id)
    if volume_section:
        sections.append(volume_section)

    # 6b. When no specific exercise was named, surface the lagging muscle group so the
    # coach can volunteer a focus ("what should I train today?") instead of waiting.
    if not matched_exercises:
        lagging_section = await _build_lagging_groups_section(session, user_id)
        if lagging_section:
            sections.append(lagging_section)

    # 6c. Short-term memory — the last few turns, for continuity across messages.
    conversation_section = await _build_recent_conversation_section(session, user_id)
    if conversation_section:
        sections.append(conversation_section)

    # 7. Exercise details with history
    for exercise in matched_exercises:
        ex_lines = [f"EXERCISE: {exercise.name}"]

        if exercise.guidance:
            ex_lines.append(f"Guidance: {exercise.guidance}")

        # Pull recent sets (last 20)
        recent_sets = await workout_set_repo.get_by_exercise(
            session, exercise.id, user_id, limit=20
        )

        if recent_sets:
            is_cardio = exercise.muscle_group in CARDIO_GROUPS
            ex_lines.append("Recent history:")

            if is_cardio:
                for ws in recent_sets:
                    date_str = ws.set_date.strftime("%b %d")
                    parts = []
                    if ws.duration_minutes:
                        parts.append(f"{ws.duration_minutes} min")
                    if ws.distance:
                        parts.append(f"{ws.distance} mi")
                    if not parts and ws.reps:
                        parts.append(f"{ws.reps} reps")
                    line = f"- {date_str}: {', '.join(parts) or '?'}"
                    if ws.notes:
                        line += f" ({ws.notes})"
                    ex_lines.append(line)
            else:
                # Strength: group by batch_id, show sets/reps/weight
                by_batch: dict[int, list] = {}
                for ws in recent_sets:
                    by_batch.setdefault(ws.batch_id, []).append(ws)

                for batch_id, sets in by_batch.items():
                    first = sets[0]
                    date_str = first.set_date.strftime("%b %d")
                    set_count = len(sets)
                    reps_str = "/".join(str(s.reps or 0) for s in sets)
                    if first.weight is not None:
                        weights_str = "/".join(
                            str(int(s.weight) if s.weight == int(s.weight) else s.weight)
                            for s in sets
                        )
                        line = f"- {date_str}: {set_count}x reps {reps_str} @ {weights_str} {first.weight_unit}"
                    else:
                        line = f"- {date_str}: {set_count}x reps {reps_str} (bodyweight)"

                    # Collect unique notes from this batch's sets
                    batch_notes = list(dict.fromkeys(
                        s.notes for s in sets if s.notes
                    ))
                    if batch_notes:
                        line += f" ({'; '.join(batch_notes)})"
                    ex_lines.append(line)

                # PR: true all-time heaviest set for this exercise (not just within
                # the recent window), so the coach prescribes against the real ceiling.
                prs = await workout_set_repo.get_personal_records(
                    session, exercise.id, user_id, limit=1
                )
                if prs:
                    pr = prs[0]
                    pr_date = pr.set_date.strftime("%b %d")
                    ex_lines.append(
                        f"PR (all-time): {pr.weight:g} {pr.weight_unit} x {pr.reps} reps ({pr_date})"
                    )

        sections.append("\n".join(ex_lines))

    # 8. Body weight history (last 5 readings) with trend
    weight_section = await _build_body_weight_section(session, user_id)
    if weight_section:
        sections.append(weight_section)

    return "\n\n".join(sections)


async def _build_consistency_section(
    session: AsyncSession, user_id: int, user_tz: str
) -> str:
    """One-block summary of training frequency, streak, and recency."""
    today = now_in_tz(user_tz).date()
    dates_90 = await workout_set_repo.get_workout_dates(session, user_id, days=90)
    if not dates_90:
        return ""

    dates_30 = [d for d in dates_90 if (today - d).days <= 30]
    count_7d = len([d for d in dates_90 if (today - d).days <= 7])
    stats = compute_consistency(dates_90, dates_30, today)

    lines = ["CONSISTENCY:"]
    lines.append(
        f"- {count_7d} workouts in last 7 days, {stats['count_30d']} in last 30, "
        f"{stats['count_90d']} in last 90"
    )
    if stats["streak"] > 0:
        unit = "day" if stats["streak"] == 1 else "days"
        lines.append(f"- Current streak: {stats['streak']} {unit}")
    elif stats["days_since_last"] is not None:
        lines.append(f"- Last workout: {stats['days_since_last']} days ago")
    if stats["avg_gap"] is not None:
        lines.append(f"- Avg {stats['avg_gap']:.1f} days between workouts")
    return "\n".join(lines)


async def _build_volume_section(session: AsyncSession, user_id: int) -> str:
    """Weekly tonnage by muscle group for the last few weeks (trend signal)."""
    rows = await workout_set_repo.get_weekly_volume(session, user_id, weeks=8)
    if not rows:
        return ""

    # Group by yearweek (rows arrive ordered yw desc, vol desc)
    weeks: OrderedDict[int, list] = OrderedDict()
    for yw, mg, vol in rows:
        weeks.setdefault(yw, []).append((mg, vol))

    lines = ["VOLUME (weekly tonnage by muscle group, recent first):"]
    for yw, groups in weeks.items():
        year = yw // 100
        week = yw % 100
        group_str = "; ".join(f"{mg} {vol:,.0f}" for mg, vol in groups)
        lines.append(f"- Wk {year}-{week:02d}: {group_str}")
    return "\n".join(lines)


def rank_lagging_groups(vol_by_group: dict) -> tuple[list, list]:
    """Split MAIN_GROUPS into (trained-ranked-ascending-by-volume, untrained).

    Pure helper so the lagging-group logic can be unit-tested without a DB.
    """
    ranked = sorted(
        ((g, v) for g, v in vol_by_group.items() if g in MAIN_GROUPS),
        key=lambda x: x[1],
    )
    untrained = [g for g in MAIN_GROUPS if g not in vol_by_group]
    return ranked, untrained


async def _build_lagging_groups_section(session: AsyncSession, user_id: int) -> str:
    """Rank resistance groups by recent volume so the coach can steer to what's lagging."""
    rows = await workout_set_repo.get_weekly_volume(session, user_id, weeks=4)
    if not rows:
        return ""  # no recent lifting to reason about — stay quiet

    vol_by_group: dict[str, float] = {}
    for _yw, mg, vol in rows:
        vol_by_group[mg] = vol_by_group.get(mg, 0.0) + (vol or 0.0)

    ranked, untrained = rank_lagging_groups(vol_by_group)
    if not ranked and not untrained:
        return ""

    lines = ["LAGGING MUSCLE GROUPS (last 4 weeks, lowest volume / stalest first):"]
    for g, v in ranked[:4]:
        lines.append(f"- {g}: {v:,.0f} lbs")
    for g in untrained:
        lines.append(f"- {g}: not trained in the last 4 weeks")
    return "\n".join(lines)


async def _build_recent_conversation_section(session: AsyncSession, user_id: int) -> str:
    """The last few turns for continuity. The current message isn't logged yet, so
    every row here is a prior turn."""
    logs = await message_log_repo.get_by_user(session, user_id, limit=4)
    if not logs:
        return ""

    lines = ["RECENT CONVERSATION (oldest first):"]
    for log in reversed(logs):  # get_by_user is newest-first
        raw = (log.raw_message or "").strip().replace("\n", " ")
        summary = (log.response_summary or "").strip().replace("\n", " ")
        if raw:
            lines.append(f"- You: {raw[:100]}")
        if summary:
            lines.append(f"  Nunzio: {summary[:120]}")
    return "\n".join(lines)


async def _build_body_weight_section(session: AsyncSession, user_id: int) -> str:
    """Last few body-weight readings plus an overall trend line."""
    weight_records = await body_weight_repo.get_by_user(session, user_id, limit=5)
    if not weight_records:
        return ""

    lines = ["BODY WEIGHT:"]
    for r in weight_records:
        date_str = r.recorded_at.strftime("%b %d")
        line = f"- {date_str}: {r.weight:g} {r.unit}"
        if r.notes:
            line += f" ({r.notes})"
        lines.append(line)

    # Trend: oldest-to-newest within this window (records are newest-first)
    if len(weight_records) >= 2:
        newest = weight_records[0]
        oldest = weight_records[-1]
        delta = newest.weight - oldest.weight
        days = (newest.recorded_at - oldest.recorded_at).days
        if days > 0 and abs(delta) >= 0.1:
            per_week = delta / days * 7
            direction = "down" if delta < 0 else "up"
            lines.append(
                f"- Trend: {direction} {abs(delta):g} {newest.unit} over {days} days "
                f"({per_week:+.1f} {newest.unit}/wk)"
            )
        elif days > 0:
            lines.append(f"- Trend: stable over {days} days")
    return "\n".join(lines)
