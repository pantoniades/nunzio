"""Coaching context assembly — pulls history, guidance, and principles into a prompt block."""

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.repository import (
    exercise_repo,
    training_principle_repo,
    workout_set_repo,
)
from .schemas import UserIntent

CARDIO_GROUPS = {"cardio"}


async def build_coaching_context(
    session: AsyncSession, intent: UserIntent, message: str, user_id: int
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

    # 4. Training principles (top 6 by priority, plus cardio if relevant)
    principles = await training_principle_repo.get_all_by_priority(session, limit=6)
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

    # 5. Exercise details with history
    for exercise in matched_exercises:
        ex_lines = [f"EXERCISE: {exercise.name}"]

        if exercise.guidance:
            ex_lines.append(f"Guidance: {exercise.guidance}")

        # Pull recent sets (last 10)
        recent_sets = await workout_set_repo.get_by_exercise(
            session, exercise.id, user_id, limit=10
        )

        if recent_sets:
            is_cardio = exercise.muscle_group in CARDIO_GROUPS
            ex_lines.append("Recent history:")

            if is_cardio:
                for ws in recent_sets:
                    date_str = ws.session.date.strftime("%b %d") if ws.session else "?"
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
                # Strength: group by session, show sets/reps/weight
                # Group consecutive sets from the same session
                by_session: dict[int, list] = {}
                for ws in recent_sets:
                    by_session.setdefault(ws.session_id, []).append(ws)

                for session_id, sets in list(by_session.items())[:5]:
                    first = sets[0]
                    date_str = (
                        first.session.date.strftime("%b %d") if first.session else "?"
                    )
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

                    # Collect unique notes from this session's sets
                    session_notes = list(dict.fromkeys(
                        s.notes for s in sets if s.notes
                    ))
                    if session_notes:
                        line += f" ({'; '.join(session_notes)})"
                    ex_lines.append(line)

                # PR: heaviest weight × reps
                pr_sets = [s for s in recent_sets if s.weight is not None]
                if pr_sets:
                    pr = max(pr_sets, key=lambda s: s.weight)
                    pr_date = pr.session.date.strftime("%b %d") if pr.session else "?"
                    ex_lines.append(
                        f"PR: {pr.weight} {pr.weight_unit} x {pr.reps} reps ({pr_date})"
                    )

        sections.append("\n".join(ex_lines))

    return "\n\n".join(sections)
