"""SQLAlchemy async models for Nunzio workout tracking."""

from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NYC_TZ = ZoneInfo("America/New_York")


def _now_nyc() -> datetime:
    return datetime.now(NYC_TZ).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class Exercise(Base):
    """Represents an exercise that can be performed in a workout."""

    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    muscle_group: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    guidance: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now_nyc
    )

    # Relationships
    workout_sets: Mapped[List["WorkoutSet"]] = relationship(
        "WorkoutSet", back_populates="exercise", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_exercises_muscle_group", "muscle_group"),
        Index("idx_exercises_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Exercise(id={self.id}, name='{self.name}', muscle_group='{self.muscle_group}')>"


class WorkoutSet(Base):
    """Represents a single set of an exercise. Flat model — no session indirection."""

    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    set_date: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now_nyc)
    exercise_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exercises.id"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="lbs")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_exercise_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now_nyc
    )

    # Relationships
    exercise: Mapped["Exercise"] = relationship(
        "Exercise", back_populates="workout_sets"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workout_sets_user_id", "user_id"),
        Index("idx_workout_sets_batch_id", "batch_id"),
        Index("idx_workout_sets_set_date", "set_date"),
        Index("idx_workout_sets_exercise", "exercise_id"),
        Index("idx_workout_sets_user_batch", "user_id", "batch_id"),
    )

    def __repr__(self) -> str:
        weight_str = f"{self.weight} {self.weight_unit}" if self.weight is not None else "bodyweight"
        return (
            f"<WorkoutSet(id={self.id}, batch_id={self.batch_id}, "
            f"exercise_id={self.exercise_id}, set_number={self.set_number}, "
            f"reps={self.reps}, weight={weight_str})>"
        )


class MessageLog(Base):
    """Log of every user message and how Nunzio interpreted it."""

    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    raw_message: Mapped[str] = mapped_column(Text, nullable=False)
    classified_intent: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    extracted_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now_nyc
    )

    __table_args__ = (
        Index("idx_message_log_user_id", "user_id"),
        Index("idx_message_log_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MessageLog(id={self.id}, intent='{self.classified_intent}', confidence={self.confidence})>"


class BodyWeight(Base):
    """A single body weight reading."""

    __tablename__ = "body_weight"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(10), nullable=False, default="lbs")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now_nyc
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_now_nyc
    )

    __table_args__ = (
        Index("idx_body_weight_user_id", "user_id"),
        Index("idx_body_weight_recorded_at", "recorded_at"),
    )

    def __repr__(self) -> str:
        return f"<BodyWeight(id={self.id}, user_id={self.user_id}, weight={self.weight} {self.unit})>"


class TrainingPrinciple(Base):
    """Coaching knowledge for prompt injection — progression rules, rep ranges, etc."""

    __tablename__ = "training_principles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    __table_args__ = (
        Index("idx_training_principles_category", "category"),
        Index("idx_training_principles_priority", "priority"),
    )

    def __repr__(self) -> str:
        return f"<TrainingPrinciple(id={self.id}, category='{self.category}', title='{self.title}')>"
