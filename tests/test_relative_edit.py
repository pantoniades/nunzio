"""Unit tests for relative edit parsing ("5lb more") — no DB or LLM needed."""

from nunzio.core import MessageHandler

parse = MessageHandler._parse_relative_edit


def test_lb_more():
    """The Jul 30 case: '5lb more' set the weight to 5 instead of adding 5."""
    assert parse("5lb more") == {"weight": 5.0}


def test_heavier_lighter():
    assert parse("make it 10 lbs heavier") == {"weight": 10.0}
    assert parse("2.5 kg lighter") == {"weight": -2.5}


def test_add_and_minus():
    assert parse("add 5") == {"weight": 5.0}
    assert parse("minus 10 lb") == {"weight": -10.0}
    assert parse("+5") == {"weight": 5.0}
    assert parse("decrease by 5 lbs") == {"weight": -5.0}


def test_reps_delta():
    assert parse("2 more reps") == {"reps": 2}
    assert parse("2 fewer reps") == {"reps": -2}


def test_absolute_edit_is_not_relative():
    assert parse("change weight to 30") == {}
    assert parse("reps to 12") == {}
    assert parse("fix #42 set 3 to 200 lbs") == {}


def test_bare_set_detection():
    bare = MessageHandler._is_bare_set
    for msg in ["12@55", "12@55 lb", "10x45", "12 @ 25 kg", "2x12@55", "8@60, felt heavy"]:
        assert bare(msg), msg
    for msg in ["low row 12@55", "again 12@55", "12", "weight 179.8", "5lb more", "delete #42"]:
        assert not bare(msg), msg


def test_bare_set_with_reps_word_and_trailing_note():
    """Oct 13: '2x12 reps heavy blue band' became a made-up 'Resistance Band Exercise'."""
    bare = MessageHandler._is_bare_set
    for msg in ["2x12 reps heavy blue band", "2x12 reps", "12@55 lb reps, easy"]:
        assert bare(msg), msg
    for msg in ["3x10 reps bench press", "2x12 heavy blue band", "3x10 squats", "2x12 reps of curls"]:
        assert not bare(msg), msg


def test_plan_is_not_a_log():
    """Nov 14: an announcement was logged as 10 assumed reps @ bodyweight."""
    plan = MessageHandler._is_plan_not_log
    for msg in [
        "Not what I meant, but very helpful. I'm going to do Triceps Press machine now",
        "about to hit squats",
        "next up: face pulls",
        "I\u2019ll do bench next",
    ]:
        assert plan(msg), msg
    for msg in [
        "did pushups",
        "bench press 12@45",
        "going to log 3x10 bench at 135",
        "3 sets of scapular pushups",
    ]:
        assert not plan(msg), msg
