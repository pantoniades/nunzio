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
        self._instructor_client = instructor.from_openai(self._client)

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
        - log_workout: User wants to record a workout they did
        - get_recommendation: User wants exercise or workout suggestions
        - chat: User wants general conversation
        - view_stats: User wants to see their workout statistics

        Return only the intent and confidence score. Be conservative.
        """

        try:
            result = await self._instructor_client.chat.completions.create(
                model=config.llm.model,
                messages=[{"role": "user", "content": prompt}],
                response_model=UserIntent,
                temperature=0.1,
                max_retries=2,
            )
            result.requires_clarification = result.confidence < 0.7
            return result

        except Exception:
            # Fallback classification
            message_lower = message.lower()
            if any(
                word in message_lower
                for word in ["log", "did", "worked out", "gym", "sets", "reps"]
            ):
                return UserIntent(
                    intent="log_workout",
                    confidence=0.6,
                    requires_clarification=True,
                )
            elif any(
                word in message_lower
                for word in ["recommend", "suggest", "exercise"]
            ):
                return UserIntent(intent="get_recommendation", confidence=0.8)
            elif any(
                word in message_lower
                for word in ["stats", "progress", "history", "show"]
            ):
                return UserIntent(intent="view_stats", confidence=0.9)
            else:
                return UserIntent(
                    intent="chat", confidence=0.5, requires_clarification=True
                )

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
        - Extract exact set numbers, reps, and weights
        - Weight in pounds unless specified otherwise
        - If unclear, make reasonable assumptions but note uncertainty
        - For cardio, extract duration instead of sets/reps
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

    async def close(self) -> None:
        """Clean up LLM client resources."""
        if self._client:
            await self._client.close()


# Global LLM client instance
llm_client = LLMClient()
