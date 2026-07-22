"""Unit tests for the reps/weight inversion guard — no DB or LLM needed."""

from nunzio.core import MessageHandler
from nunzio.llm.schemas import ExerciseSet

swap = MessageHandler._swap_if_inverted


def test_inverted_curls_are_swapped():
    # The "Dumbbell curls 8x30" bug: extractor produced reps=30, weight=8.
    s = ExerciseSet(exercise_name="Dumbbell Curls", reps=30, weight=8.0)
    assert swap(s) is True
    assert s.reps == 8
    assert s.weight == 30.0


def test_normal_set_untouched():
    s = ExerciseSet(exercise_name="Bench Press", reps=8, weight=185.0)
    assert swap(s) is False
    assert (s.reps, s.weight) == (8, 185.0)


def test_reps_below_threshold_untouched():
    # 25 reps @ 10 lb — reps under the 30 threshold, left alone.
    s = ExerciseSet(exercise_name="Lateral Raise", reps=25, weight=10.0)
    assert swap(s) is False


def test_weight_at_threshold_not_swapped():
    # weight must be strictly below 15 to qualify.
    s = ExerciseSet(exercise_name="Curl", reps=30, weight=15.0)
    assert swap(s) is False


def test_cardio_untouched():
    s = ExerciseSet(
        exercise_name="Rowing", reps=None, weight=None, duration_minutes=20
    )
    assert swap(s) is False


def test_bodyweight_untouched():
    s = ExerciseSet(exercise_name="Pushups", reps=40, weight=None)
    assert swap(s) is False
