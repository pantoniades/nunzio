"""Async LLM client with Instructor integration for structured data extraction."""

import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
import instructor
from openai import AsyncOpenAI
from tenacity import AsyncRetrying, retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..config import config
from .schemas import (
    BodyWeightData,
    EditSetData,
    UserIntent,
    WorkoutData,
)

logger = logging.getLogger(__name__)


def _instructor_retries(label: str, attempts: int = 3) -> AsyncRetrying:
    """Build a tenacity AsyncRetrying that logs each instructor JSON-parse retry."""

    def _log(retry_state):
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        logger.warning(
            "Instructor retry for %s (attempt %d): %s",
            label, retry_state.attempt_number, exc,
        )

    return AsyncRetrying(stop=stop_after_attempt(attempts), after=_log)


class LLMClient:
    """Manages LLM communication via OpenAI-compatible API + Instructor."""

    def __init__(self) -> None:
        self._client: Optional[AsyncOpenAI] = None
        self._instructor_client: Optional[instructor.AsyncInstructor] = None
        self.model_override: str | None = None

    async def initialize(self) -> None:
        """Initialize the LLM client."""
        self._client = AsyncOpenAI(
            base_url=f"{config.llm.base_url}/v1",
            api_key="not-needed",
        )
        self._instructor_client = instructor.from_openai(
            self._client, mode=instructor.Mode.JSON
        )

    async def _get_active_model(self) -> str:
        """Check llama-swap /running endpoint and use the currently loaded model if one is ready."""
        try:
            async with httpx.AsyncClient(timeout=2) as http:
                resp = await http.get(f"{config.llm.base_url}/running")
                resp.raise_for_status()
                data = resp.json()
                for entry in data:
                    if entry.get("state") == "ready":
                        model = entry["model"]
                        if model != config.llm.model:
                            self.model_override = model
                        else:
                            self.model_override = None
                        return model
        except Exception:
            logger.debug("Could not check /running endpoint, using configured model")
        self.model_override = None
        return config.llm.model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    async def classify_intent(self, message: str) -> UserIntent:
        """Classify user intent with confidence scoring."""
        if not self._instructor_client:
            await self.initialize()

        today = datetime.now(ZoneInfo("America/New_York"))
        today_str = today.strftime("%A, %B %-d, %Y")

        prompt = f"""
        Analyze this user message and classify their primary intent:

        Today is {today_str}.

        MESSAGE: "{message}"

        POSSIBLE INTENTS:
        - log_workout: User is reporting a workout they already did (past tense: "I did", "I benched", etc.)
        - log_weight: User is reporting their body weight ("weighed 185", "weight is 82 kg", "191.4 lbs", "body weight 180")
        - view_stats: User wants to see their workout history or statistics
        - list_workouts: User wants to see a list of recent workout sessions with IDs ("last workouts", "list workouts", "list sessions", "show sessions")
        - delete_workout: User wants to undo, delete, or remove a logged workout ("undo", "delete last", "remove session #42", "that's wrong")
        - repeat_last: User wants to log the same workout again ("again", "repeat last", "same as last time", "another set", "one more", "one more set", "same thing")
        - edit_set: User wants to fix, change, or correct a value on an already-logged set ("change reps to 12", "fix weight to 185", "edit last set", "update bench press to 8 reps", "correct #42 set 3 to 200 lbs")
        - coaching: User wants advice, recommendations, questions about training, or anything else

        For view_stats intent, also classify the stats_type:
        - "prs": User wants personal records ("show my PRs", "what are my best lifts")
        - "exercise_history": User asks about a specific exercise's history ("bench press history", "how has my squat been")
        - "volume": User asks about training volume ("how much volume this week", "weekly volume")
        - "consistency": User asks about workout frequency/consistency ("how consistent am I", "how often do I work out", "workout streak")
        - "weight": User asks about body weight history or trend ("what's my weight", "weight trend", "weight history")
        - "last_session": User asks about their last/most recent workout ("last time", "last workout", "what did I do last")
        - "overview": General stats request or anything else ("show my stats", "how have my workouts been")

        DATE FILTERING for view_stats and list_workouts:
        - If the user mentions a date or time range ("today", "yesterday", "this week", "last Monday", "on March 3"),
          resolve it to concrete dates and set stats_date (and stats_end_date for ranges).
        - "today" → stats_date = today's date
        - "yesterday" → stats_date = yesterday's date
        - "this week" → stats_date = Monday of this week, stats_end_date = today
        - "last week" → stats_date = Monday of last week, stats_end_date = Sunday of last week
        - For "last time" / "last workout" / "what did I do last": use stats_type="last_session", leave dates null.
        - If no date is mentioned, leave stats_date and stats_end_date null.

        Also extract any exercise names and muscle groups mentioned in the message.
        Exercise names should match common names like "Bench Press", "Squat", "Deadlift", etc.
        Muscle groups should match: chest, back, shoulders, legs, biceps, triceps, core, cardio, flexibility.

        Return the intent, confidence score, stats_type (only for view_stats), stats_date, stats_end_date, any mentioned exercises, and any mentioned muscle groups.
        """

        try:
            model = await self._get_active_model()
            result = await self._instructor_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_model=UserIntent,
                temperature=0.1,
                max_retries=_instructor_retries("classify_intent"),
            )
            return result

        except Exception:
            logger.warning("LLM classification failed, using keyword fallback", exc_info=True)
            # Fallback classification
            message_lower = message.lower()
            if any(
                word in message_lower
                for word in ["weigh", "weighed", "body weight", "bw"]
            ):
                return UserIntent(intent="log_weight", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["edit", "change", "fix", "correct", "update"]
            ):
                return UserIntent(intent="edit_set", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["undo", "delete", "remove"]
            ):
                return UserIntent(intent="delete_workout", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["again", "repeat", "same as last", "another", "one more", "same thing"]
            ):
                return UserIntent(intent="repeat_last", confidence=0.7)
            elif any(
                word in message_lower
                for word in ["log", "did", "worked out", "i benched", "sets", "reps"]
            ):
                return UserIntent(intent="log_workout", confidence=0.6)
            elif any(
                phrase in message_lower
                for phrase in ["last workouts", "list workouts", "list sessions", "show sessions"]
            ):
                return UserIntent(intent="list_workouts", confidence=0.9)
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

        today = datetime.now(ZoneInfo("America/New_York"))
        today_str = today.strftime("%A, %B %-d, %Y")

        prompt = f"""
        Extract workout details from this message. Be precise with numbers.

        Today is {today_str}.

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
        - EXERCISE NAMES: Include movement qualifiers that change which exercise it is.
          Words like incline, decline, seated, low, cable, overhead, reverse, Bulgarian,
          Romanian, sumo, close-grip, wide-grip, lateral, rear delt, face, scapular
          are PART OF THE NAME, not notes.
          Examples:
          "incline bench press" → exercise_name="Incline Bench Press"
          "low row" → exercise_name="Low Row"
          "seated row" → exercise_name="Seated Row"
          "Romanian deadlift" → exercise_name="Romanian Deadlift"
          "rear delt fly" → exercise_name="Rear Delt Fly"
        - NOTES: Only subjective observations (pain, effort, form, mood) and equipment details
          (band color, cable attachment, tempo, machine setting) go in the `notes` field.
          Examples:
          "bench press at 100 lb shoulder sore" → exercise_name="Bench Press", notes="shoulder sore"
          "purple band chest pull" → exercise_name="Chest Pull", notes="purple band"
          "incline press felt easy" → exercise_name="Incline Press", notes="felt easy"
        - BARE NUMBERS: When a single number follows an exercise name with no "reps", "sets",
          or "x" notation (e.g. "face pull 30", "bench 185"), use exercise context to decide:
          for exercises typically done with external weight (cable, barbell, dumbbell, machine),
          treat the number as weight in pounds. For bodyweight exercises (pushups, pull-ups,
          sit-ups), treat it as reps.
          Examples:
          "face pull 30" → weight=30, reps=null (cable exercise → weight)
          "bench 185" → weight=185, reps=null (barbell exercise → weight)
          "pushups 30" → weight=null, reps=30 (bodyweight exercise → reps)
        - DATE: If the user mentions when they did the workout (e.g. "yesterday", "on Monday",
          "last Friday", "Feb 15", "2 days ago"), resolve it to a concrete date and set the
          `date` field in YYYY-MM-DD format. If no date is mentioned, leave `date` as null.
        """

        try:
            model = await self._get_active_model()
            result = await self._instructor_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_model=WorkoutData,
                temperature=0.1,
                max_retries=_instructor_retries("extract_workout"),
            )
            if result.exercises:
                return result
            return None

        except Exception:
            logger.error("Workout extraction failed", exc_info=True)
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def extract_body_weight_data(self, message: str) -> BodyWeightData | None:
        """Extract body weight data from user message."""
        if not self._instructor_client:
            await self.initialize()

        today = datetime.now(ZoneInfo("America/New_York"))
        today_str = today.strftime("%A, %B %-d, %Y")

        prompt = f"""
        Extract the body weight reading from this message.

        Today is {today_str}.

        MESSAGE: "{message}"

        IMPORTANT:
        - Extract the numeric weight value and unit (lbs or kg). Default to lbs if not specified.
        - If the user mentions when they weighed ("yesterday", "this morning", "on Monday"),
          resolve it to a concrete date in YYYY-MM-DD format. Otherwise leave date as null.
        - Any context about the weigh-in (morning, post-workout, fasted, after dinner) goes in notes.
        """

        try:
            model = await self._get_active_model()
            result = await self._instructor_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_model=BodyWeightData,
                temperature=0.1,
                max_retries=_instructor_retries("extract_body_weight"),
            )
            return result
        except Exception:
            logger.error("Body weight extraction failed", exc_info=True)
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def extract_edit_set_data(self, message: str) -> EditSetData | None:
        """Extract edit-set instructions from user message."""
        if not self._instructor_client:
            await self.initialize()

        prompt = f"""
        Extract what the user wants to edit about a previously logged workout set.

        MESSAGE: "{message}"

        IMPORTANT:
        - Identify WHICH set(s) to edit:
          - "last set" / "last workout" → is_last=true
          - "#42 set 3" / "batch 42 set 3" → batch_id=42, set_number=3
          - "#42" (no set number) → batch_id=42, set_number=null (edit all sets in batch)
          - "change bench press to 12 reps" → exercise_name="Bench Press", is_last=false
        - Identify WHAT to change — only set the new_* fields the user explicitly mentions:
          - "change reps to 12" → new_reps=12
          - "fix weight to 185" → new_weight=185
          - "update to 8 reps at 200 lbs" → new_reps=8, new_weight=200
          - "change notes to felt easy" → new_notes="felt easy"
        - Leave new_* fields as null when the user does NOT mention them.
        - Default weight unit is lbs unless specified otherwise.
        """

        try:
            model = await self._get_active_model()
            result = await self._instructor_client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_model=EditSetData,
                temperature=0.1,
                max_retries=_instructor_retries("extract_edit_set"),
            )
            return result
        except Exception:
            logger.error("Edit set extraction failed", exc_info=True)
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
            model = await self._get_active_model()
            response = await self._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.7,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error("Coaching response generation failed", exc_info=True)
            return f"Sorry, I couldn't generate a response right now. ({e})"

    async def close(self) -> None:
        """Clean up LLM client resources."""
        if self._client:
            await self._client.close()


# Global LLM client instance
llm_client = LLMClient()
