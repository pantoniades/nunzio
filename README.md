# Nunzio - Local Workout Assistant

A conversational workout tracking assistant that runs locally, using local LLMs for natural language understanding and MySQL for persistence. Tell Nunzio what you did in plain English, and he'll log it. Ask for advice, and he'll give specific prescriptions based on your actual history.

Two interfaces: interactive CLI for local use, Telegram bot for mobile (at the gym).

## Features

- Natural language workout logging ("I did 3 sets of bench press at 185 lbs")
- Cardio logging with duration and distance ("ran 3 miles in 25 minutes")
- Undo/delete workouts ("undo", "delete last", "delete session #42")
- Repeat last workout ("again", "repeat last")
- Smart exercise matching — word-overlap scoring replaces naive substring search. Unknown exercises get created as-is instead of being force-mapped to the wrong catalog entry. Matched names show the mapping ("Dumbbell Flyes (from 'dumbbell fly')")
- Context-aware coaching based on your actual workout history, exercise guidance, and training principles
- Intent classification with exercise and muscle group extraction in a single LLM call
- Exercise catalog with 29 exercises across 9 muscle groups (including cardio)
- Training principles (progression, deload, rep ranges, volume, etc.) injected into coaching prompts
- Workout statistics and progress tracking
- Message logging — every interaction saved with intent, confidence, and response for debugging
- Telegram bot via long-polling — no port forwarding or dynamic DNS needed
- Podman container for deployment
- Local LLM integration via Ollama + Instructor (JSON mode) for structured extraction
- Multi-user support — each Telegram user's data is isolated (CLI uses a separate user ID)
- Complete privacy — everything runs locally

## Quick Start

### Prerequisites

- Python 3.12+
- MySQL 8.4+
- OpenAI compatible LLM service running with a model available

### Installation

```bash
git clone <repo-url>
cd nunzio
python -m venv venv
source venv/bin/activate
pip install -e .
```

### Configure

```bash
cp .env.example .env
# Edit .env with your database credentials, Ollama URL, and model name
```

### Set up database

```sql
CREATE DATABASE nunzio_workouts;
CREATE USER 'nunzio'@'%' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON nunzio_workouts.* TO 'nunzio'@'%';
FLUSH PRIVILEGES;
```

Then create tables and seed data:

```bash
python scripts/create_tables.py
python scripts/seed_exercises.py
python scripts/seed_principles.py
```

### Run the CLI

```bash
nunzio
```

### Run the Telegram bot

1. Message `@BotFather` on Telegram, `/newbot`, copy the token
2. Set `TELEGRAM__TOKEN=<your token>` in `.env`
3. Optionally set `TELEGRAM__ALLOWED_USER_IDS=[12345678]` to restrict access (message `@userinfobot` to find your ID)

```bash
nunzio-bot
```

### Run in Podman

```bash
podman build -t nunzio .
podman run --env-file .env nunzio
```

The container runs the Telegram bot by default.

### Example usage

```
You: I did 3 sets of bench press at 185 lbs, 10 reps
You: ran 3 miles in 25 minutes
You: show my stats
You: what should I bench next session?
You: undo
You: did 2 sets of squat 5 reps at 225 lbs
You: again
You: did 1 set of purple band chest pull 10 reps
```

### Clean slate

To wipe all data and start fresh:

```bash
python scripts/create_tables.py    # drops and recreates all tables
python scripts/seed_exercises.py   # re-populates exercise catalog
python scripts/seed_principles.py  # re-populates training principles
```

### Upgrading from v0.2

If you have an existing database, run the migration instead of recreating tables:

```bash
python scripts/migrate_v03.py
```

This adds the `raw_exercise_name` column to `workout_sets` and creates the `message_log` table. Idempotent — safe to run multiple times.

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE__URL`: MySQL connection string
- `LLM__BASE_URL`: Ollama server URL
- `LLM__MODEL`: Model to use (e.g. `qwen3:30b-a3b`)
- `TELEGRAM__TOKEN`: Bot token from BotFather
- `TELEGRAM__ALLOWED_USER_IDS`: JSON list of allowed Telegram user IDs (empty = open)

## Architecture

### How a message flows

```
User message
  → LLM classify_intent() → UserIntent (intent, confidence, exercises, muscle groups)
  → Route by intent:
      log_workout   → extract_workout_data() → scored exercise matching → DB persist
      view_stats    → query recent sessions + sets → format response
      delete_workout → parse "undo"/"last"/session ID → DB delete with cascade
      repeat_last   → get_latest_for_user() → clone session + sets
      coaching      → build_coaching_context() → generate_coaching_response()
  → Log to message_log table
  → Return response
```

### Intent routing

5 intents: `log_workout`, `view_stats`, `coaching` (catch-all), `delete_workout`, `repeat_last`. Classification uses Instructor (JSON mode) with a fallback keyword matcher if the LLM call fails.

### Exercise matching

When logging a workout, the LLM extracts exercise names from natural language. These get matched against the exercise catalog in three tiers:

1. **Exact name match** — use it directly
2. **Scored match >= 0.5** — word-overlap Jaccard similarity against all catalog entries. Use the best match, show the mapping in the response (e.g. `Dumbbell Flyes (from "dumbbell fly")`)
3. **Score < 0.5** — create a new ad-hoc exercise with the user's exact name and muscle group "general"

The raw exercise name from the user is always preserved in `workout_sets.raw_exercise_name`.

### Coaching pipeline

`build_coaching_context()` in `llm/context.py` assembles a prompt block from:
1. Training principles by priority (top 6, plus cardio principle if relevant)
2. Matched exercise details (from intent extraction)
3. Per-exercise guidance text (from `exercises.guidance` column)
4. Recent workout history per exercise (last 10 sets, grouped by session, with PR)

This gets injected into the user message alongside a coaching system prompt. The LLM generates free-text advice (NOT Instructor — raw completions).

### Code layout

```
src/nunzio/
├── core.py            # MessageHandler: intent routing, all handlers, message logging
├── cli.py             # Interactive CLI (entry point: nunzio)
├── bot.py             # Telegram bot via long-polling (entry point: nunzio-bot)
├── config.py          # Pydantic settings from .env
├── main.py            # Thin wrapper for CLI
├── database/
│   ├── connection.py  # Async SQLAlchemy engine + session manager
│   ├── models.py      # Exercise, WorkoutSession, WorkoutSet, MessageLog, TrainingPrinciple
│   └── repository.py  # Repository pattern: CRUD + scored search, latest-for-user, delete
└── llm/
    ├── client.py      # Ollama/Instructor: classify_intent, extract_workout_data, coaching
    ├── context.py     # Coaching context assembly (history, guidance, principles)
    └── schemas.py     # Pydantic models: UserIntent, ExerciseSet, WorkoutData

scripts/
├── create_tables.py     # Drop + recreate all tables
├── seed_exercises.py    # Seed 29-exercise catalog
├── seed_principles.py   # Seed 9 training principles
├── clear_and_reseed.py  # Wipe data + reseed
└── migrate_v03.py       # v0.3 migration (raw_exercise_name + message_log)

tests/
├── test_exercise_matching.py  # Unit: scoring function (no external deps)
├── test_expand_sets.py        # Unit: set expansion post-processing
├── test_delete_workout.py     # Unit + integration: undo/delete
├── test_repeat_last.py        # Integration: repeat last workout
├── test_llm_integration.py    # Integration: intent classification + extraction (needs Ollama)
├── test_db.py                 # Integration: DB connectivity + CRUD (needs MySQL)
└── test_ollama.py             # Connectivity: Ollama health check
```

### Database schema

| Table | Key columns | Purpose |
|-------|------------|---------|
| `exercises` | name, muscle_group, guidance | Exercise catalog (29 seeded + ad-hoc) |
| `workout_sessions` | user_id, date, notes | One per "I did X" message |
| `workout_sets` | session_id, exercise_id, set_number, reps, weight, weight_unit, duration_minutes, distance, raw_exercise_name, notes | Individual sets within a session |
| `training_principles` | category, title, content, priority | Coaching knowledge (9 seeded) |
| `message_log` | user_id, raw_message, classified_intent, confidence, response_summary | Every interaction logged |

### Key patterns

- **Config**: `from nunzio.config import config` — pydantic-settings, env vars with `__` delimiter
- **DB sessions**: `async with db_manager.get_session() as session:` — auto-commit/rollback
- **Repositories**: `exercise_repo`, `workout_session_repo`, `workout_set_repo`, `message_log_repo`, `training_principle_repo`
- **LLM calls**: Instructor (JSON mode) for structured extraction, raw OpenAI client for coaching
- **Retries**: tenacity with exponential backoff on LLM calls
- **Two interfaces, shared core**: `MessageHandler` owns all logic. CLI is verbose (session IDs), bot is terse.
- **User isolation**: `user_id` on every session/query. Telegram passes real user ID, CLI uses 0.

## Development

```bash
pip install -e .[dev]
ruff check src/
pytest tests/test_exercise_matching.py tests/test_expand_sets.py  # unit tests (no services needed)
pytest tests/                                                      # full suite (needs Ollama + MySQL)
```
