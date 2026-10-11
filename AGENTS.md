# AGENTS.md - Development Guidelines for Agentic Coding

## Build/Test Commands

```bash
# Install (editable, with dev deps) — on odysseus use uv; pip is broken by a middlebox
uv pip install -e ".[dev]"

# Lint
ruff check src/ tests/

# Unit tests (no external services needed)
pytest tests/test_exercise_matching.py tests/test_repeat_modifiers.py \
       tests/test_relative_edit.py tests/test_roster.py tests/test_checkin.py

# Full test suite (needs the LLM + MySQL) — the bar for "done"
pytest tests/

# Run the CLI
nunzio                          # uses entry point
python -m nunzio.cli            # module invocation

# DB management
python scripts/create_tables.py    # drop + recreate all tables
python scripts/seed_exercises.py   # seed exercise catalog
python scripts/seed_principles.py  # seed training principles
python scripts/clear_and_reseed.py # wipe data + reseed
python scripts/migrate_v03.py      # v0.3 migration (additive, idempotent)
python scripts/migrate_v05.py      # v0.5 migration (flatten sessions into sets)
python scripts/migrate_v07.py      # v0.7: user_settings table
python scripts/migrate_v08.py      # v0.8: proactive_log table
python scripts/migrate_v09.py      # v0.9: exercise cleanup — dry run; --apply to write (back up first)
```

## Workflow

- Single developer: commit directly to `master` and push. No feature branches or PRs.
- Deploy: pull into `~/Deploy/nunzio`, `podman build --format docker -t localhost/nunzio:latest .`,
  then `systemctl --user restart nunzio` (see `deploy/README.md`).

## Project Structure

```
src/nunzio/
├── core.py            # MessageHandler: intent routing, all handlers, message logging
├── cli.py             # Interactive CLI (entry point: nunzio)
├── bot.py             # Telegram bot via long-polling (entry point: nunzio-bot)
├── checkin.py         # Proactive Telegram check-ins (PR / streak / nudge)
├── exercise_names.py  # Name normalization, match scoring, muscle-group guessing (pure)
├── stats.py           # Consistency stats
├── config.py          # Pydantic settings (.env)
├── main.py            # Thin wrapper → cli.main()
├── database/
│   ├── connection.py  # Async engine + session manager
│   ├── models.py      # SQLAlchemy models (Exercise, WorkoutSet, MessageLog, TrainingPrinciple, BodyWeight, UserSettings, ProactiveLog)
│   └── repository.py  # Repository pattern CRUD + scored search, batch ops, delete
└── llm/
    ├── client.py      # OpenAI-compatible client + Instructor: classify, extract, coaching, log comments
    ├── context.py     # Coaching context assembly (roster, history, volume, principles)
    └── schemas.py     # Pydantic models for LLM I/O (UserIntent, ExerciseSet, WorkoutData, EditSetData)

scripts/               # DB management + migration scripts
tests/                 # Unit + integration tests
```

## Code Style

- Line length: 88 (Ruff)
- Python 3.12+
- All DB/network ops async
- Type hints on public APIs
- Double quotes, trailing commas, 4-space indent
- Imports: stdlib → third-party → local

## Key Patterns

- **Config**: `from nunzio.config import config` — pydantic-settings, env vars with `__` delimiter
- **DB sessions**: `async with db_manager.get_session() as session:`
- **Repositories**: `exercise_repo`, `workout_set_repo`, `message_log_repo`, `training_principle_repo`, `body_weight_repo`, `user_settings_repo`, `proactive_log_repo`
- **LLM**: `LLMClient.classify_intent()` → `UserIntent`, `LLMClient.extract_workout_data()` → `WorkoutData`, `LLMClient.extract_edit_set_data()` → `EditSetData` (Instructor TOOLS mode), `LLMClient.generate_coaching_response()` / `generate_log_comment()` → str
- **Retries**: tenacity with exponential backoff on LLM calls
- **Weight storage**: Float column + weight_unit string (lbs/kg), stored as-is from user input
- **Exercise matching**: exact name → normalized-token Jaccard with equipment/angle penalty (≥0.5) → create ad-hoc with `guess_muscle_group()`. Raw name always preserved. Different machines for one movement stay separate exercises (loads aren't comparable).
- **Deterministic shortcuts before/around the LLM**: bare sets ("12@55") get the last exercise name prefixed before classification; repeat overrides and relative edits ("5lb more") are regex-parsed in `core.py`.
- **Intent routing**: 9 intents (log_workout, log_weight, set_timezone, view_stats, list_workouts, edit_set, delete_workout, repeat_last, coaching)
- **Message logging**: fire-and-forget in process(), exception-swallowed
