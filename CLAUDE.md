# Nunzio - Local Workout Assistant

## What This Is

A workout tracker with two interfaces — CLI and Telegram bot — that uses a local LLM (Ollama) for natural language understanding and MySQL for persistence. You say what you did in plain English, the LLM extracts structured data, and it gets saved to the database. Ask for coaching and it gives specific prescriptions based on your actual history.

## Current State

Working end-to-end via both CLI and Telegram bot. The pipeline is: user input → LLM intent classification (with exercise/muscle group extraction) → routing to log_workout, view_stats, coaching, delete_workout, or repeat_last → DB persistence or LLM coaching response.

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
- Delete/undo workouts: "undo", "delete last", "delete session #42" — routed via `delete_workout` intent
- Repeat last workout: "again", "repeat last" — clones most recent session via `repeat_last` intent
- Scored exercise matching: word-overlap Jaccard replaces ILIKE `%query%`. Exact match → use it, score ≥ 0.5 → use it (show mapping), score < 0.5 → create ad-hoc exercise with user's exact name
- Raw exercise name preserved: `workout_sets.raw_exercise_name` stores what the user actually said. Response shows mapping when names differ (e.g. `Dumbbell Flyes (from "dumbbell fly")`)
- Set-level notes pass through from LLM extraction to DB
- Notes extraction: LLM prompt extracts subjective observations and equipment modifiers into `notes` field, keeping exercise names clean
- Sensible defaults: missing reps default to 10 for strength sets (shown as "assumed" in response)
- Coaching context includes set notes (pain, effort, equipment) in history lines
- Message logging: every message logged to `message_log` table with intent, confidence, and response summary

## Architecture

**Two interfaces, shared core** — `core.MessageHandler` owns all message processing logic. The CLI (`cli.py`) and Telegram bot (`bot.py`) are thin wrappers. The handler takes a `verbose` flag: CLI gets session IDs and debug detail, the bot gets cleaner output.

**Intent routing** — 5 intents: `log_workout`, `view_stats`, `coaching` (catch-all), `delete_workout`, `repeat_last`.

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
- `workout_sets` table: `reps` now nullable, added `duration_minutes` INT, `distance` FLOAT, `raw_exercise_name` TEXT
- New `training_principles` table: `category`, `title`, `content`, `priority`
- New `message_log` table: `user_id`, `raw_message`, `classified_intent`, `confidence`, `extracted_data`, `response_summary`, `created_at`
- v0.3 migration: `scripts/migrate_v03.py` (adds `raw_exercise_name` column + creates `message_log` table)

## Development Discipline

- **Run tests before considering any change done.** `pytest tests/` is the bar for "finished."
- **Write at least a smoke test when adding a new feature** — don't move on without one. The coaching context pipeline shipped with zero tests and the intent rename silently broke existing ones. That's what happens when tests aren't part of the workflow.
- Current tests hit real Ollama and MySQL. Mocking is on the TODO but isn't an excuse to skip running what exists.

## What's Next

- ~~**Sensible defaults for missing reps.**~~ **Done (v0.4).** Missing reps default
  to 10 for strength sets; "(assumed)" shown in response. Cardio sets with
  `duration_minutes` are skipped. Follow-up prompting deferred (needs conversation state).
- **Edit individual sets.** Delete/undo works at session level. Still no way to edit
  a single set within a session (change weight, fix reps). Could be "edit set #3 to 12 reps"
  or "change weight on last set to 40 lbs".
- **Specify Dates.**: Currently everything is "now". User should be able to specify
  "... yesterday" or "on Feb 24" and have the workout logged at the appropriate time.
- **LLM serving backend (TBD)**: Currently using Ollama, but may switch. The LLM client
  uses `openai.AsyncOpenAI` pointed at Ollama's `/v1` compat endpoint — the native
  `ollama` Python client doesn't work with Instructor. This means switching backends
  (vLLM, llama.cpp server, etc.) should be straightforward as long as they expose an
  OpenAI-compatible API. The `ollama` pip package is still in deps but unused at runtime.
- **Web search for recommendations**: Let Nunzio search the web to give better, more
  contextual workout suggestions instead of just listing exercises from the DB.
- **Personality on log responses.** When logging a workout, Nunzio could add a brief
  context-aware comment based on the notes and history. E.g. if notes say "difficult set"
  → "Great job getting through it"; if the user jumped in weight → "Scale back if you
  feel pain". Needs a lightweight LLM call (or heuristic) after the log is saved, appended
  to the confirmation message. Keep it one line, not an essay.
- **Proactive check-ins (cron).** Nunzio should reach out unprompted via Telegram:
  congratulate when a session shows upward trends (new PR, volume increase, consistency
  streak), and nudge if the user hasn't logged a workout in N days. Needs a scheduled
  job (cron or async loop) that queries recent history per user, runs trend detection,
  and sends a message through the bot. Personality lives here too — tone, encouragement
  style, how blunt the nudges are.
- ~~**Extract equipment/variant modifiers into set notes.**~~ **Done (v0.4).** Extraction
  prompt now tells the LLM to put subjective observations (pain, effort, mood) and
  equipment modifiers (band color, grip width, tempo) into `notes`, keeping exercise
  names clean. Notes also surface in coaching context history lines.
- **Workout notes.** Set-level notes now pass through from extraction to DB and appear
  in coaching context. Session-level notes from freeform text (e.g. "shoulder hurt")
  aren't extracted separately — the raw message is stored as session notes, which is
  a rough approximation.
- **Body weight tracking.** New intent: "weighed 191.4 lb" saves the user's weight with
  timestamp. New `body_weight` table: `user_id`, `weight`, `unit`, `recorded_at`. Needs
  a new intent in classification (e.g. `log_weight`), a simple extraction model, and a
  way to view history ("what's my weight trend?"). Could tie into coaching context too —
  the LLM knowing the user's weight trend is useful for advice.
- Richer stats (PRs, volume trends, per-exercise history)
- Conversation context / multi-turn workout logging
- Proper test coverage with mocked LLM/DB (current tests hit real services)
