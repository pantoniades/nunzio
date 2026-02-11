# Nunzio - Local Workout Assistant

## What This Is

A CLI workout tracker that uses local LLM (Ollama) for natural language understanding and a MySQL database for persistence. You say what you did in plain English, the LLM extracts structured data, and it gets saved to the database.

## Current State

Working end-to-end CLI with context-aware coaching. The pipeline is: user input → LLM intent classification (with exercise/muscle group extraction) → routing to log_workout, view_stats, or coaching → DB persistence or LLM coaching response.

What works:
- Natural language workout logging via Ollama/Instructor structured extraction (JSON mode)
- Cardio logging with duration_minutes and distance (not just sets/reps/weight)
- Exercise catalog seeded in DB (29 exercises across 8 muscle groups) with per-exercise coaching guidance
- Training principles table (9 principles: progression, deload, rep ranges, volume, etc.)
- Context-aware coaching: LLM gets the user's actual history, exercise guidance, and training principles injected into the prompt — gives specific prescriptions (sets/reps/weight) not generic advice
- Workout session + set persistence with Float weight + unit tracking
- Stats view (recent sessions, total volume, set counts)
- Intent classification extracts mentioned exercises and muscle groups in the same LLM call
- `nunzio` entry point via pyproject.toml

## Architecture

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

## Schema Changes (requires create_tables.py + re-seed)

- `exercises` table: added `guidance` TEXT column
- `workout_sets` table: `reps` now nullable, added `duration_minutes` INT and `distance` FLOAT
- New `training_principles` table: `category`, `title`, `content`, `priority`

## What's Next

- **LLM serving backend (TBD)**: Currently using Ollama, but may switch. The LLM client
  uses `openai.AsyncOpenAI` pointed at Ollama's `/v1` compat endpoint — the native
  `ollama` Python client doesn't work with Instructor. This means switching backends
  (vLLM, llama.cpp server, etc.) should be straightforward as long as they expose an
  OpenAI-compatible API. The `ollama` pip package is still in deps but unused at runtime.
- **Web search for recommendations**: Let Nunzio search the web to give better, more
  contextual workout suggestions instead of just listing exercises from the DB.
- **Personality (TBD)**: Nunzio should evolve a personality — tone, encouragement style,
  how he talks about workouts. Details to be figured out.
- Telegram bot integration (config is stubbed, no bot code yet)
- Exercise name fuzzy matching (currently exact match + simple search fallback)
- Richer stats (PRs, volume trends, per-exercise history)
- Conversation context / multi-turn workout logging
- Proper test coverage with mocked LLM/DB (current tests hit real services)
