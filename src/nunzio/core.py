"""Core message processing — shared by CLI and Telegram bot."""

from datetime import datetime

from .database.connection import db_manager
from .database.repository import exercise_repo, workout_session_repo, workout_set_repo
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

    async def process(self, message: str) -> str:
        """Classify intent and route to the appropriate handler."""
        intent = await self._llm.classify_intent(message)

        if intent.intent == "log_workout" and intent.confidence > 0.5:
            return await self._handle_log_workout(message)
        elif intent.intent == "view_stats":
            return await self._handle_view_stats()
        else:
            return await self._handle_coaching(message, intent)

    async def _handle_log_workout(self, message: str) -> str:
        workout_data = await self._llm.extract_workout_data(message)
        if not workout_data or not workout_data.exercises:
            return "I couldn't extract workout details. Try something like: '3 sets of bench press at 185 lbs, 10 reps'"

        async with db_manager.get_session() as session:
            ws = await workout_session_repo.create(
                session,
                obj_in={"date": datetime.now(), "notes": message},
            )

            logged: list[str] = []
            for ex_set in workout_data.exercises:
                exercise = await exercise_repo.get_by_name(session, ex_set.exercise_name)
                if not exercise:
                    candidates = await exercise_repo.search(
                        session, ex_set.exercise_name, limit=1
                    )
                    if candidates:
                        exercise = candidates[0]
                    else:
                        exercise = await exercise_repo.create(
                            session,
                            obj_in={
                                "name": ex_set.exercise_name,
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
                    },
                )

                if ex_set.duration_minutes:
                    parts = [f"{ex_set.duration_minutes} min"]
                    if ex_set.distance:
                        parts.append(f"{ex_set.distance} mi")
                    logged.append(f"  {exercise.name}: {', '.join(parts)}")
                else:
                    weight_str = (
                        f"{ex_set.weight} {ex_set.unit}" if ex_set.weight else "bodyweight"
                    )
                    logged.append(
                        f"  {exercise.name}: set {ex_set.set_number} - {ex_set.reps} reps @ {weight_str}"
                    )

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

    async def _handle_view_stats(self) -> str:
        async with db_manager.get_session() as session:
            sessions = await workout_session_repo.get_latest(session, limit=5)
            all_sets = await workout_set_repo.get_multi(session, limit=1000)

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

    async def _handle_coaching(self, message: str, intent) -> str:
        async with db_manager.get_session() as session:
            context = await build_coaching_context(session, intent, message)
            return await self._llm.generate_coaching_response(message, context)
