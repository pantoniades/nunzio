# Nunzio - Local Workout Assistant

A conversational workout tracking assistant that runs locally, using local LLMs for natural language understanding and MySQL for persistence. Tell Nunzio what you did in plain English, and he'll log it. Ask for advice, and he'll give specific prescriptions based on your actual history.

Two interfaces: interactive CLI for local use, Telegram bot for mobile (at the gym).

## Features

- Natural language workout logging ("I did 3 sets of bench press at 185 lbs", "low row 2x12@55")
- Gym shorthand: a bare set like `12@55` or `10x45 lb` is logged as the last exercise you did
- Cardio logging with duration and distance ("ran 3 miles in 25 minutes")
- Undo/delete workouts ("undo", "delete last", "delete #42")
- Edit sets, including relative changes ("change reps to 12", "5lb more", "2 fewer reps")
- Repeat last workout with overrides ("again", "again 12@30", "again 2x12@55", "one more set", "2 more sets @20 lb", "again twice")
- Body-weight tracking ("weight 179.8") with trend vs. your last weigh-in
- Coaching grounded in your own data: prescribes only exercises you actually do, at weights from your last sessions, and eases you back in after a layoff. Uses history, volume trends, consistency, lagging muscle groups, body-weight trend, exercise guidance, and training principles
- Encouraging one-liner after notable logs (PRs, first time, back after a gap); a lighter warm-up set is never scolded
- Proactive Telegram check-ins: PR congrats, streak milestones, and inactivity nudges (from 3 days idle, never more than every other day)
- Per-user timezone, settable in chat ("set my timezone to Tokyo", "I'm in London now") — relative dates like "yesterday" resolve in your current zone
- Intent classification with exercise and muscle group extraction in a single LLM call
- Exercise catalog seeded with 29 exercises; new ones are created as you log them, with a guessed muscle group. Equipment-aware matching keeps "dumbbell bench press" separate from barbell bench press, and different machines for the same movement stay separate because their loads aren't comparable
- Training principles (progression, deload, rep ranges, volume, etc.) injected into coaching prompts
- Workout statistics: "stats" (recent days, "more" to page back), "bench press history", PRs, weekly volume, consistency, weight trend
- Message logging — every interaction saved with intent, confidence, and response for debugging
- Telegram bot via long-polling — no port forwarding or dynamic DNS needed
- Podman container for deployment
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
pip install -e .        # or: uv pip install -e .
```

### Configure

```bash
cp .env.example .env
# Edit .env with your database credentials, LLM endpoint URL, and model name
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
podman build --format docker -t nunzio .
podman run --env-file .env nunzio
```

The container runs the Telegram bot by default.

To run it **full-time** (auto-start on boot, restart on crash) via systemd +
Podman Quadlet, see [`deploy/README.md`](deploy/README.md).

### Example usage

```
You: I did 3 sets of bench press at 185 lbs, 10 reps
You: ran 3 miles in 25 minutes
You: show my stats
You: what should I bench next session?
You: undo
You: low row 12@40
You: 12@55            (logged as Low Row)
You: again 2x12@55    (two more sets of 12 @ 55)
You: 5lb more         (last set becomes 60)
You: weight 179.8
You: did 1 set of purple band chest pull 10 reps
```

### Clean slate

To wipe all data and start fresh:

```bash
python scripts/create_tables.py    # drops and recreates all tables
python scripts/seed_exercises.py   # re-populates exercise catalog
python scripts/seed_principles.py  # re-populates training principles
```

### Upgrading

If you have an existing database, run migrations instead of recreating tables:

```bash
python scripts/migrate_v03.py   # v0.2 → v0.3: adds raw_exercise_name + message_log
python scripts/migrate_v05.py   # v0.3/v0.4 → v0.5: flattens sessions into sets
python scripts/migrate_v07.py   # → v0.7: adds user_settings (per-user timezone)
python scripts/migrate_v08.py   # → v0.8: adds proactive_log (check-in dedup)
python scripts/migrate_v09.py   # → v0.9: exercise cleanup — dry run; add --apply to write
```

All are idempotent — safe to run multiple times. `migrate_v07.py` and
`migrate_v08.py` only create new tables. `migrate_v09.py` changes data (merges
duplicate exercises, splits mis-matched sets, backfills muscle groups), so it
prints its plan unless you pass `--apply`. Back up `exercises` and `workout_sets` first.

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE__URL`: MySQL connection string
- `LLM__BASE_URL`: any OpenAI-compatible endpoint (currently llama-swap)
- `LLM__MODEL`: model to use (default `gemma-4-27b`)
- `TELEGRAM__TOKEN`: Bot token from BotFather
- `TELEGRAM__ALLOWED_USER_IDS`: JSON list of allowed Telegram user IDs (empty = open)

## Architecture

### How a message flows

```
User message
  → bare set ("12@55")? prefix the last exercise name (no LLM)
  → LLM classify_intent() → UserIntent (intent, confidence, exercises, muscle groups)
  → Route by intent:
      log_workout    → extract_workout_data() → scored exercise matching → DB persist → log comment
      log_weight     → extract body weight → plausibility guard → DB persist
      view_stats     → sub-route by stats_type → format response
      list_workouts  → recent workouts list
      edit_set       → extract_edit_set_data() + relative-delta parsing → update sets
      delete_workout → parse "undo"/"last"/batch ID → delete batch
      repeat_last    → regex-parsed overrides → clone sets (or N sets of the last one)
      set_timezone   → resolve IANA zone → user_settings
      coaching       → build_coaching_context() → generate_coaching_response()
  → Log to message_log table
  → Return response
```

### Intent routing

9 intents: `log_workout`, `log_weight`, `set_timezone`, `view_stats`, `list_workouts`, `edit_set`, `delete_workout`, `repeat_last`, and `coaching` (catch-all). Classification uses Instructor (JSON mode) with a fallback keyword matcher if the LLM call fails. `edit_set` extraction uses Instructor TOOLS mode (gemma returns all-null on that schema in JSON mode).

### Exercise matching

When logging a workout, the LLM extracts exercise names from natural language. These get matched against the exercise catalog in three tiers:

1. **Exact name match** — use it directly
2. **Scored match >= 0.5** — Jaccard similarity over normalized tokens (`exercise_names.py`: plurals, hyphens and synonyms like pec/pectoral→chest, flyes→fly are folded). If the names differ on an equipment or angle word (dumbbell, barbell, machine, cable, band, incline, decline…), the score is halved, so "dumbbell bench press" does not become "Bench Press". Use the best match, show the mapping in the response (e.g. `Incline Dumbbell Press (from "incline dumbbell bench")`)
3. **Score < 0.5** — create a new ad-hoc exercise with the user's exact name and a muscle group guessed from keywords (`guess_muscle_group()`)

History and edit lookups use the same 0.5 bar and prefer exercises the user has actually logged. The raw exercise name from the user is always preserved in `workout_sets.raw_exercise_name`.

### Coaching pipeline

`build_coaching_context()` in `llm/context.py` assembles a prompt block from:
1. Training principles by priority (plus cardio principles if relevant)
2. Consistency (frequency, streak, days since last workout) and weekly volume by muscle group
3. **YOUR EXERCISES** — every exercise from the last 90 days with its last session's sets
4. Lagging muscle groups (when no exercise is named) and the last few conversation turns
5. Matched exercises: guidance text, recent history grouped by batch, all-time PR
6. Body-weight readings and trend

This gets injected into the user message alongside a coaching system prompt. The LLM generates free-text advice (NOT Instructor — raw completions). The prompt only allows exercises from YOUR EXERCISES (unless the user asks for something new), bases weights on the last working sets in the same unit, never goes above the last working weight after a gap of a week or more, and never uses textbook loads or placeholders.

### Code layout

```
src/nunzio/
├── core.py            # MessageHandler: intent routing, all handlers, message logging
├── cli.py             # Interactive CLI (entry point: nunzio)
├── bot.py             # Telegram bot via long-polling (entry point: nunzio-bot)
├── checkin.py         # Proactive Telegram check-ins (PR / streak / nudge), hourly job
├── exercise_names.py  # Name normalization, match scoring, muscle-group guessing (pure)
├── stats.py           # Consistency stats (streak, gaps, frequency)
├── config.py          # Pydantic settings from .env
├── main.py            # Thin wrapper for CLI
├── database/
│   ├── connection.py  # Async SQLAlchemy engine + session manager
│   ├── models.py      # Exercise, WorkoutSet, MessageLog, TrainingPrinciple, BodyWeight, UserSettings, ProactiveLog
│   └── repository.py  # Repository pattern: CRUD + scored search, batch ops, delete
└── llm/
    ├── client.py      # OpenAI-compatible client + Instructor: classify, extract, coaching, log comments
    ├── context.py     # Coaching context assembly (roster, history, volume, principles)
    └── schemas.py     # Pydantic models: UserIntent, ExerciseSet, WorkoutData, EditSetData

scripts/
├── create_tables.py     # Drop + recreate all tables
├── seed_exercises.py    # Seed 29-exercise catalog
├── seed_principles.py   # Seed 9 training principles
├── clear_and_reseed.py  # Wipe data + reseed
├── migrate_v03.py       # v0.3 migration (raw_exercise_name + message_log)
├── migrate_v05.py       # v0.5 migration (flatten sessions into sets)
├── migrate_v07.py       # v0.7 migration (user_settings: per-user timezone)
├── migrate_v08.py       # v0.8 migration (proactive_log)
└── migrate_v09.py       # v0.9 exercise cleanup (dry run unless --apply)

tests/                         # 168 tests; most hit the real LLM + MySQL
├── test_exercise_matching.py  # Unit: scoring, normalization, muscle-group guessing
├── test_repeat_modifiers.py   # Unit: "again 12@30", "2x12@55", "one more set" parsing
├── test_relative_edit.py      # Unit: "5lb more" deltas, bare-set detection
├── test_roster.py             # Unit: YOUR EXERCISES coaching block
├── test_checkin.py            # Unit: check-in triggers + nudge spacing
├── test_log_personality.py    # Unit: log comment heuristics + summaries
├── test_expand_sets.py        # Unit: set expansion post-processing
├── test_repeat_last.py        # Integration: repeat, one more set, bare sets
├── test_edit_set.py           # Integration: edits incl. relative weight
├── test_delete_workout.py     # Unit + integration: undo/delete
├── test_coaching.py           # Integration: coaching context + response
├── test_llm_integration.py    # Integration: intent classification + extraction
├── test_db.py                 # Integration: DB connectivity + CRUD
└── ...                        # body weight, timezone, dates, stats, guards, defaults
```

### Database schema

| Table | Key columns | Purpose |
|-------|------------|---------|
| `exercises` | name, muscle_group, guidance | Exercise catalog (29 seeded + ad-hoc, muscle group guessed) |
| `workout_sets` | user_id, batch_id, set_date, exercise_id, set_number, reps, weight, weight_unit, duration_minutes, distance, raw_exercise_name, notes | Individual sets, grouped by batch_id per log message |
| `training_principles` | category, title, content, priority | Coaching knowledge (9 seeded) |
| `message_log` | user_id, raw_message, classified_intent, confidence, extracted_data, response_summary | Every interaction logged |
| `body_weight` | user_id, weight, unit, recorded_at, notes | Weigh-ins |
| `user_settings` | user_id, timezone | Per-user preferences |
| `proactive_log` | user_id, kind, ref_key, sent_at | Check-in dedup and nudge spacing |

### Key patterns

- **Config**: `from nunzio.config import config` — pydantic-settings, env vars with `__` delimiter
- **DB sessions**: `async with db_manager.get_session() as session:` — auto-commit/rollback
- **Repositories**: `exercise_repo`, `workout_set_repo`, `message_log_repo`, `training_principle_repo`, `body_weight_repo`, `user_settings_repo`, `proactive_log_repo`
- **LLM calls**: Instructor (JSON mode) for structured extraction, raw OpenAI client for coaching
- **Retries**: tenacity with exponential backoff on LLM calls
- **Two interfaces, shared core**: `MessageHandler` owns all logic. CLI is verbose (batch IDs), bot is terse.
- **User isolation**: `user_id` on every set/query. Telegram passes real user ID, CLI uses 0.

## Development

```bash
pip install -e .[dev]
ruff check src/ tests/
pytest tests/test_exercise_matching.py tests/test_repeat_modifiers.py \
       tests/test_relative_edit.py tests/test_roster.py tests/test_checkin.py  # unit (no services)
pytest tests/                                                              # full suite (needs LLM + MySQL)
```
