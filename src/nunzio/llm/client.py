"""Async Ollama client with Instructor integration for structured data extraction."""

from typing import Optional

import instructor
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import config
from .schemas import (
    UserIntent,
    WorkoutData,
)


class LLMClient:
    """Manages LLM communication via Ollama's OpenAI-compatible API + Instructor."""

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._instructor_client: Optional[instructor.AsyncInstructor] = None

    async def initialize(self) -> None:
        """Initialize the LLM client."""
        self._client = AsyncOpenAI(
            base_url=f"{config.llm.base_url}/v1",
            api_key="ollama",
        )
        self._instructor_client = instructor.from_openai(
            self._client, mode=instructor.Mode.JSON
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    async def classify_intent(self, message: str) -> UserIntent:
        """Classify user intent with confidence scoring."""
        if not self._instructor_client:
            await self.initialize()

        prompt = f"""
        Analyze this user message and classify their primary intent:

        MESSAGE: "{message}"

        POSSIBLE INTENTS:
        - log_workout: User is reporting a workout they already did (past tense: "I did", "I benched", etc.)
        - view_stats: User wants to see their workout history or statistics
        - delete_workout: User wants to undo, delete, or remove a logged workout ("undo", "delete last", "remove session #42", "that's wrong")
        - repeat_last: User wants to log the same workout again ("again", "repeat last", "same as last time")
        - coaching: User wants advice, recommendations, questions about training, or anything else

        Also extract any exercise names and muscle groups mentioned in the message.
        Exercise names should match common names like "Bench Press", "Squat", "Deadlift", etc.
        Muscle groups should match: chest, back, shoulders, legs, biceps, triceps, core, cardio, flexibility.

        Return the intent, confidence score, any mentioned exercises, and any mentioned muscle groups.
        """

        try:
            result = await self._instructor_client.chat.completions.create(
                model=config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                response_model=UserIntent,
                temperature=0.1,
                max_retries=2,
            )
            return result

        except Exception:
            # Fallback classification
            message_lower = message.lower()
            if any(
                word in message_lower
                for word in ["undo", "delete", "remove"]
            ):
                return UserIntent(intent="delete_workout", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["again", "repeat", "same as last"]
            ):
                return UserIntent(intent="repeat_last", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["log", "did", "worked out", "i benched", "sets", "reps"]
            ):
                return UserIntent(intent="log_workout", confidence=0.6)
            elif any(
                word in message_lower
                for word in ["stats", "progress", "history", "show"]
            ):
                return UserIntent(intent="view_stats", confidence=0.9)
            else:
                return UserIntent(intent="coaching", confidence=0.5)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def extract_workout_data(self, message: str) -> WorkoutData | None:
        """Extract structured workout data from user message."""
        if not self._instructor_client:
            await self.initialize()

        prompt = f"""
        Extract workout details from this message. Be precise with numbers:

        MESSAGE: "{message}"

        IMPORTANT:
        - Exercise names should match common exercises
        - For strength exercises: extract set_number, reps, and weight
        - When the user says "N sets", you MUST return N separate ExerciseSet objects,
          one per set, with set_number 1 through N. Do NOT return a single object with
          set_number=N.
          Examples:
          "2 sets of 10 rear delt fly at 40 lbs" → TWO ExerciseSet objects:
            {{set_number: 1, reps: 10, weight: 40}} and {{set_number: 2, reps: 10, weight: 40}}
          "did 3 sets of 8 curls 30 lbs" → THREE ExerciseSet objects:
            {{set_number: 1, reps: 8, weight: 30}}, {{set_number: 2, reps: 8, weight: 30}},
            {{set_number: 3, reps: 8, weight: 30}}
        - For cardio exercises (running, cycling, elliptical, rowing, swimming, etc.):
          use duration_minutes for time and distance if mentioned. Leave reps as null.
          "20 minutes on the bike" → duration_minutes=20, reps=null
          "ran 3 miles in 25 min" → duration_minutes=25, distance=3.0, reps=null
        - Weight in pounds unless specified otherwise
        - If unclear, make reasonable assumptions
        - NOTES: Any subjective observations (pain, effort, form, mood) or equipment/variant
          modifiers (band color, grip width, cable attachment, tempo) go in the `notes` field.
          Keep the exercise name clean — just the base movement.
          Examples:
          "bench press at 100 lb shoulder sore" → exercise_name="Bench Press", notes="shoulder sore"
          "purple band chest pull" → exercise_name="Chest Pull", notes="purple band"
          "wide grip lat pulldown felt easy" → exercise_name="Lat Pulldown", notes="wide grip, felt easy"
        """

        try:
            result = await self._instructor_client.chat.completions.create(
                model=config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                response_model=WorkoutData,
                temperature=0.1,
                max_retries=2,
            )
            if result.exercises:
                return result
            return None

        except Exception as e:
            print(f"Workout extraction failed: {e}")
            return None

    async def generate_coaching_response(self, message: str, context: str) -> str:
        """Generate a coaching response using context (history + guidance + principles)."""
        if not self._client:
            await self.initialize()

        system_prompt = (
            "You are Nunzio, a direct workout coach. Give specific, actionable advice "
            "with exact sets, reps, and weights.\n\n"
            "RULES:\n"
            "- When the user's history is provided, base your advice on their actual numbers\n"
            "- Prescribe specific weights: \"3x10 @ 35/40/40 lbs\" not \"moderate weight\"\n"
            "- Progressive overload: if all target reps were hit last time, suggest +5 lbs "
            "for barbell compounds, +5 lbs (per hand) for dumbbells, +2.5 lbs for isolation\n"
            "- If they missed reps or stalled, suggest same weight or a deload\n"
            "- For cardio: progress by adding duration or intervals, not weight. Reference "
            "their recent times/distances. Suggest specific session plans (\"30 min steady "
            "state at conversational pace\" or \"8x30s sprints with 90s rest\")\n"
            "- Keep responses concise — a prescription and brief rationale, not an essay\n"
            "- If there's not enough history, say so and give a conservative starting point\n"
            "- Reference the exercise guidance and training principles provided in context"
        )

        user_content = message
        if context:
            user_content = f"{context}\n\n---\nUSER QUESTION: {message}"

        try:
            response = await self._client.chat.completions.create(
                model=config.llm.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Sorry, I couldn't generate a response right now. ({e})"

    async def close(self) -> None:
        """Clean up LLM client resources."""
        if self._client:
            await self._client.close()


# Global LLM client instance
llm_client = LLMClient()
