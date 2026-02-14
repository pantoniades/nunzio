# AGENTS.md - Development Guidelines for Agentic Coding

## Build/Test Commands

```bash
# Install (editable, with dev deps)
pip install -e .[dev]

# Lint
ruff check src/

# Unit tests (no external services needed)
pytest tests/test_exercise_matching.py tests/test_expand_sets.py

# Full test suite (needs Ollama + MySQL)
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
```

## Project Structure

```
src/nunzio/
├── core.py            # MessageHandler: intent routing, all handlers, message logging
├── cli.py             # Interactive CLI (entry point: nunzio)
├── bot.py             # Telegram bot via long-polling (entry point: nunzio-bot)
├── config.py          # Pydantic settings (.env)
├── main.py            # Thin wrapper → cli.main()
├── database/
│   ├── connection.py  # Async engine + session manager
│   ├── models.py      # SQLAlchemy models (Exercise, WorkoutSet, MessageLog, TrainingPrinciple)
│   └── repository.py  # Repository pattern CRUD + scored search, batch ops, delete
└── llm/
    ├── client.py      # Ollama/Instructor: classify_intent, extract_workout_data, coaching
    ├── context.py     # Coaching context assembly (history, guidance, principles)
    └── schemas.py     # Pydantic models for LLM I/O (UserIntent, ExerciseSet, WorkoutData)

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
- **Repositories**: `exercise_repo`, `workout_set_repo`, `message_log_repo`, `training_principle_repo`
- **LLM**: `LLMClient.classify_intent()` → `UserIntent`, `LLMClient.extract_workout_data()` → `WorkoutData`, `LLMClient.generate_coaching_response()` → str
- **Retries**: tenacity with exponential backoff on LLM calls
- **Weight storage**: Float column + weight_unit string (lbs/kg), stored as-is from user input
- **Exercise matching**: exact name → scored Jaccard (≥0.5) → create ad-hoc. Raw name always preserved.
- **Intent routing**: 5 intents (log_workout, view_stats, coaching, delete_workout, repeat_last)
- **Message logging**: fire-and-forget in process(), exception-swallowed
