"""Unit tests for resident-model selection — no DB or LLM needed."""

from nunzio.llm.client import LLMClient

pick = LLMClient._pick_model_from_running


def test_empty_running_returns_configured():
    chosen, override = pick([], "qwen3.5-27b")
    assert chosen == "qwen3.5-27b"
    assert override is False


def test_no_ready_entry_returns_configured():
    running = [{"state": "starting", "model": "gemma-4-27b"}]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "qwen3.5-27b"
    assert override is False


def test_ready_configured_model_is_used_without_override():
    running = [{"state": "ready", "model": "qwen3.5-27b"}]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "qwen3.5-27b"
    assert override is False


def test_ready_allowlisted_model_overrides():
    running = [{"state": "ready", "model": "gemma-4-27b"}]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "gemma-4-27b"
    assert override is True


def test_ready_non_allowlisted_model_forces_swap():
    running = [{"state": "ready", "model": "phi4"}]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "qwen3.5-27b"
    assert override is False


def test_first_ready_entry_wins():
    running = [
        {"state": "starting", "model": "phi4"},
        {"state": "ready", "model": "qwen3-coder-30b"},
    ]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "qwen3-coder-30b"
    assert override is True


def test_ready_entry_missing_model_falls_back():
    running = [{"state": "ready"}]
    chosen, override = pick(running, "qwen3.5-27b")
    assert chosen == "qwen3.5-27b"
    assert override is False
