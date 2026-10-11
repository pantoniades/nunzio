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
