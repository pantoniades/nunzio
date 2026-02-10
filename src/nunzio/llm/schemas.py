"""LLM schemas for structured workout data extraction and conversation management."""

from datetime import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, Field


class UserIntent(BaseModel):
    """User intent classification with confidence scoring."""
    intent: Literal[
        "log_workout", 
        "get_recommendation", 
        "chat", 
        "view_stats"
    ] = Field(description="Primary user intention")
    confidence: float = Field(
        ge=0.0, 
        le=1.0, 
        description="Confidence score for intent classification (0.0-1.0)"
    )
    requires_clarification: bool = Field(
        default=False,
        description="Whether user message needs clarification"
    )


class ExerciseSet(BaseModel):
    """Individual exercise set within a workout."""
    exercise_name: str = Field(
        description="Name of the exercise (e.g., 'Bench Press', 'Squat')"
    )
    set_number: int = Field(
        description="Set number"
    )
    reps: int = Field(
        description="Number of repetitions"
    )
    weight: Optional[float] = Field(
        default=None,
        description="Weight in pounds"
    )
    unit: Literal["lbs", "kg", "bodyweight"] = Field(
        default="lbs",
        description="Weight unit"
    )
    rest_time: Optional[int] = Field(
        default=None,
        description="Rest time in seconds"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about form or effort"
    )


class WorkoutData(BaseModel):
    """Complete workout session data."""
    exercises: List[ExerciseSet] = Field(
        description="List of exercises performed"
    )
    workout_type: Optional[str] = Field(
        default=None,
        description="Type of workout (e.g., 'strength', 'cardio', 'hiit')"
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Workout duration in minutes"
    )
    date: Optional[datetime] = Field(
        default=None,
        description="Workout date if specified"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Workout session notes"
    )
    perceived_exertion: Optional[int] = Field(
        default=None,
        description="RPE scale 1-10"
    )


class ConversationResponse(BaseModel):
    """Response structure for bot replies."""
    response_text: str = Field(
        description="Text response to user"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in response accuracy"
    )
    requires_clarification: bool = Field(
        default=False,
        description="Whether user needs to provide more information"
    )
    suggestions: List[str] = Field(
        default_factory=list,
        description="Follow-up suggestions for user"
    )
    next_intent: Optional[Literal[
        "log_workout",
        "get_recommendation", 
        "view_stats",
        "clarify_workout",
        "confirm_workout"
    ]] = Field(
        default=None,
        description="Expected next user action"
    )


class ClarificationRequest(BaseModel):
    """Request for user clarification."""
    missing_fields: List[str] = Field(
        description="What information is still needed"
    )
    suggested_format: str = Field(
        description="Suggested format for user's next message"
    )
    example_response: str = Field(
        description="Example of how user should respond"
    )