"""Unit tests for body-weight unit conversion and plausibility — no DB/LLM."""

from nunzio.core import _convert_weight, _is_plausible_body_weight


def test_convert_same_unit_is_identity():
    assert _convert_weight(100.0, "lbs", "lbs") == 100.0
    assert _convert_weight(80.0, "kg", "kg") == 80.0


def test_convert_kg_to_lbs():
    assert round(_convert_weight(100.0, "kg", "lbs"), 1) == 220.5


def test_convert_lbs_to_kg():
    assert round(_convert_weight(220.462, "lbs", "kg"), 1) == 100.0


def test_plausible_lbs():
    assert _is_plausible_body_weight(185.0, "lbs") is True
    assert _is_plausible_body_weight(20.0, "lbs") is False  # the "20 lb" bug
    assert _is_plausible_body_weight(800.0, "lbs") is False


def test_plausible_kg():
    assert _is_plausible_body_weight(84.0, "kg") is True
    assert _is_plausible_body_weight(10.0, "kg") is False
    assert _is_plausible_body_weight(400.0, "kg") is False
