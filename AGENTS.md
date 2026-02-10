# AGENTS.md - Development Guidelines for Agentic Coding

## Build/Test Commands

```bash
# Install (editable, with dev deps)
pip install -e .[dev]

# Lint
ruff check src/

# Tests
pytest tests/

# Run the CLI
nunzio                          # uses entry point
python -m nunzio.cli            # module invocation

# DB management
python scripts/create_tables.py   # drop + recreate all tables
python scripts/seed_exercises.py  # seed exercise catalog
python scripts/clear_and_reseed.py  # wipe data + reseed
```

## Project Structure

```
src/nunzio/
├── cli.py             # Interactive CLI (entry point)
├── config.py          # Pydantic settings (.env)
├── main.py            # Thin wrapper → cli.main()
├── database/
│   ├── connection.py  # Async engine + session manager
│   ├── models.py      # SQLAlchemy models (Exercise, WorkoutSession, WorkoutSet)
│   └── repository.py  # Repository pattern CRUD
└── llm/
    ├── client.py      # Ollama/Instructor: classify_intent, extract_workout_data
    └── schemas.py     # Pydantic models for LLM I/O

scripts/               # DB management scripts
tests/                 # pytest tests
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
- **Repositories**: `exercise_repo`, `workout_session_repo`, `workout_set_repo`
- **LLM**: `LLMClient.classify_intent()` → `UserIntent`, `LLMClient.extract_workout_data()` → `WorkoutData`
- **Retries**: tenacity with exponential backoff on LLM calls
- **Weight storage**: Float column + weight_unit string (lbs/kg), stored as-is from user input
