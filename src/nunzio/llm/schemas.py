"""LLM schemas for structured workout data extraction and conversation management."""

import datetime
from typing import Literal, Optional, List

from pydantic import BaseModel, Field


class UserIntent(BaseModel):
    """User intent classification with exercise/muscle group extraction."""
    intent: Literal["log_workout", "view_stats", "list_workouts", "coaching", "delete_workout", "repeat_last"] = Field(
        description="Primary user intention"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for intent classification (0.0-1.0)",
    )
    stats_type: Optional[Literal["overview", "prs", "exercise_history", "volume", "consistency"]] = Field(
        default=None,
        description="Sub-type for view_stats intent: overview (recent workouts), prs (personal records), exercise_history (history for a specific exercise), volume (weekly volume trends), consistency (workout frequency/streak)",
    )
    mentioned_exercises: List[str] = Field(
        default_factory=list,
        description="Exercise names mentioned in the message",
    )
    mentioned_muscle_groups: List[str] = Field(
        default_factory=list,
        description="Muscle groups mentioned in the message",
    )


class ExerciseSet(BaseModel):
    """Individual exercise set within a workout."""
    exercise_name: str = Field(
        description="Name of the exercise (e.g., 'Bench Press', 'Squat', 'Running')"
    )
    set_number: int = Field(
        default=1,
        description="Set number (use 1 for cardio)",
    )
    reps: Optional[int] = Field(
        default=None,
        description="Number of repetitions (None for cardio exercises)",
    )
    weight: Optional[float] = Field(
        default=None,
        description="Weight in pounds (None for cardio/bodyweight)",
    )
    unit: Literal["lbs", "kg", "bodyweight"] = Field(
        default="lbs",
        description="Weight unit",
    )
    duration_minutes: Optional[int] = Field(
        default=None,
        description="Duration in minutes (for cardio exercises like running, cycling, rowing, elliptical)",
    )
    distance: Optional[float] = Field(
        default=None,
        description="Distance covered (for cardio — miles or km)",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about form or effort",
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
    date: Optional[datetime.date] = Field(
        default=None,
        description="Workout date in YYYY-MM-DD format if the user specifies when they worked out (e.g. 'yesterday', 'on Monday', 'Feb 15'). Null if no date is mentioned.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Workout session notes"
    )
    perceived_exertion: Optional[int] = Field(
        default=None,
        description="RPE scale 1-10"
    )
