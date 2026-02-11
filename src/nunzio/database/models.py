"""SQLAlchemy async models for Nunzio workout tracking."""

from datetime import datetime
from typing import List

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
        DateTime, nullable=False, default=datetime.utcnow
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


class WorkoutSession(Base):
    """Represents a workout session containing multiple sets."""

    __tablename__ = "workout_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    workout_sets: Mapped[List["WorkoutSet"]] = relationship(
        "WorkoutSet", back_populates="session", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workout_sessions_date", "date"),
        Index("idx_workout_sessions_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<WorkoutSession(id={self.id}, date='{self.date.isoformat()}')>"


class WorkoutSet(Base):
    """Represents a single set of an exercise within a workout session."""

    __tablename__ = "workout_sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workout_sessions.id"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exercises.id"), nullable=False
    )
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    weight_unit: Mapped[str] = mapped_column(String(10), nullable=False, default="lbs")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    session: Mapped["WorkoutSession"] = relationship(
        "WorkoutSession", back_populates="workout_sets"
    )
    exercise: Mapped["Exercise"] = relationship(
        "Exercise", back_populates="workout_sets"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workout_sets_session", "session_id"),
        Index("idx_workout_sets_exercise", "exercise_id"),
        Index("idx_workout_sets_session_exercise", "session_id", "exercise_id"),
    )

    def __repr__(self) -> str:
        weight_str = f"{self.weight} {self.weight_unit}" if self.weight is not None else "bodyweight"
        return (
            f"<WorkoutSet(id={self.id}, session_id={self.session_id}, "
            f"exercise_id={self.exercise_id}, set_number={self.set_number}, "
            f"reps={self.reps}, weight={weight_str})>"
        )


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
