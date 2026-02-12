# Nunzio - Local Workout Assistant

## What This Is

A workout tracker with two interfaces — CLI and Telegram bot — that uses a local LLM (Ollama) for natural language understanding and MySQL for persistence. You say what you did in plain English, the LLM extracts structured data, and it gets saved to the database. Ask for coaching and it gives specific prescriptions based on your actual history.

## Current State

Working end-to-end via both CLI and Telegram bot. The pipeline is: user input → LLM intent classification (with exercise/muscle group extraction) → routing to log_workout, view_stats, or coaching → DB persistence or LLM coaching response.

What works:
- Natural language workout logging via Ollama/Instructor structured extraction (JSON mode)
- Cardio logging with duration_minutes and distance (not just sets/reps/weight)
- Exercise catalog seeded in DB (29 exercises across 8 muscle groups) with per-exercise coaching guidance
- Training principles table (9 principles: progression, deload, rep ranges, volume, etc.)
- Context-aware coaching: LLM gets the user's actual history, exercise guidance, and training principles injected into the prompt — gives specific prescriptions (sets/reps/weight) not generic advice
- Per-user data isolation: `user_id` (BigInteger) on `WorkoutSession`, all queries filtered. Telegram passes real user ID, CLI uses `user_id=0`
- Workout session + set persistence with Float weight + unit tracking
- Stats view (recent sessions, total volume, set counts)
- Intent classification extracts mentioned exercises and muscle groups in the same LLM call
- Telegram bot via long-polling (no port forwarding needed), with optional user ID restriction
- `nunzio` (CLI) and `nunzio-bot` (Telegram) entry points via pyproject.toml
- Containerfile for Podman deployment (runs the bot by default)

## Architecture

**Two interfaces, shared core** — `core.MessageHandler` owns all message processing logic. The CLI (`cli.py`) and Telegram bot (`bot.py`) are thin wrappers. The handler takes a `verbose` flag: CLI gets session IDs and debug detail, the bot gets cleaner output.

**Intent routing** — 3 intents: `log_workout`, `view_stats`, `coaching` (coaching is the catch-all).

**Coaching pipeline** — `build_coaching_context()` in `llm/context.py` assembles:
1. Training principles by priority (top 6, plus cardio principle if relevant)
2. Matched exercise details (fuzzy-matched from intent extraction)
3. Per-exercise guidance text (from `exercises.guidance` column)
4. Recent workout history per exercise (last 10 sets, grouped by session, with PR)

This context block is injected into the user message alongside a coaching system prompt. The LLM generates free-text advice (NOT Instructor — raw completions).

**Instructor mode** — Uses `instructor.Mode.JSON` (not TOOLS) because qwen generates multiple tool calls which Instructor can't handle.

## Infrastructure

- **LLM**: Ollama on `odysseus:11434`, model `qwen3:30b-a3b` (configurable via .env)
- **DB**: MySQL on `odysseus:3306`, database `nunzio_workouts`
- **Structured extraction**: Instructor library (JSON mode) wrapping Ollama for Pydantic model output
- **Container**: Podman via multi-stage Containerfile, runs `nunzio-bot` by default. Config via `--env-file`.

## Schema Changes (requires create_tables.py + re-seed)

- `workout_sessions` table: added `user_id` BIGINT NOT NULL with index
- `exercises` table: added `guidance` TEXT column
- `workout_sets` table: `reps` now nullable, added `duration_minutes` INT and `distance` FLOAT
- New `training_principles` table: `category`, `title`, `content`, `priority`

## Development Discipline

- **Run tests before considering any change done.** `pytest tests/` is the bar for "finished."
- **Write at least a smoke test when adding a new feature** — don't move on without one. The coaching context pipeline shipped with zero tests and the intent rename silently broke existing ones. That's what happens when tests aren't part of the workflow.
- Current tests hit real Ollama and MySQL. Mocking is on the TODO but isn't an excuse to skip running what exists.

## What's Next

- **Bug: "N sets of X" logs one set with set_number=N instead of N separate sets.**
  "did rear delt 2 sets of 10 40 lb" → logs only "Set 2 - 10 reps @40.0 lbs" instead of
  two separate sets. The LLM puts the count into `set_number` on a single ExerciseSet
  instead of emitting N ExerciseSet objects. Fix is likely prompt-level (better examples
  in the extraction prompt) and/or post-processing to expand a single set with
  set_number>1 into N copies.
- **Missing data should prompt a follow-up, not silently default.** Two variants:
  1. Missing weight: "set of 10 reps bench press" logs @bodyweight because weight is
     Optional and the display treats None as bodyweight.
  2. Missing reps: "2 sets of face pulls at 40 lb" logs 0 reps — the LLM leaves reps
     null/zero when not stated.
  Nunzio should either use sensible defaults (e.g. assume 10 reps for strength if
  unspecified) or ask the user to fill in the gap before saving. The follow-up approach
  is better but harder — requires conversation state, holding partial data in memory,
  and a confirmation flow. Touches core message handling.
- **Edit/delete workouts.** No way to fix mistakes after logging. "20 sets of 10 reps"
  gets recorded faithfully (correct behavior — no anomaly detection yet) but the user
  has no way to undo or correct it. Needs at minimum: delete last session, delete
  specific session by ID, and ideally edit individual sets. Could be commands ("delete
  last", "delete session #42") routed through intent classification, or explicit slash
  commands in Telegram (/undo, /delete).
- **Specify Dates.**: Currently everything is "now". User should be able to specify 
  "... yesterday" or "on Feb 24" and have the workout logged at the appropriate time.
- **LLM serving backend (TBD)**: Currently using Ollama, but may switch. The LLM client
  uses `openai.AsyncOpenAI` pointed at Ollama's `/v1` compat endpoint — the native
  `ollama` Python client doesn't work with Instructor. This means switching backends
  (vLLM, llama.cpp server, etc.) should be straightforward as long as they expose an
  OpenAI-compatible API. The `ollama` pip package is still in deps but unused at runtime.
- **Web search for recommendations**: Let Nunzio search the web to give better, more
  contextual workout suggestions instead of just listing exercises from the DB.
- **Personality (TBD)**: Nunzio should evolve a personality — tone, encouragement style,
  how he talks about workouts. Details to be figured out.
- Exercise name fuzzy matching (currently exact match + simple search fallback)
- Richer stats (PRs, volume trends, per-exercise history)
- Conversation context / multi-turn workout logging
- Proper test coverage with mocked LLM/DB (current tests hit real services)
