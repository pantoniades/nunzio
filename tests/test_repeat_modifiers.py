"""Unit tests for repeat-last modifier parsing — no DB or LLM needed."""

from nunzio.core import MessageHandler

parse = MessageHandler._parse_repeat_modifiers


def test_plain_again():
    m = parse("again")
    assert m["reps"] is None
    assert m["weight"] is None
    assert m["times"] == 1
    assert m["note"] is None


def test_weight_override_at():
    m = parse("again at 35 lbs")
    assert m["weight"] == 35.0
    assert m["weight_unit"] == "lbs"
    assert m["times"] == 1
    assert m["note"] is None


def test_weight_override_for():
    m = parse("again for 35 lb")
    assert m["weight"] == 35.0
    assert m["weight_unit"] == "lbs"


def test_weight_override_at_symbol():
    m = parse("again @ 40")
    assert m["weight"] == 40.0


def test_weight_override_kg():
    m = parse("again at 20 kg")
    assert m["weight"] == 20.0
    assert m["weight_unit"] == "kg"


def test_weight_with_number_and_unit():
    m = parse("again 35 lbs")
    assert m["weight"] == 35.0
    assert m["weight_unit"] == "lbs"


def test_twice():
    m = parse("again twice")
    assert m["times"] == 2
    assert m["weight"] is None
    assert m["note"] is None


def test_x2():
    m = parse("again x2")
    assert m["times"] == 2


def test_3_times():
    m = parse("again 3 times")
    assert m["times"] == 3


def test_weight_and_times():
    m = parse("again at 35 lbs twice")
    assert m["weight"] == 35.0
    assert m["times"] == 2


def test_bare_number_as_weight():
    m = parse("again 54")
    assert m["weight"] == 54.0
    assert m["weight_unit"] == "lbs"
    assert m["note"] is None


def test_bare_decimal_as_weight():
    m = parse("again 42.5")
    assert m["weight"] == 42.5
    assert m["weight_unit"] == "lbs"


def test_note_preserved():
    m = parse("again, elbow feels better")
    assert m["weight"] is None
    assert m["times"] == 1
    assert m["note"] == "elbow feels better"


def test_reps_x_weight():
    m = parse("again 10x55")
    assert m["reps"] == 10
    assert m["weight"] == 55.0
    assert m["weight_unit"] == "lbs"
    assert m["times"] == 1
    assert m["note"] is None


def test_reps_x_weight_with_unit():
    m = parse("again 8x100 kg")
    assert m["reps"] == 8
    assert m["weight"] == 100.0
    assert m["weight_unit"] == "kg"


def test_reps_x_weight_with_spaces():
    m = parse("another 10 x 50")
    assert m["reps"] == 10
    assert m["weight"] == 50.0
    assert m["weight_unit"] == "lbs"


def test_reps_x_weight_with_comma():
    m = parse("Another, 10x55")
    assert m["reps"] == 10
    assert m["weight"] == 55.0
    assert m["note"] is None


def test_reps_x_weight_with_note():
    m = parse("again 10x50, knee felt better")
    assert m["reps"] == 10
    assert m["weight"] == 50.0
    assert m["note"] == "knee felt better"


# --- Shorthand seen in real usage (v0.9) ---


def test_reps_at_weight():
    m = parse("Again 12@30")
    assert (m["reps"], m["weight"], m["weight_unit"]) == (12, 30.0, "lbs")
    assert m["sets"] is None
    assert m["note"] is None


def test_reps_at_weight_kg():
    m = parse("Again 12@20 kg")
    assert (m["reps"], m["weight"], m["weight_unit"]) == (12, 20.0, "kg")
    assert m["note"] is None


def test_reps_at_weight_with_note():
    m = parse("Again 8@40 difficult")
    assert (m["reps"], m["weight"]) == (8, 40.0)
    assert m["note"] == "difficult"


def test_sets_reps_at_weight():
    m = parse("Again 2x12@55")
    assert (m["sets"], m["reps"], m["weight"]) == (2, 12, 55.0)
    assert m["times"] == 1
    assert m["note"] is None


def test_n_more_sets_with_weight():
    m = parse("2 more sets @20 lb")
    assert m["sets"] == 2
    assert m["weight"] == 20.0
    assert m["note"] is None


def test_n_more_sets():
    m = parse("2 more sets")
    assert m["sets"] == 2
    assert m["note"] is None


def test_one_more_set():
    m = parse("One more set")
    assert m["sets"] == 1
    assert m["times"] == 1
    assert m["note"] is None


def test_twice_more():
    m = parse("Twice more")
    assert m["times"] == 2
    assert m["sets"] is None
    assert m["note"] is None


def test_weight_kg_no_space():
    m = parse("Again @16kg")
    assert (m["weight"], m["weight_unit"]) == (16.0, "kg")
    assert m["reps"] is None


def test_decimal_kg():
    m = parse("Again @26.25 kg")
    assert m["weight"] == 26.25
    assert m["weight_unit"] == "kg"


def test_more_inside_note_kept():
    m = parse("again, felt more stable")
    assert m["note"] == "felt more stable"
