"""Async repository pattern implementation for database operations."""

from typing import Generic, List, Optional, Type, TypeVar, Union

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .models import Base, Exercise, MessageLog, TrainingPrinciple, WorkoutSet

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

    async def get_all(self, session: AsyncSession) -> List[Exercise]:
        """Get all exercises."""
        stmt = select(Exercise)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def score_match(query: str, name: str) -> float:
        """Score exercise name match using word-overlap Jaccard similarity.

        Tokenizes both strings, computes |intersection| / |union|.
        """
        q_tokens = set(query.lower().split())
        n_tokens = set(name.lower().split())
        if not q_tokens or not n_tokens:
            return 0.0
        intersection = q_tokens & n_tokens
        union = q_tokens | n_tokens
        return len(intersection) / len(union)

    async def search_scored(
        self, session: AsyncSession, query: str
    ) -> List[tuple]:
        """Score all exercises against query using word-overlap Jaccard.

        Returns list of (Exercise, score) sorted by score descending.
        """
        all_exercises = await self.get_all(session)
        scored = [(ex, self.score_match(query, ex.name)) for ex in all_exercises]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


class WorkoutSetRepository(BaseRepository[WorkoutSet, dict, dict]):
    """Repository for WorkoutSet operations."""

    async def get_next_batch_id(self, session: AsyncSession, user_id: int) -> int:
        """Get the next batch_id for a user (max + 1, or 1 if none exist)."""
        stmt = select(func.max(WorkoutSet.batch_id)).where(
            WorkoutSet.user_id == user_id
        )
        result = await session.execute(stmt)
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1

    async def get_latest_batch_for_user(
        self, session: AsyncSession, user_id: int
    ) -> List[WorkoutSet]:
        """Get all sets from the user's most recent batch, with exercise eagerly loaded."""
        # First get the latest batch_id
        sub = (
            select(func.max(WorkoutSet.batch_id))
            .where(WorkoutSet.user_id == user_id)
            .scalar_subquery()
        )
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.exercise))
            .where(WorkoutSet.user_id == user_id)
            .where(WorkoutSet.batch_id == sub)
            .order_by(WorkoutSet.set_number)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def delete_batch(
        self, session: AsyncSession, batch_id: int, user_id: int
    ) -> List[WorkoutSet]:
        """Delete all sets with the given batch_id owned by user. Returns sets before deletion."""
        # Fetch first (with exercises) so we can return details
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.exercise))
            .where(WorkoutSet.batch_id == batch_id)
            .where(WorkoutSet.user_id == user_id)
        )
        result = await session.execute(stmt)
        sets = list(result.scalars().all())
        if sets:
            del_stmt = (
                delete(WorkoutSet)
                .where(WorkoutSet.batch_id == batch_id)
                .where(WorkoutSet.user_id == user_id)
            )
            await session.execute(del_stmt)
            await session.flush()
        return sets

    async def get_latest_batches(
        self, session: AsyncSession, user_id: int, *, limit: int = 10
    ) -> List[WorkoutSet]:
        """Get sets from the N most recent batches for list_workouts, ordered by batch_id desc."""
        # Get the N most recent distinct batch_ids
        batch_sub = (
            select(WorkoutSet.batch_id)
            .where(WorkoutSet.user_id == user_id)
            .group_by(WorkoutSet.batch_id)
            .order_by(WorkoutSet.batch_id.desc())
            .limit(limit)
            .subquery()
        )
        stmt = (
            select(WorkoutSet)
            .options(selectinload(WorkoutSet.exercise))
            .where(WorkoutSet.user_id == user_id)
            .where(WorkoutSet.batch_id.in_(select(batch_sub.c.batch_id)))
            .order_by(WorkoutSet.batch_id.desc(), WorkoutSet.set_number)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_user(
        self, session: AsyncSession, user_id: int, *, limit: int = 1000
    ) -> List[WorkoutSet]:
        """Get all sets for a user."""
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.user_id == user_id)
            .order_by(WorkoutSet.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_exercise(
        self, session: AsyncSession, exercise_id: int, user_id: int, *, limit: int = 50
    ) -> List[WorkoutSet]:
        """Get sets for a specific exercise for a user."""
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.exercise_id == exercise_id)
            .where(WorkoutSet.user_id == user_id)
            .order_by(WorkoutSet.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_personal_records(
        self, session: AsyncSession, exercise_id: int, user_id: int, *, limit: int = 10
    ) -> List[WorkoutSet]:
        """Get personal records for an exercise (by weight) for a user."""
        stmt = (
            select(WorkoutSet)
            .where(WorkoutSet.exercise_id == exercise_id)
            .where(WorkoutSet.user_id == user_id)
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


class MessageLogRepository(BaseRepository[MessageLog, dict, dict]):
    """Repository for MessageLog operations."""

    async def get_by_user(
        self, session: AsyncSession, user_id: int, *, limit: int = 50
    ) -> List[MessageLog]:
        """Get recent message logs for a user."""
        stmt = (
            select(MessageLog)
            .where(MessageLog.user_id == user_id)
            .order_by(MessageLog.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())


# Repository instances
exercise_repo = ExerciseRepository(Exercise)
workout_set_repo = WorkoutSetRepository(WorkoutSet)
training_principle_repo = TrainingPrincipleRepository(TrainingPrinciple)
message_log_repo = MessageLogRepository(MessageLog)
