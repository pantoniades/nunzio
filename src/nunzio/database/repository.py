"""Async repository pattern implementation for database operations."""

from typing import Generic, List, Optional, Type, TypeVar, Union

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Base, Exercise, TrainingPrinciple, WorkoutSession, WorkoutSet

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType")
UpdateSchemaType = TypeVar("UpdateSchemaType")


class BaseRepository(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    """Base repository with async CRUD operations."""

    def __init__(self, model: Type[ModelType]) -> None:
        self.model = model

    async def get(self, session: AsyncSession, id: int) -> Optional[ModelType]:
        """Get a single record by ID."""
        stmt = select(self.model).where(self.model.id == id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_multi(
        self, session: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> List[ModelType]:
        """Get multiple records with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self, session: AsyncSession, *, obj_in: CreateSchemaType
    ) -> ModelType:
        """Create a new record."""
        if isinstance(obj_in, dict):
            obj_data = obj_in
        else:
            obj_data = (
                obj_in.model_dump()
                if hasattr(obj_in, "model_dump")
                else obj_in.__dict__
            )

        db_obj = self.model(**obj_data)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def update(
        self,
        session: AsyncSession,
        *,
        db_obj: ModelType,
        obj_in: Union[UpdateSchemaType, dict],
    ) -> ModelType:
        """Update an existing record."""
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = (
                obj_in.model_dump(exclude_unset=True)
                if hasattr(obj_in, "model_dump")
                else obj_in.__dict__
            )

        for field, value in update_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        await session.flush()
        await session.refresh(db_obj)
        return db_obj

    async def delete(self, session: AsyncSession, *, id: int) -> Optional[ModelType]:
        """Delete a record by ID."""
        obj = await self.get(session, id=id)
        if obj:
            await session.delete(obj)
            await session.flush()
        return obj

    async def delete_all(self, session: AsyncSession) -> int:
        """Delete all records (use with caution)."""
        stmt = delete(self.model)
        result = await session.execute(stmt)
        await session.flush()
        return result.rowcount


class ExerciseRepository(BaseRepository[Exercise, dict, dict]):
    """Repository for Exercise operations."""

    async def get_by_name(self, session: AsyncSession, name: str) -> Optional[Exercise]:
        """Get an exercise by name."""
        stmt = select(Exercise).where(Exercise.name == name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_muscle_group(
        self, session: AsyncSession, muscle_group: str
    ) -> List[Exercise]:
        """Get exercises by muscle group."""
        stmt = select(Exercise).where(Exercise.muscle_group == muscle_group)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def search(
        self, session: AsyncSession, query: str, *, limit: int = 20
    ) -> List[Exercise]:
        """Search exercises by name (case-insensitive)."""
        stmt = select(Exercise).where(Exercise.name.ilike(f"%{query}%")).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class WorkoutSessionRepository(BaseRepository[WorkoutSession, dict, dict]):
    """Repository for WorkoutSession operations."""

    async def get_with_sets(
        self, session: AsyncSession, id: int
    ) -> Optional[WorkoutSession]:
        """Get a workout session with all its sets."""
        stmt = (
            select(WorkoutSession)
            .options(selectinload(WorkoutSession.workout_sets))
            .where(WorkoutSession.id == id)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_date_range(
        self,
        session: AsyncSession,
        *,
        start_date: str,
        end_date: str,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkoutSession]:
        """Get workout sessions within a date range."""
        stmt = (
            select(WorkoutSession)
            .where(WorkoutSession.date >= start_date)
            .where(WorkoutSession.date <= end_date)
            .order_by(WorkoutSession.date.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(
        self, session: AsyncSession, *, limit: int = 10
    ) -> List[WorkoutSession]:
        """Get the most recent workout sessions."""
        stmt = select(WorkoutSession).order_by(WorkoutSession.date.desc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


class WorkoutSetRepository(BaseRepository[WorkoutSet, dict, dict]):
    """Repository for WorkoutSet operations."""

    async def get_by_session(
        self, session: AsyncSession, session_id: int
    ) -> List[WorkoutSet]:
        """Get all sets for a specific workout session."""
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.exercise))
            .where(WorkoutSet.session_id == session_id)
            .order_by(WorkoutSet.set_number)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_exercise(
        self, session: AsyncSession, exercise_id: int, *, limit: int = 50
    ) -> List[WorkoutSet]:
        """Get sets for a specific exercise."""
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.session))
            .where(WorkoutSet.exercise_id == exercise_id)
            .order_by(WorkoutSet.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_personal_records(
        self, session: AsyncSession, exercise_id: int, *, limit: int = 10
    ) -> List[WorkoutSet]:
        """Get personal records for an exercise (by weight)."""
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.session))
            .where(WorkoutSet.exercise_id == exercise_id)
            .where(WorkoutSet.weight.isnot(None))
            .order_by(WorkoutSet.weight.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


class TrainingPrincipleRepository(BaseRepository[TrainingPrinciple, dict, dict]):
    """Repository for TrainingPrinciple operations."""

    async def get_by_category(
        self, session: AsyncSession, category: str
    ) -> List[TrainingPrinciple]:
        """Get training principles by category."""
        stmt = select(TrainingPrinciple).where(
            TrainingPrinciple.category == category
        ).order_by(TrainingPrinciple.priority)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_by_priority(
        self, session: AsyncSession, *, limit: int = 10
    ) -> List[TrainingPrinciple]:
        """Get training principles ordered by priority (lower = more important)."""
        stmt = select(TrainingPrinciple).order_by(
            TrainingPrinciple.priority
        ).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# Repository instances
exercise_repo = ExerciseRepository(Exercise)
workout_session_repo = WorkoutSessionRepository(WorkoutSession)
workout_set_repo = WorkoutSetRepository(WorkoutSet)
training_principle_repo = TrainingPrincipleRepository(TrainingPrinciple)
