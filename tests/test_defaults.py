"""Tests for post-processing logic: reps defaults and repeat-note extraction."""

from nunzio.core import MessageHandler
from nunzio.llm.schemas import ExerciseSet


def _make_set(name="Bench Press", set_number=1, reps=None, weight=135.0, **kw):
    return ExerciseSet(exercise_name=name, set_number=set_number, reps=reps, weight=weight, **kw)


def _apply_defaults(exercises: list[ExerciseSet]) -> set[int]:
    """Replicate the defaulting logic from core._handle_log_workout."""
    defaulted: set[int] = set()
    for i, ex_set in enumerate(exercises):
        if ex_set.duration_minutes:
            continue
        if not ex_set.reps:
            ex_set.reps = 10
            defaulted.add(i)
    return defaulted


def test_missing_reps_gets_default():
    """Strength set with no reps → defaults to 10."""
    exercises = [_make_set(reps=None, weight=100.0)]
    defaulted = _apply_defaults(exercises)
    assert exercises[0].reps == 10
    assert 0 in defaulted


def test_zero_reps_gets_default():
    """Strength set with reps=0 → defaults to 10."""
    exercises = [_make_set(reps=0, weight=100.0)]
    defaulted = _apply_defaults(exercises)
    assert exercises[0].reps == 10
    assert 0 in defaulted


def test_cardio_with_duration_skipped():
    """Cardio set with duration_minutes → reps stays None."""
    exercises = [_make_set(name="Running", reps=None, weight=None, duration_minutes=30)]
    defaulted = _apply_defaults(exercises)
    assert exercises[0].reps is None
    assert 0 not in defaulted


def test_explicit_reps_unchanged():
    """Strength set with explicit reps → no change."""
    exercises = [_make_set(reps=8, weight=135.0)]
    defaulted = _apply_defaults(exercises)
    assert exercises[0].reps == 8
    assert 0 not in defaulted


def test_mixed_sets():
    """Multiple sets: one missing reps, one explicit, one cardio."""
    exercises = [
        _make_set(name="Bench Press", reps=None, weight=100.0),
        _make_set(name="Squat", reps=5, weight=225.0),
        _make_set(name="Running", reps=None, weight=None, duration_minutes=20),
    ]
    defaulted = _apply_defaults(exercises)
    assert exercises[0].reps == 10  # defaulted
    assert exercises[1].reps == 5   # unchanged
    assert exercises[2].reps is None  # cardio, skipped
    assert defaulted == {0}


# --- Repeat-note extraction ---

def test_repeat_note_bare_again():
    """Just 'again' → no note."""
    assert MessageHandler._extract_repeat_note("again") is None


def test_repeat_note_bare_repeat_last():
    """'repeat last' → no note."""
    assert MessageHandler._extract_repeat_note("repeat last") is None


def test_repeat_note_with_text():
    """'again didn't struggle this time' → extracts the note."""
    note = MessageHandler._extract_repeat_note("Again didn't struggle this time")
    assert note == "didn't struggle this time"


def test_repeat_note_same_thing_with_text():
    """'same thing but felt easier' → extracts note."""
    note = MessageHandler._extract_repeat_note("same thing but felt easier")
    assert note == "but felt easier"


def test_repeat_note_only_trigger_words():
    """'same as last time' → no note."""
    assert MessageHandler._extract_repeat_note("same as last time") is None
