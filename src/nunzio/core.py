"""Core message processing — shared by CLI and Telegram bot."""

import re
from datetime import datetime

from .database.connection import db_manager
from .database.repository import exercise_repo, message_log_repo, workout_session_repo, workout_set_repo
from .llm.client import LLMClient
from .llm.context import build_coaching_context


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
        """Classify intent and route to the appropriate handler."""
        intent = await self._llm.classify_intent(message)

        if intent.intent == "log_workout" and intent.confidence > 0.5:
            response = await self._handle_log_workout(message, user_id)
        elif intent.intent == "view_stats":
            response = await self._handle_view_stats(user_id)
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
            pass

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

    async def _handle_log_workout(self, message: str, user_id: int) -> str:
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
            ws = await workout_session_repo.create(
                session,
                obj_in={"date": datetime.now(), "notes": message, "user_id": user_id},
            )

            logged: list[str] = []
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
                        "session_id": ws.id,
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

        header = f"Logged workout (session #{ws.id}):" if self._verbose else "Logged:"
        lines = [header] + logged
        total_volume = sum(
            (s.weight or 0) * (s.reps or 0)
            for s in workout_data.exercises
            if s.unit != "bodyweight"
        )
        if total_volume > 0:
            lines.append(f"  Total volume: {total_volume:.0f} lbs")
        return "\n".join(lines)

    @staticmethod
    def _parse_session_id(message: str) -> int | None:
        """Extract a session ID from a message like 'delete session #42' or 'delete 42'."""
        match = re.search(r"#?(\d+)", message)
        if match:
            return int(match.group(1))
        return None

    async def _handle_delete_workout(self, message: str, user_id: int) -> str:
        """Delete a workout session — 'undo'/'delete last' or by session ID."""
        msg_lower = message.lower()
        async with db_manager.get_session() as session:
            # "undo", "delete last", or no specific ID → delete most recent
            if any(word in msg_lower for word in ["undo", "last"]) or not re.search(r"\d+", message):
                ws = await workout_session_repo.get_latest_for_user(session, user_id)
                if not ws:
                    return "Nothing to delete — no workouts found."
                session_id = ws.id
            else:
                session_id = self._parse_session_id(message)
                if not session_id:
                    return "I couldn't figure out which session to delete. Try 'undo' or 'delete session #42'."

            deleted = await workout_session_repo.delete_session(session, session_id, user_id)
            if not deleted:
                return f"Session #{session_id} not found (or not yours)."

            # Build confirmation showing what was deleted
            exercises: list[str] = []
            for s in deleted.workout_sets:
                name = s.exercise.name if s.exercise else f"exercise #{s.exercise_id}"
                if name not in exercises:
                    exercises.append(name)
            date_str = deleted.date.strftime("%b %d")
            ex_str = ", ".join(exercises) if exercises else "no exercises"
            return f"Deleted session #{deleted.id} ({date_str}): {ex_str} — {len(deleted.workout_sets)} sets removed."

    @staticmethod
    def _extract_repeat_note(message: str) -> str | None:
        """Strip trigger words from a repeat message; remainder becomes the note."""
        stripped = re.sub(
            r"\b(same as last time|repeat last|same thing|again|repeat)\b",
            "",
            message,
            flags=re.IGNORECASE,
        ).strip(" ,.-;:")
        return stripped or None

    async def _handle_repeat_last(self, message: str, user_id: int) -> str:
        """Repeat the user's most recent workout session."""
        new_note = self._extract_repeat_note(message)

        async with db_manager.get_session() as session:
            last = await workout_session_repo.get_latest_for_user(session, user_id)
            if not last or not last.workout_sets:
                return "Nothing to repeat — no previous workouts found."

            # Create new session mirroring the old one
            new_ws = await workout_session_repo.create(
                session,
                obj_in={"date": datetime.now(), "notes": f"Repeat of session #{last.id}", "user_id": user_id},
            )

            logged: list[str] = []
            for old_set in sorted(last.workout_sets, key=lambda s: (s.exercise_id, s.set_number)):
                await workout_set_repo.create(
                    session,
                    obj_in={
                        "session_id": new_ws.id,
                        "exercise_id": old_set.exercise_id,
                        "set_number": old_set.set_number,
                        "reps": old_set.reps,
                        "weight": old_set.weight,
                        "weight_unit": old_set.weight_unit,
                        "duration_minutes": old_set.duration_minutes,
                        "distance": old_set.distance,
                        "raw_exercise_name": old_set.raw_exercise_name if hasattr(old_set, "raw_exercise_name") else None,
                        "notes": new_note,  # new note (if any), never carry over old
                    },
                )
                name = old_set.exercise.name if old_set.exercise else f"exercise #{old_set.exercise_id}"
                if old_set.duration_minutes:
                    parts = [f"{old_set.duration_minutes} min"]
                    if old_set.distance:
                        parts.append(f"{old_set.distance} mi")
                    line = f"  {name}: {', '.join(parts)}"
                else:
                    weight_str = f"{old_set.weight} {old_set.weight_unit}" if old_set.weight else "bodyweight"
                    line = f"  {name}: set {old_set.set_number} - {old_set.reps} reps @ {weight_str}"
                if new_note:
                    line += f" — note: {new_note}"
                logged.append(line)

        header = f"Repeated session #{last.id} → new session #{new_ws.id}:" if self._verbose else "Repeated last workout:"
        return "\n".join([header] + logged)

    async def _handle_view_stats(self, user_id: int) -> str:
        async with db_manager.get_session() as session:
            sessions = await workout_session_repo.get_latest(session, user_id, limit=5)
            all_sets = await workout_set_repo.get_by_user(session, user_id, limit=1000)

            if not sessions:
                return "No workouts logged yet. Tell me about a workout to get started!"

            total_volume = sum((s.weight or 0) * (s.reps or 0) for s in all_sets)
            lines = [
                "Workout Stats:",
                f"  Sessions: {len(sessions)} (recent)",
                f"  Total sets: {len(all_sets)}",
                f"  Total volume: {total_volume:.0f} lbs",
                "",
                "Recent:",
            ]
            for ws in sessions[:5]:
                sets = await workout_set_repo.get_by_session(session, ws.id)
                exercise_names: list[str] = []
                for s in sets:
                    name = s.exercise.name if s.exercise else f"exercise #{s.exercise_id}"
                    if name not in exercise_names:
                        exercise_names.append(name)
                date_str = ws.date.strftime("%b %d")
                exercises_str = (
                    ", ".join(exercise_names) if exercise_names else "no exercises"
                )
                if self._verbose:
                    lines.append(
                        f"  #{ws.id} ({date_str}): {exercises_str} - {len(sets)} sets"
                    )
                else:
                    lines.append(f"  {date_str}: {exercises_str} ({len(sets)} sets)")

            return "\n".join(lines)

    async def _handle_coaching(self, message: str, intent, user_id: int) -> str:
        async with db_manager.get_session() as session:
            context = await build_coaching_context(session, intent, message, user_id)
            return await self._llm.generate_coaching_response(message, context)
