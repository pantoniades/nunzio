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


# --- v0.9: normalization, variants, muscle-group guessing ---

from nunzio.exercise_names import guess_muscle_group  # noqa: E402


def test_plural_folds_to_singular():
    assert score("dumbbell curl", "Dumbbell Curls") == 1.0
    assert score("face pull", "Face Pulls") == 1.0


def test_hyphen_and_synonyms_fold():
    assert score("band pull apart", "Band Pull-Apart") == 1.0
    assert score("pec fly", "Chest Fly") == 1.0
    assert score("pectoral fly", "Chest Fly") == 1.0
    assert score("dumbbell fly", "Dumbbell Flyes") == 1.0


def test_equipment_mismatch_below_threshold():
    """The Aug 10 case: 'Dumbbell bench press' must not map to barbell Bench Press."""
    assert score("dumbbell bench press", "Bench Press") < 0.5
    assert score("incline dumbbell curls", "Dumbbell Curls") < 0.5
    assert score("machine pec fly", "Chest Fly") < 0.5


def test_shoulder_press_does_not_match_bench_press():
    """The Jul 24 case: 'shoulder press history' returned Bench Press."""
    assert score("shoulder press", "Bench Press") < 0.5


def test_same_variant_still_matches():
    assert score("incline dumbbell bench", "Incline Dumbbell Press") >= 0.5


def test_hyphenated_up_movements_fold():
    """Nov 14 root cause: 'scapular pushups' missed the catalog's 'Scapular Push-Up'."""
    assert score("scapular pushups", "Scapular Push-Up") == 1.0
    assert score("scap pushups", "Scapular Push-Up") == 1.0
    assert score("push ups", "Pushup") == 1.0
    assert score("pull-ups", "Pull Up") == 1.0
    assert score("chinups", "Chin-Up") == 1.0
    assert guess_muscle_group("Scapular Pushups") == "chest"


def test_more_specific_query_is_a_different_exercise():
    """Nov 14: 'scapular pushups' was logged as Pushup four times running."""
    assert score("scapular pushups", "Pushup") < 0.5
    assert score("Dumbbell Hammer Curl", "Dumbbell Curl") < 0.5
    assert score("close grip bench press", "Bench Press") < 0.5


def test_abbreviated_or_redundant_query_still_matches():
    assert score("bench", "Bench Press") >= 0.5
    assert score("pulldown", "Lat Pulldown") >= 0.5
    assert score("rope pulldown", "Tricep Rope Pulldown") >= 0.5
    assert score("incline dumbbell bench press", "Incline Dumbbell Press") >= 0.5
    assert score("the bench press", "Bench Press") == 1.0


def test_guess_muscle_group():
    cases = {
        "Low Row": "back",
        "Lat Pulldown": "back",
        "Face Pull": "shoulders",
        "Band Pull Apart": "shoulders",
        "Rear Delt Fly": "shoulders",
        "Barbell curl": "biceps",
        "Leg Curl": "legs",
        "Tricep Rope Pulldown": "triceps",
        "Dumbbell Skull Crusher": "triceps",
        "Machine Pec Fly": "chest",
        "Incline Bench Press": "chest",
        "Shoulder Press": "shoulders",
        "Elliptical": "cardio",
        "Stationary Bike": "cardio",
        "Plank": "core",
        "Chin Up": "back",
        "Abduction Machine": "general",
    }
    for name, group in cases.items():
        assert guess_muscle_group(name) == group, name
