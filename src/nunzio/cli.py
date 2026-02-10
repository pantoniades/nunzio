"""Interactive CLI for Nunzio workout assistant."""

import asyncio
import sys
from datetime import datetime

from .database.connection import db_manager
from .database.repository import exercise_repo, workout_session_repo, workout_set_repo
from .llm.client import LLMClient


class NunzioCLI:
    """CLI that routes natural language through LLM extraction to DB persistence."""

    def __init__(self) -> None:
        self._llm = LLMClient()

    async def initialize(self) -> None:
        await db_manager.initialize()
        await self._llm.initialize()
        print("Connected to database and LLM.")

    async def close(self) -> None:
        await self._llm.close()
        await db_manager.close()

    async def run(self) -> None:
        await self.initialize()
        print("Nunzio Workout Assistant")
        print("Type 'help' for commands or 'exit' to quit.")
        print("-" * 50)

        while True:
            try:
                user_input = input("You: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "bye"):
                    print("Goodbye!")
                    break
                if user_input.lower() == "help":
                    self._show_help()
                    continue

                response = await self._process_message(user_input)
                print(f"Nunzio: {response}")
                print("-" * 50)

            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
                continue

        await self.close()

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    async def _process_message(self, message: str) -> str:
        intent = await self._llm.classify_intent(message)
        print(f"  [intent: {intent.intent}, confidence: {intent.confidence:.2f}]")

        if intent.intent == "log_workout" and intent.confidence > 0.5:
            return await self._handle_log_workout(message)
        elif intent.intent == "view_stats":
            return await self._handle_view_stats()
        elif intent.intent == "get_recommendation":
            return await self._handle_recommendation(message)
        else:
            return self._handle_chat()

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_log_workout(self, message: str) -> str:
        workout_data = await self._llm.extract_workout_data(message)
        if not workout_data or not workout_data.exercises:
            return "I couldn't extract workout details. Try something like: '3 sets of bench press at 185 lbs, 10 reps'"

        async with db_manager.get_session() as session:
            # Create a session for this workout
            ws = await workout_session_repo.create(
                session,
                obj_in={"date": datetime.now(), "notes": message},
            )

            logged: list[str] = []
            for ex_set in workout_data.exercises:
                # Find or create the exercise
                exercise = await exercise_repo.get_by_name(session, ex_set.exercise_name)
                if not exercise:
                    # Try a fuzzy search before creating
                    candidates = await exercise_repo.search(session, ex_set.exercise_name, limit=1)
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
                    },
                )
                weight_str = f"{ex_set.weight} {ex_set.unit}" if ex_set.weight else "bodyweight"
                logged.append(f"  {exercise.name}: set {ex_set.set_number} - {ex_set.reps} reps @ {weight_str}")

        lines = [f"Logged workout (session #{ws.id}):"] + logged
        total_volume = sum(
            (s.weight or 0) * s.reps
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

            total_volume = sum((s.weight or 0) * s.reps for s in all_sets)
            lines = [
                "Workout Stats:",
                f"  Total sessions: {len(sessions)} (showing recent)",
                f"  Total sets: {len(all_sets)}",
                f"  Total volume: {total_volume:.0f} lbs",
                "",
                "Recent sessions:",
            ]
            for ws in sessions[:5]:
                sets = await workout_set_repo.get_by_session(session, ws.id)
                exercise_names: list[str] = []
                for s in sets:
                    name = s.exercise.name if s.exercise else f"exercise #{s.exercise_id}"
                    if name not in exercise_names:
                        exercise_names.append(name)
                date_str = ws.date.strftime("%Y-%m-%d %H:%M")
                exercises_str = ", ".join(exercise_names) if exercise_names else "no exercises"
                lines.append(f"  #{ws.id} ({date_str}): {exercises_str} - {len(sets)} sets")

            return "\n".join(lines)

    async def _handle_recommendation(self, message: str) -> str:
        msg_lower = message.lower()
        target_group = None
        group_keywords = {
            "chest": ["chest", "pec"],
            "back": ["back", "lat", "pull"],
            "shoulders": ["shoulder", "delt"],
            "legs": ["leg", "quad", "hamstring", "glute", "squat"],
            "biceps": ["bicep", "curl"],
            "triceps": ["tricep"],
            "core": ["core", "ab", "abs"],
            "cardio": ["cardio", "run", "conditioning"],
        }
        for group, keywords in group_keywords.items():
            if any(kw in msg_lower for kw in keywords):
                target_group = group
                break

        async with db_manager.get_session() as session:
            if target_group:
                exercises = await exercise_repo.get_by_muscle_group(session, target_group)
                if exercises:
                    lines = [f"Exercises for {target_group}:"]
                    for ex in exercises:
                        desc = f" - {ex.description}" if ex.description else ""
                        lines.append(f"  {ex.name}{desc}")
                    return "\n".join(lines)

            # Fallback: show a sampling across groups
            all_exercises = await exercise_repo.get_multi(session, limit=100)
            if not all_exercises:
                return "No exercises in the database yet. Run the seed script to populate exercises."

            by_group: dict[str, list[str]] = {}
            for ex in all_exercises:
                by_group.setdefault(ex.muscle_group, []).append(ex.name)

            lines = ["Here are some exercises by muscle group:"]
            for group, names in sorted(by_group.items()):
                sample = names[:3]
                lines.append(f"  {group}: {', '.join(sample)}")
            lines.append("\nAsk about a specific muscle group for more detail.")
            return "\n".join(lines)

    def _handle_chat(self) -> str:
        return (
            "I can help you log workouts, view stats, or suggest exercises.\n"
            "Try something like:\n"
            '  "I did 3 sets of bench press at 185 lbs"\n'
            '  "show my stats"\n'
            '  "what should I do for legs?"'
        )

    def _show_help(self) -> None:
        print(
            "Nunzio Commands:\n"
            "\n"
            "  Log a workout:\n"
            '    "I did 3 sets of bench press at 185 lbs, 10 reps"\n'
            '    "squat 5x5 at 225 lbs"\n'
            "\n"
            "  View stats:\n"
            '    "show my stats"\n'
            '    "how have my workouts been?"\n'
            "\n"
            "  Get recommendations:\n"
            '    "what should I do for chest?"\n'
            '    "suggest some leg exercises"\n'
            "\n"
            "  help  - show this message\n"
            "  exit  - quit"
        )


async def main() -> None:
    cli = NunzioCLI()
    await cli.run()


def main_sync() -> None:
    """Entry point for pyproject.toml console_scripts."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
        sys.exit(0)


if __name__ == "__main__":
    main_sync()
