"""Core message processing — shared by CLI and Telegram bot."""

import asyncio
import logging
import re
from collections import OrderedDict
from datetime import date as date_type, datetime, timedelta

from .database.connection import db_manager
from .database.models import _now_nyc
from .database.repository import body_weight_repo, exercise_repo, message_log_repo, workout_set_repo
from .llm.client import LLMClient
from .llm.context import build_coaching_context

logger = logging.getLogger(__name__)


class MessageHandler:
    """Routes natural language through LLM extraction to DB persistence."""

    def __init__(self, verbose: bool = True) -> None:
        self._llm = LLMClient()
        self._verbose = verbose

    async def initialize(self) -> None:
        await db_manager.initialize()
        await self._llm.initialize()

    async def close(self) -> None:
        await self._llm.close()
        await db_manager.close()

    async def process(self, message: str, user_id: int) -> str:
        """Classify intent and route to the appropriate handler.

        Runs classification and workout extraction in parallel so log_workout
        (the most common intent) doesn't pay for two sequential LLM calls.
        """
        intent, workout_data = await asyncio.gather(
            self._llm.classify_intent(message),
            self._llm.extract_workout_data(message),
        )

        if intent.intent == "log_workout" and intent.confidence > 0.5:
            response = await self._handle_log_workout(message, user_id, workout_data=workout_data)
        elif intent.intent == "log_weight":
            response = await self._handle_log_weight(message, user_id)
        elif intent.intent == "view_stats":
            response = await self._handle_view_stats(intent, user_id)
        elif intent.intent == "list_workouts":
            response = await self._handle_list_workouts(user_id)
        elif intent.intent == "delete_workout":
            response = await self._handle_delete_workout(message, user_id)
        elif intent.intent == "repeat_last":
            response = await self._handle_repeat_last(message, user_id)
        else:
            response = await self._handle_coaching(message, intent, user_id)

        # Fire-and-forget message logging — failure must not block the response
        try:
            async with db_manager.get_session() as session:
                await message_log_repo.create(
                    session,
                    obj_in={
                        "user_id": user_id,
                        "raw_message": message,
                        "classified_intent": intent.intent,
                        "confidence": intent.confidence,
                        "extracted_data": None,
                        "response_summary": response[:200] if response else None,
                    },
                )
        except Exception:
            logger.warning("Message logging failed", exc_info=True)

        return response

    @staticmethod
    def _expand_sets(exercises: list) -> list:
        """Expand a lone set with set_number>1 into N copies.

        Catches the LLM mistake where "2 sets of 10" becomes one ExerciseSet
        with set_number=2 instead of two separate objects.
        """
        from collections import Counter

        # Count how many ExerciseSet objects exist per exercise name
        name_counts = Counter(ex.exercise_name for ex in exercises)

        expanded: list = []
        for ex in exercises:
            if name_counts[ex.exercise_name] == 1 and ex.set_number > 1:
                # Single entry with set_number > 1 → likely "N sets" misread as set #N
                for i in range(1, ex.set_number + 1):
                    copy = ex.model_copy(update={"set_number": i})
                    expanded.append(copy)
            else:
                expanded.append(ex)
        return expanded

    async def _handle_log_workout(self, message: str, user_id: int, *, workout_data=None) -> str:
        if workout_data is None:
            workout_data = await self._llm.extract_workout_data(message)
        if not workout_data or not workout_data.exercises:
            return "I couldn't extract workout details. Try something like: '3 sets of bench press at 185 lbs, 10 reps'"

        workout_data.exercises = self._expand_sets(workout_data.exercises)

        # Apply sensible defaults for missing reps (strength only)
        defaulted_reps: set[int] = set()  # indices where we assumed reps
        for i, ex_set in enumerate(workout_data.exercises):
            if ex_set.duration_minutes:
                continue  # cardio — no reps expected
            if not ex_set.reps:
                ex_set.reps = 10
                defaulted_reps.add(i)

        async with db_manager.get_session() as session:
            batch_id = await workout_set_repo.get_next_batch_id(session, user_id)
            if workout_data.date:
                now = datetime.combine(workout_data.date, _now_nyc().time())
            else:
                now = _now_nyc()

            logged: list[str] = []
            logged_set_data: list[dict] = []
            history: list = []
            for set_idx, ex_set in enumerate(workout_data.exercises):
                raw_name = ex_set.exercise_name
                matched_differently = False

                # 1. Exact name match
                exercise = await exercise_repo.get_by_name(session, raw_name)

                if not exercise:
                    # 2. Scored matching against catalog
                    scored = await exercise_repo.search_scored(session, raw_name)
                    if scored and scored[0][1] >= 0.5:
                        exercise = scored[0][0]
                        matched_differently = (exercise.name.lower() != raw_name.lower())
                    else:
                        # 3. Score too low — create ad-hoc exercise with user's name
                        exercise = await exercise_repo.create(
                            session,
                            obj_in={
                                "name": raw_name,
                                "muscle_group": "general",
                            },
                        )

                unit = ex_set.unit if ex_set.unit != "bodyweight" else "lbs"
                await workout_set_repo.create(
                    session,
                    obj_in={
                        "user_id": user_id,
                        "batch_id": batch_id,
                        "set_date": now,
                        "exercise_id": exercise.id,
                        "set_number": ex_set.set_number,
                        "reps": ex_set.reps,
                        "weight": ex_set.weight,
                        "weight_unit": unit,
                        "duration_minutes": ex_set.duration_minutes,
                        "distance": ex_set.distance,
                        "raw_exercise_name": raw_name,
                        "notes": ex_set.notes,
                    },
                )

                # Build display name — show mapping when matched differently
                display_name = exercise.name
                if matched_differently:
                    display_name = f'{exercise.name} (from "{raw_name}")'

                if ex_set.duration_minutes:
                    parts = [f"{ex_set.duration_minutes} min"]
                    if ex_set.distance:
                        parts.append(f"{ex_set.distance} mi")
                    line = f"  {display_name}: {', '.join(parts)}"
                else:
                    weight_str = (
                        f"{ex_set.weight} {ex_set.unit}" if ex_set.weight else "bodyweight"
                    )
                    reps_display = f"{ex_set.reps} reps"
                    if set_idx in defaulted_reps:
                        reps_display += " (assumed)"
                    line = f"  {display_name}: set {ex_set.set_number} - {reps_display} @ {weight_str}"

                if ex_set.notes:
                    line += f" — note: {ex_set.notes}"
                logged.append(line)
                logged_set_data.append({
                    "exercise_id": exercise.id,
                    "name": exercise.name,
                    "weight": ex_set.weight,
                    "reps": ex_set.reps,
                    "notes": ex_set.notes,
                    "is_cardio": bool(ex_set.duration_minutes),
                })

            # Query history for personality comment
            exercise_ids = list({d["exercise_id"] for d in logged_set_data})
            history = await workout_set_repo.get_recent_for_exercises(
                session, exercise_ids, user_id, exclude_batch=batch_id
            )

        comment = self._generate_log_comment(logged_set_data, history, now)

        if workout_data.date and workout_data.date != date_type.today():
            date_label = workout_data.date.strftime("%b %-d")
            header = f"Logged workout (#{batch_id}) for {date_label}:" if self._verbose else f"Logged for {date_label}:"
        else:
            header = f"Logged workout (#{batch_id}):" if self._verbose else "Logged:"
        lines = [header] + logged
        volume_by_unit: dict[str, float] = {}
        for s in workout_data.exercises:
            if s.unit == "bodyweight" or not s.weight:
                continue
            unit = s.unit or "lbs"
            volume_by_unit[unit] = volume_by_unit.get(unit, 0) + s.weight * (s.reps or 0)
        for unit, vol in volume_by_unit.items():
            if vol > 0:
                lines.append(f"  Total volume: {vol:.0f} {unit}")
        if comment:
            lines.append(comment)
        return "\n".join(lines)

    @staticmethod
    def _generate_log_comment(
        logged_sets: list[dict],
        history: list,
        now: datetime,
    ) -> str | None:
        """Return a one-line heuristic comment based on what was just logged.

        Checks in priority order, returns first match:
        1. New PR (weight exceeds all historical weight for that exercise)
        2. First time logging an exercise
        3. Back after gap (>3 days since last set for any logged exercise)
        4. Weight increase (current > most recent historical for same exercise)
        5. Pain in notes
        """
        if not logged_sets:
            return None

        # Build per-exercise history lookup
        # hist_by_ex: {exercise_id: [WorkoutSet, ...]} ordered newest first
        hist_by_ex: dict[int, list] = {}
        for ws in history:
            hist_by_ex.setdefault(ws.exercise_id, []).append(ws)

        # Unique exercises from this batch (preserve order)
        seen_ids: set[int] = set()
        exercises: list[dict] = []
        for s in logged_sets:
            if s["exercise_id"] not in seen_ids:
                seen_ids.add(s["exercise_id"])
                exercises.append(s)

        # Check heuristics per exercise, return first match by priority

        # 1. New PR
        for ex in exercises:
            if ex["is_cardio"] or not ex["weight"]:
                continue
            ex_hist = hist_by_ex.get(ex["exercise_id"], [])
            max_current = max(
                (s["weight"] for s in logged_sets
                 if s["exercise_id"] == ex["exercise_id"] and s["weight"]),
                default=0,
            )
            max_historical = max(
                (ws.weight for ws in ex_hist if ws.weight is not None),
                default=0,
            )
            if max_historical > 0 and max_current > max_historical:
                return f"New PR on {ex['name']}!"

        # 2. First time
        for ex in exercises:
            if ex["exercise_id"] not in hist_by_ex:
                return f"First time logging {ex['name']}."

        # 3. Back after gap (>3 days)
        for ex in exercises:
            ex_hist = hist_by_ex.get(ex["exercise_id"], [])
            if ex_hist:
                most_recent_date = max(ws.set_date for ws in ex_hist)
                gap_days = (now - most_recent_date).days
                if gap_days > 3:
                    return f"Back at it after {gap_days} days."

        # 4. Weight increase vs most recent
        for ex in exercises:
            if ex["is_cardio"] or not ex["weight"]:
                continue
            ex_hist = hist_by_ex.get(ex["exercise_id"], [])
            if not ex_hist:
                continue
            # Most recent historical set for this exercise
            most_recent = ex_hist[0]  # already sorted newest first
            if most_recent.weight and ex["weight"] > most_recent.weight:
                return f"Moving up in weight on {ex['name']}."

        # 5. Pain in notes
        pain_words = {"pain", "sore", "hurt"}
        for s in logged_sets:
            if s["notes"] and any(w in s["notes"].lower() for w in pain_words):
                return "Take it easy if the pain persists."

        return None

    @staticmethod
    def _parse_workout_id(message: str) -> int | None:
        """Extract a workout ID from a message like 'delete #42' or 'delete 42'."""
        match = re.search(r"#?(\d+)", message)
        if match:
            return int(match.group(1))
        return None

    async def _handle_delete_workout(self, message: str, user_id: int) -> str:
        """Delete a workout — 'undo'/'delete last' or by batch ID."""
        msg_lower = message.lower()
        async with db_manager.get_session() as session:
            # "undo", "delete last", or no specific ID → delete most recent
            if any(word in msg_lower for word in ["undo", "last"]) or not re.search(r"\d+", message):
                latest = await workout_set_repo.get_latest_batch_for_user(session, user_id)
                if not latest:
                    return "Nothing to delete — no workouts found."
                batch_id = latest[0].batch_id
            else:
                batch_id = self._parse_workout_id(message)
                if not batch_id:
                    return "I couldn't figure out which workout to delete. Try 'undo' or 'delete #42'."

            deleted = await workout_set_repo.delete_batch(session, batch_id, user_id)
            if not deleted:
                return f"Workout #{batch_id} not found (or not yours)."

            # Build confirmation showing what was deleted
            exercises: list[str] = []
            for s in deleted:
                name = s.exercise.name if s.exercise else f"exercise #{s.exercise_id}"
                if name not in exercises:
                    exercises.append(name)
            date_str = deleted[0].set_date.strftime("%b %-d")
            ex_str = ", ".join(exercises) if exercises else "no exercises"
            return f"Deleted workout #{batch_id} ({date_str}): {ex_str} — {len(deleted)} sets removed."

    @staticmethod
    def _parse_repeat_modifiers(message: str) -> dict:
        """Parse weight overrides and repetition count from a repeat message.

        Returns dict with keys: weight, weight_unit, times, note.
        """
        # Strip trigger words first
        stripped = re.sub(
            r"\b(same as last time|repeat last|same thing|again|repeat)\b",
            "",
            message,
            flags=re.IGNORECASE,
        ).strip(" ,.-;:")

        weight = None
        weight_unit = None
        times = 1
        note = stripped

        # Weight override: "at 35 lb", "for 35 lbs", "@ 40", "35 lb", "35 kg"
        weight_match = re.search(
            r"(?:at|for|@)\s*(\d+(?:\.\d+)?)\s*(lbs?|kg)?\b"
            r"|(\d+(?:\.\d+)?)\s*(lbs?|kg)\b",
            stripped,
            re.IGNORECASE,
        )
        if weight_match:
            w = weight_match.group(1) or weight_match.group(3)
            u = weight_match.group(2) or weight_match.group(4)
            weight = float(w)
            weight_unit = "kg" if u and u.lower().startswith("k") else "lbs"
            note = stripped[:weight_match.start()] + stripped[weight_match.end():]

        # Repetition count: "twice", "x2", "2x", "2 times", "3 times"
        times_match = re.search(
            r"\btwice\b|\bx\s*(\d+)\b|(\d+)\s*x\b|(\d+)\s+times?\b",
            note or "",
            re.IGNORECASE,
        )
        if times_match:
            if "twice" in (times_match.group(0) or "").lower():
                times = 2
            else:
                t = times_match.group(1) or times_match.group(2) or times_match.group(3)
                times = int(t)
            note = note[:times_match.start()] + note[times_match.end():]

        note = (note or "").strip(" ,.-;:") or None

        return {"weight": weight, "weight_unit": weight_unit, "times": times, "note": note}

    async def _handle_repeat_last(self, message: str, user_id: int) -> str:
        """Repeat the user's most recent workout, with optional modifiers."""
        mods = self._parse_repeat_modifiers(message)

        async with db_manager.get_session() as session:
            last_sets = await workout_set_repo.get_latest_batch_for_user(session, user_id)
            if not last_sets:
                return "Nothing to repeat — no previous workouts found."

            old_batch_id = last_sets[0].batch_id
            now = _now_nyc()
            sorted_sets = sorted(last_sets, key=lambda s: (s.exercise_id, s.set_number))

            logged: list[str] = []
            for _rep in range(mods["times"]):
                new_batch_id = await workout_set_repo.get_next_batch_id(session, user_id)

                for old_set in sorted_sets:
                    use_weight = mods["weight"] if mods["weight"] is not None else old_set.weight
                    use_unit = mods["weight_unit"] if mods["weight_unit"] is not None else old_set.weight_unit

                    await workout_set_repo.create(
                        session,
                        obj_in={
                            "user_id": user_id,
                            "batch_id": new_batch_id,
                            "set_date": now,
                            "exercise_id": old_set.exercise_id,
                            "set_number": old_set.set_number,
                            "reps": old_set.reps,
                            "weight": use_weight,
                            "weight_unit": use_unit,
                            "duration_minutes": old_set.duration_minutes,
                            "distance": old_set.distance,
                            "raw_exercise_name": old_set.raw_exercise_name,
                            "notes": mods["note"],
                        },
                    )
                    name = old_set.exercise.name if old_set.exercise else f"exercise #{old_set.exercise_id}"
                    if old_set.duration_minutes:
                        parts = [f"{old_set.duration_minutes} min"]
                        if old_set.distance:
                            parts.append(f"{old_set.distance} mi")
                        line = f"  {name}: {', '.join(parts)}"
                    else:
                        weight_str = f"{use_weight} {use_unit}" if use_weight else "bodyweight"
                        line = f"  {name}: set {old_set.set_number} - {old_set.reps} reps @ {weight_str}"
                    if mods["note"]:
                        line += f" — note: {mods['note']}"
                    logged.append(line)

        header = f"Repeated #{old_batch_id} → #{new_batch_id}:" if self._verbose else "Repeated last workout:"
        if mods["times"] > 1:
            header = f"Repeated #{old_batch_id} x{mods['times']}:" if self._verbose else f"Repeated last workout x{mods['times']}:"
        return "\n".join([header] + logged)

    @staticmethod
    def _fmt_weight(w: float | None, unit: str) -> str:
        """Format weight: drop .0, omit unit when lbs."""
        if w is None:
            return "bodyweight"
        w_str = f"{w:g}"
        if unit and unit != "lbs":
            return f"{w_str} {unit}"
        return w_str

    async def _handle_view_stats(self, intent, user_id: int) -> str:
        stats_type = getattr(intent, "stats_type", None) or "overview"
        if stats_type == "prs":
            return await self._handle_prs(user_id)
        elif stats_type == "exercise_history":
            return await self._handle_exercise_history(intent, user_id)
        elif stats_type == "volume":
            return await self._handle_volume_trends(user_id)
        elif stats_type == "consistency":
            return await self._handle_consistency(user_id)
        elif stats_type == "weight":
            return await self._handle_weight_trend(user_id)
        else:
            return await self._handle_overview(user_id)

    async def _handle_overview(self, user_id: int) -> str:
        """Default stats: last 3 days of workouts."""
        async with db_manager.get_session() as session:
            all_sets = await workout_set_repo.get_latest_batches(session, user_id, limit=20)

            if not all_sets:
                return "No workouts logged yet. Tell me about a workout to get started!"

            # Group sets by date, keep adding until >= 3 distinct days
            days: OrderedDict[str, list] = OrderedDict()
            for ws in reversed(all_sets):
                date_key = ws.set_date.strftime("%a %b %-d")
                days.setdefault(date_key, []).append(ws)

            while len(days) > 3:
                days.popitem(last=False)

            lines: list[str] = []
            for i, (date_key, day_sets) in enumerate(days.items()):
                if i > 0:
                    lines.append("")
                lines.append(date_key)

                exercises: OrderedDict[int, list] = OrderedDict()
                for s in day_sets:
                    exercises.setdefault(s.exercise_id, []).append(s)

                for ex_id, ex_sets in exercises.items():
                    first = ex_sets[0]
                    name = first.exercise.name if first.exercise else f"exercise #{ex_id}"

                    if first.duration_minutes:
                        parts = [f"{first.duration_minutes} min"]
                        if first.distance:
                            d_str = f"{first.distance:g}"
                            parts.append(f"{d_str} mi")
                        lines.append(f"  {name} \u2014 {', '.join(parts)}")
                        continue

                    all_same = all(
                        s.reps == first.reps and s.weight == first.weight
                        for s in ex_sets
                    )

                    if all_same and first.weight is not None:
                        w_str = self._fmt_weight(first.weight, first.weight_unit)
                        lines.append(f"  {name} \u2014 {len(ex_sets)}x{first.reps} @ {w_str}")
                    elif all_same and first.weight is None:
                        lines.append(f"  {name} \u2014 {len(ex_sets)}x{first.reps}")
                    else:
                        set_strs: list[str] = []
                        for s in ex_sets:
                            r = s.reps or 0
                            if s.weight is not None:
                                w_str = self._fmt_weight(s.weight, s.weight_unit)
                                set_strs.append(f"{r}x{w_str}")
                            else:
                                set_strs.append(f"{r} reps")
                        lines.append(f"  {name} \u2014 {' / '.join(set_strs)}")

            return "\n".join(lines)

    async def _handle_prs(self, user_id: int) -> str:
        """Show personal records — heaviest weight per exercise."""
        async with db_manager.get_session() as session:
            prs = await workout_set_repo.get_all_prs(session, user_id)

            if not prs:
                return "No personal records yet — log some weighted exercises first!"

            lines: list[str] = ["Personal Records:"]
            for ws in prs:
                name = ws.exercise.name if ws.exercise else f"exercise #{ws.exercise_id}"
                w_str = self._fmt_weight(ws.weight, ws.weight_unit)
                date_str = ws.set_date.strftime("%b %-d")
                reps_str = f" x {ws.reps}" if ws.reps else ""
                lines.append(f"  {name}: {w_str}{reps_str} ({date_str})")

            return "\n".join(lines)

    async def _handle_exercise_history(self, intent, user_id: int) -> str:
        """Show history for a specific exercise."""
        async with db_manager.get_session() as session:
            # Resolve exercise from mentioned_exercises
            exercise = None
            for name in getattr(intent, "mentioned_exercises", []):
                exercise = await exercise_repo.get_by_name(session, name)
                if not exercise:
                    scored = await exercise_repo.search_scored(session, name)
                    if scored and scored[0][1] >= 0.3:
                        exercise = scored[0][0]
                if exercise:
                    break

            if not exercise:
                return "Which exercise? Try something like 'bench press history'."

            sets = await workout_set_repo.get_by_exercise(
                session, exercise.id, user_id, limit=50
            )

            if not sets:
                return f"No history for {exercise.name}."

            # Group by batch_id
            batches: OrderedDict[int, list] = OrderedDict()
            for s in sets:
                batches.setdefault(s.batch_id, []).append(s)

            lines: list[str] = [f"{exercise.name} — last {len(batches)} sessions:"]
            for batch_id, batch_sets in list(batches.items())[:20]:
                first = batch_sets[0]
                date_str = first.set_date.strftime("%b %-d")

                if first.duration_minutes:
                    parts = [f"{first.duration_minutes} min"]
                    if first.distance:
                        parts.append(f"{first.distance:g} mi")
                    lines.append(f"  {date_str}: {', '.join(parts)}")
                else:
                    n = len(batch_sets)
                    all_same = all(
                        s.reps == first.reps and s.weight == first.weight
                        for s in batch_sets
                    )
                    if all_same and first.weight is not None:
                        w_str = self._fmt_weight(first.weight, first.weight_unit)
                        lines.append(f"  {date_str}: {n}x{first.reps} @ {w_str}")
                    else:
                        set_strs: list[str] = []
                        for s in batch_sets:
                            r = s.reps or 0
                            w_str = self._fmt_weight(s.weight, s.weight_unit)
                            set_strs.append(f"{r}x{w_str}")
                        lines.append(f"  {date_str}: {' / '.join(set_strs)}")

            return "\n".join(lines)

    async def _handle_volume_trends(self, user_id: int) -> str:
        """Show weekly volume by muscle group for the last 8 weeks."""
        async with db_manager.get_session() as session:
            rows = await workout_set_repo.get_weekly_volume(session, user_id, weeks=8)

            if not rows:
                return "No volume data yet — log some weighted exercises first!"

            # Group by yearweek
            weeks: OrderedDict[int, list] = OrderedDict()
            for yw, mg, vol in rows:
                weeks.setdefault(yw, []).append((mg, vol))

            lines: list[str] = ["Weekly Volume (last 8 weeks):"]
            for yw, groups in weeks.items():
                # Convert YEARWEEK to readable format
                year = yw // 100
                week = yw % 100
                lines.append(f"  Week {week} ({year}):")
                for mg, vol in groups:
                    lines.append(f"    {mg}: {vol:,.0f} lbs")

            return "\n".join(lines)

    async def _handle_consistency(self, user_id: int) -> str:
        """Show workout frequency, streak, and consistency metrics."""
        async with db_manager.get_session() as session:
            dates_90 = await workout_set_repo.get_workout_dates(session, user_id, days=90)
            dates_30 = [d for d in dates_90 if (datetime.now().date() - d).days <= 30]

        stats = self._compute_consistency(dates_90, dates_30)
        lines: list[str] = ["Consistency:"]
        lines.append(f"  Last 30 days: {stats['count_30d']} workouts")
        lines.append(f"  Last 90 days: {stats['count_90d']} workouts")
        if stats["avg_gap"] is not None:
            lines.append(f"  Avg days between workouts: {stats['avg_gap']:.1f}")
        if stats["streak"] > 0:
            unit = "day" if stats["streak"] == 1 else "days"
            lines.append(f"  Current streak: {stats['streak']} {unit}")
        elif stats["count_90d"] > 0:
            lines.append(f"  Last workout: {stats['days_since_last']} days ago")

        return "\n".join(lines)

    @staticmethod
    def _compute_consistency(
        dates_90: list, dates_30: list
    ) -> dict:
        """Compute consistency metrics from workout date lists.

        Returns dict with count_30d, count_90d, avg_gap, streak, days_since_last.
        """
        today = date_type.today()
        count_30d = len(dates_30)
        count_90d = len(dates_90)

        avg_gap = None
        if count_90d >= 2:
            sorted_dates = sorted(dates_90)
            gaps = [(sorted_dates[i + 1] - sorted_dates[i]).days for i in range(len(sorted_dates) - 1)]
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

    async def _handle_list_workouts(self, user_id: int) -> str:
        """Show last 10 workouts with batch IDs for use with delete."""
        async with db_manager.get_session() as session:
            all_sets = await workout_set_repo.get_latest_batches(session, user_id, limit=10)

            if not all_sets:
                return "No workouts logged yet."

            # Group by batch_id (already ordered by batch_id desc)
            batches: OrderedDict[int, list] = OrderedDict()
            for s in all_sets:
                batches.setdefault(s.batch_id, []).append(s)

            lines: list[str] = []
            for batch_id, sets in batches.items():
                date_str = sets[0].set_date.strftime("%b %-d")

                # Collect unique exercise names preserving order
                ex_names: list[str] = []
                for s in sets:
                    name = s.exercise.name if s.exercise else f"exercise #{s.exercise_id}"
                    if name not in ex_names:
                        ex_names.append(name)

                n = len(sets)
                set_word = "set" if n == 1 else "sets"
                ex_str = ", ".join(ex_names) if ex_names else "no exercises"
                lines.append(f"#{batch_id}  {date_str}  {ex_str} ({n} {set_word})")

            return "\n".join(lines)

    async def _handle_log_weight(self, message: str, user_id: int) -> str:
        """Log a body weight reading."""
        data = await self._llm.extract_body_weight_data(message)
        if not data:
            return "I couldn't extract a weight reading. Try something like: 'weighed 185 lbs'"

        if data.date:
            recorded_at = datetime.combine(data.date, _now_nyc().time())
        else:
            recorded_at = _now_nyc()

        async with db_manager.get_session() as session:
            previous = await body_weight_repo.get_latest(session, user_id)

            await body_weight_repo.create(
                session,
                obj_in={
                    "user_id": user_id,
                    "weight": data.weight,
                    "unit": data.unit,
                    "notes": data.notes,
                    "recorded_at": recorded_at,
                },
            )

        w_str = f"{data.weight:g} {data.unit}"
        parts = [f"Logged {w_str}."]

        if data.notes:
            parts[0] = f"Logged {w_str} ({data.notes})."

        if data.date and data.date != date_type.today():
            date_label = data.date.strftime("%b %-d")
            parts[0] = parts[0].rstrip(".") + f" for {date_label}."

        if previous:
            delta = data.weight - previous.weight
            if abs(delta) >= 0.1:
                arrow = "\u2193" if delta < 0 else "\u2191"
                prev_date = previous.recorded_at.strftime("%b %-d")
                parts.append(f"{arrow} {abs(delta):g} {data.unit} from last weigh-in on {prev_date}.")

        return " ".join(parts)

    async def _handle_weight_trend(self, user_id: int) -> str:
        """Show recent body weight readings and trend."""
        async with db_manager.get_session() as session:
            records = await body_weight_repo.get_by_user(session, user_id, limit=10)

        if not records:
            return "No body weight readings yet. Try: 'weighed 185 lbs'"

        lines: list[str] = ["Body Weight:"]
        for r in records:
            date_str = r.recorded_at.strftime("%b %-d")
            line = f"  {date_str}: {r.weight:g} {r.unit}"
            if r.notes:
                line += f" ({r.notes})"
            lines.append(line)

        # Overall delta (oldest to newest in this window)
        if len(records) >= 2:
            newest = records[0]
            oldest = records[-1]
            delta = newest.weight - oldest.weight
            days = (newest.recorded_at - oldest.recorded_at).days
            if days > 0:
                per_week = delta / days * 7
                arrow = "\u2193" if delta < 0 else "\u2191"
                lines.append(f"  {arrow} {abs(delta):g} {newest.unit} over {days} days ({per_week:+.1f}/wk)")

        return "\n".join(lines)

    async def _handle_coaching(self, message: str, intent, user_id: int) -> str:
        async with db_manager.get_session() as session:
            context = await build_coaching_context(session, intent, message, user_id)
            return await self._llm.generate_coaching_response(message, context)
