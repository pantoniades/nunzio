"""Unit tests for exercise name scoring — no DB or LLM needed."""

from nunzio.database.repository import ExerciseRepository


score = ExerciseRepository.score_match


def test_exact_match():
    assert score("Bench Press", "Bench Press") == 1.0


def test_exact_match_case_insensitive():
    assert score("bench press", "Bench Press") == 1.0


def test_high_overlap():
    # "dumbbell fly" vs "Dumbbell Flyes" — 1 shared word out of 3 unique
    s = score("dumbbell fly", "Dumbbell Flyes")
    assert s >= 0.3  # "dumbbell" matches, "fly"/"flyes" don't


def test_partial_overlap_single_word():
    # "chest pull" vs "Chest Press" — only "chest" matches, 3 unique words
    s = score("chest pull", "Chest Press")
    assert s < 0.5, f"Score {s} should be below threshold for bad match"


def test_no_overlap():
    s = score("purple band stretch", "Barbell Squat")
    assert s == 0.0


def test_chest_pull_vs_chest_press_below_threshold():
    """The motivating case: 'purple band chest pull' should NOT match 'Chest Press'."""
    s = score("purple band chest pull", "Chest Press")
    assert s < 0.5, f"Score {s} — 'purple band chest pull' must not match 'Chest Press'"


def test_dumbbell_flyes_match():
    """'dumbbell fly' should get a decent score against 'Dumbbell Flyes'."""
    s = score("dumbbell fly", "Dumbbell Flyes")
    # Only "dumbbell" overlaps exactly; "fly" != "flyes"
    # Jaccard: {dumbbell} / {dumbbell, fly, flyes} = 1/3 ≈ 0.33
    assert s > 0.0


def test_exact_single_word():
    assert score("Squat", "Squat") == 1.0


def test_empty_query():
    assert score("", "Bench Press") == 0.0


def test_empty_name():
    assert score("Bench Press", "") == 0.0
