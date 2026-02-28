"""Unit tests for repeat-last modifier parsing — no DB or LLM needed."""

from nunzio.core import MessageHandler

parse = MessageHandler._parse_repeat_modifiers


def test_plain_again():
    m = parse("again")
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


def test_note_preserved():
    m = parse("again, elbow feels better")
    assert m["weight"] is None
    assert m["times"] == 1
    assert m["note"] == "elbow feels better"
