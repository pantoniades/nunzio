"""Tests for the _expand_sets post-processing in MessageHandler."""

from nunzio.core import MessageHandler
from nunzio.llm.schemas import ExerciseSet


def _make_set(name="Bench Press", set_number=1, reps=10, weight=135.0, **kw):
    return ExerciseSet(exercise_name=name, set_number=set_number, reps=reps, weight=weight, **kw)


def test_single_entry_with_high_set_number_expands():
    """'2 sets of 10' misread as one entry with set_number=2 → expand to 2 sets."""
    exercises = [_make_set(name="Rear Delt Fly", set_number=2, reps=10, weight=40.0)]
    result = MessageHandler._expand_sets(exercises)
    assert len(result) == 2
    assert result[0].set_number == 1
    assert result[1].set_number == 2
    assert all(s.reps == 10 and s.weight == 40.0 for s in result)


def test_three_sets_expand():
    exercises = [_make_set(set_number=3, reps=8, weight=30.0)]
    result = MessageHandler._expand_sets(exercises)
    assert len(result) == 3
    for i, s in enumerate(result, 1):
        assert s.set_number == i
        assert s.reps == 8


def test_multiple_correct_entries_unchanged():
    """If the LLM already returned multiple entries, don't double-expand."""
    exercises = [
        _make_set(set_number=1, reps=10, weight=135.0),
        _make_set(set_number=2, reps=8, weight=135.0),
        _make_set(set_number=3, reps=6, weight=135.0),
    ]
    result = MessageHandler._expand_sets(exercises)
    assert len(result) == 3


def test_single_set_number_1_unchanged():
    """A single set with set_number=1 should stay as-is."""
    exercises = [_make_set(set_number=1)]
    result = MessageHandler._expand_sets(exercises)
    assert len(result) == 1


def test_mixed_exercises():
    """Two different exercises, one needing expansion, one not."""
    exercises = [
        _make_set(name="Curl", set_number=3, reps=12, weight=25.0),
        _make_set(name="Squat", set_number=1, reps=5, weight=225.0),
    ]
    result = MessageHandler._expand_sets(exercises)
    curls = [s for s in result if s.exercise_name == "Curl"]
    squats = [s for s in result if s.exercise_name == "Squat"]
    assert len(curls) == 3
    assert len(squats) == 1
