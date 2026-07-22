# Nunzio - Local Workout Assistant

## What This Is

A workout tracker with two interfaces — CLI and Telegram bot — that uses a local LLM for natural language understanding and MySQL for persistence. You say what you did in plain English, the LLM extracts structured data, and it gets saved to the database. Ask for coaching and it gives specific prescriptions based on your actual history.

## Current State

Working end-to-end via both CLI and Telegram bot. The pipeline is: user input → LLM intent classification (with exercise/muscle group extraction) → routing to log_workout, view_stats, coaching, delete_workout, or repeat_last → DB persistence or LLM coaching response.

What works:
- Natural language workout logging via Instructor structured extraction (JSON mode)
- Cardio logging with duration_minutes and distance (not just sets/reps/weight)
- Exercise catalog seeded in DB (29 exercises across 8 muscle groups) with per-exercise coaching guidance
- Training principles table (9 principles: progression, deload, rep ranges, volume, etc.)
- Context-aware coaching: LLM gets the user's actual history, exercise guidance, and training principles injected into the prompt — gives specific prescriptions (sets/reps/weight) not generic advice
- Per-user data isolation: `user_id` (BigInteger) on `WorkoutSet`, all queries filtered. Telegram passes real user ID, CLI uses `user_id=0`
- Flat data model: no session table, sets have `user_id`, `batch_id`, `set_date` directly. `batch_id` groups sets from a single log message.
- Timezone-aware dates: `set_date` stored in America/New_York via `zoneinfo`
- Date specification: "yesterday", "on Monday", "Feb 15" etc. resolved by LLM to concrete dates. Today's date injected into extraction prompt. Response header shows date when not today.
- Stats view with sub-types: overview (last 3 days), PRs (heaviest per exercise), exercise history, weekly volume trends, consistency (streak, frequency, avg gap)
- Log response personality: heuristic one-liner after logging (new PR, first time, back after gap, weight increase, pain warning). Pure code, no LLM call.
- Proper logging: `logging.getLogger(__name__)` across all modules. CLI and bot configure via `config.logging.level`.
- Intent classification extracts mentioned exercises and muscle groups in the same LLM call
- Telegram bot via long-polling (no port forwarding needed), with optional user ID restriction
- `nunzio` (CLI) and `nunzio-bot` (Telegram) entry points via pyproject.toml
- Containerfile for Podman deployment (runs the bot by default)
- Delete/undo workouts: "undo", "delete last", "delete #42" — routed via `delete_workout` intent
- Edit individual sets: "change reps to 12", "fix weight to 185", "edit last set" — routed via `edit_set` intent (LLM extracts which set + what to change)
- Body weight tracking: "weighed 191.4 lb" — routed via `log_weight` intent, persisted in `body_weight` table, weigh-in trends shown on log
- Repeat last workout: "again", "repeat last" — clones most recent batch via `repeat_last` intent. Inline override syntax: "again 10x55" or "Another, 10x50 kg" applies reps and weight overrides (regex-parsed, no LLM call)
- Resident-model reuse: when llama-swap has a model from the JSON-mode allowlist (`qwen3.5-27b`, `qwen3-coder-30b`, `gemma-4-27b`) already loaded, Nunzio uses it to skip swap latency. Other resident models force a swap back to the configured default. Override is shown in the response footer and logged at INFO on transitions.
- Scored exercise matching: word-overlap Jaccard replaces ILIKE `%query%`. Exact match → use it, score ≥ 0.5 → use it (show mapping), score < 0.5 → create ad-hoc exercise with user's exact name
- Raw exercise name preserved: `workout_sets.raw_exercise_name` stores what the user actually said. Response shows mapping when names differ (e.g. `Dumbbell Flyes (from "dumbbell fly")`)
- Set-level notes pass through from LLM extraction to DB
- Notes extraction: LLM prompt extracts subjective observations and equipment modifiers into `notes` field, keeping exercise names clean
- Sensible defaults: missing reps default to 10 for strength sets (shown as "assumed" in response)
- Coaching context includes set notes (pain, effort, equipment) in history lines
- Message logging: every message logged to `message_log` table with intent, confidence, and response summary (v0.8: `extracted_data` now stores the classified intent JSON)

### v0.8 additions
- Default model switched to `gemma-4-27b` (was `qwen3.5-27b`); `edit_set` extraction routed through Instructor `Mode.TOOLS` because gemma returns all-null on the all-optional `EditSetData` schema under JSON mode
- Reps/weight inversion guard: unitless "8x30" that the extractor flips to 30 reps @ 8 lb is corrected back to 8 reps @ 30 lb (with a "say 'edit' if I flipped it" note); a new `NxM` rule in the extraction prompt prevents most flips upstream
- Body-weight plausibility guard: an implausible reading (e.g. "20 lb") is rejected with guidance instead of silently stored; weigh-in delta reconciles kg↔lb units before subtracting
- Hybrid log comments: notable logs get an LLM-written, numbers-grounded one-liner (heuristic fallback)
- Coaching overhaul: true all-time PRs (not window-local), no more truncation of fetched volume/history, a LAGGING MUSCLE GROUPS block when no exercise is named, and a short RECENT CONVERSATION memory block
- Proactive check-ins via PTB JobQueue (`checkin.py`): PR congrats / streak milestones / inactivity nudges with a focus suggestion, deduped in `proactive_log`
- UX: bare "edit" echoes the target set; "more" paginates the stats overview; category queries ("what aerobic have I done") summarize a muscle group

## Architecture

**Two interfaces, shared core** — `core.MessageHandler` owns all message processing logic. The CLI (`cli.py`) and Telegram bot (`bot.py`) are thin wrappers. The handler takes a `verbose` flag: CLI gets session IDs and debug detail, the bot gets cleaner output.

**Intent routing** — 9 intents: `log_workout`, `log_weight`, `set_timezone`, `view_stats`, `list_workouts`, `edit_set`, `delete_workout`, `repeat_last`, and `coaching` (catch-all). `view_stats` sub-routes by `stats_type` field on `UserIntent`: overview (default), prs, exercise_history, volume, consistency, weight, last_session.

**Coaching pipeline** — `build_coaching_context()` in `llm/context.py` assembles:
1. Training principles by priority (top 6, plus cardio principle if relevant)
2. Matched exercise details (fuzzy-matched from intent extraction)
3. Per-exercise guidance text (from `exercises.guidance` column)
4. Recent workout history per exercise (last 10 sets, grouped by batch_id, with PR)

This context block is injected into the user message alongside a coaching system prompt. The LLM generates free-text advice (NOT Instructor — raw completions).

**Instructor mode** — Uses `instructor.Mode.JSON` (not TOOLS) because some models generate multiple tool calls which Instructor can't handle. **Exception:** `edit_set` extraction uses `Mode.TOOLS` — the all-optional `EditSetData` schema causes `gemma-4-27b` to return an all-null object under JSON mode, but it extracts correctly under TOOLS (and so does qwen). The client holds two instructor clients (`_instructor_client` JSON, `_instructor_tools_client` TOOLS).

**Proactive check-ins** — `checkin.py` runs as an in-process PTB JobQueue job (hourly, wired in `bot.py` `_post_init`). For each recipient whose local time is `CHECKIN_HOUR`, `compute_checkin()` picks the top-priority trigger (fresh PR > streak milestone > inactivity nudge with a suggested lagging-group focus) and sends one message via `bot.send_message`, deduped through the `proactive_log` table. Recipients come from `TELEGRAM__ALLOWED_USER_IDS` (or all logged users if unrestricted, never `user_id=0`). Requires the `python-telegram-bot[job-queue]` extra.

**Log comments (hybrid)** — After a log, `_generate_log_comment()` heuristic decides if anything's notable (PR/first-time/gap/weight-up/pain). If so, it's upgraded to an LLM-written, numbers-grounded one-liner via `LLMClient.generate_log_comment()`; on any failure it falls back to the heuristic string.

## Infrastructure

- **LLM**: OpenAI-compatible API (currently llama-swap on `odysseus:11500`), default model `gemma-4-27b` (configurable via .env; `qwen3.5-27b` and `qwen3-coder-30b` also in the resident-reuse allowlist)
- **DB**: MySQL on `odysseus:3306`, database `nunzio_workouts`
- **Structured extraction**: Instructor library (JSON mode) wrapping OpenAI client for Pydantic model output
- **Container**: Podman via multi-stage Containerfile (built with `uv`, not pip), runs `nunzio-bot` by default. Config via `--env-file`.
- **Deployment**: runs full-time on odysseus as a rootless Podman Quadlet systemd service (`nunzio.service`), monitored by `~/admin/health-check.sh`. Two clones: `~/Projects/nunzio` (dev) and `~/Deploy/nunzio` (build/run, holds the live `.env`). Redeploy + host-specific gotchas (uv, `--format docker`, migrations) documented in [`deploy/README.md`](deploy/README.md).

## Schema (v0.5 — flat model)

- `workout_sets` table: `user_id` BIGINT, `batch_id` INT, `set_date` DATETIME (NYC tz), `exercise_id` FK, `set_number`, `reps` (nullable), `weight` FLOAT, `weight_unit`, `duration_minutes`, `distance`, `raw_exercise_name`, `notes`, `created_at`
- `exercises` table: `name`, `muscle_group`, `description`, `guidance`, `created_at`
- `training_principles` table: `category`, `title`, `content`, `priority`
- `message_log` table: `user_id`, `raw_message`, `classified_intent`, `confidence`, `extracted_data` (now populated with the classified `UserIntent` JSON), `response_summary`, `created_at`
- `proactive_log` table (v0.8): `user_id`, `kind` (pr/streak/nudge), `ref_key`, `sent_at` — dedup for proactive check-ins. Created by `scripts/migrate_v08.py` (idempotent, non-destructive)
- **Dropped**: `workout_sessions` table (v0.5 — flattened into workout_sets)
- v0.5 migration: `scripts/migrate_v05.py` (backfills user_id/set_date/batch_id from sessions, drops session_id + workout_sessions)

## Development Discipline

- **Run tests before considering any change done.** `pytest tests/` is the bar for "finished."
- **Write at least a smoke test when adding a new feature** — don't move on without one. The coaching context pipeline shipped with zero tests and the intent rename silently broke existing ones. That's what happens when tests aren't part of the workflow.
- Current tests hit real LLM and MySQL. Mocking is on the TODO but isn't an excuse to skip running what exists.

## What's Next

- ~~**Sensible defaults for missing reps.**~~ **Done (v0.4).** Missing reps default
  to 10 for strength sets; "(assumed)" shown in response. Cardio sets with
  `duration_minutes` are skipped. Follow-up prompting deferred (needs conversation state).
- ~~**Edit individual sets.**~~ **Done.** `edit_set` intent routes "change reps to 12",
  "fix weight to 185", "edit last set", "#42 set 3 to 200 lbs" through Instructor
  extraction (`EditSetData` schema) to a repository update.
- ~~**Per-user timezone preferences.**~~ **Done (v0.7).** `user_settings` table
  (`scripts/migrate_v07.py`) with a `timezone` column; a `set_timezone` intent resolves
  the IANA name via the LLM and persists it (`core._handle_set_timezone`). No longer
  hardcoded to America/New_York (that's just the default).
- ~~**Specify Dates.**~~ **Done (v0.6).** Today's date injected into extraction prompt;
  LLM resolves relative dates ("yesterday", "on Monday", "Feb 15") to concrete
  `YYYY-MM-DD` via `WorkoutData.date` field. `core.py` uses extracted date when present,
  falls back to `_now_nyc()`. Response header shows the date when it's not today
  (e.g. `Logged workout (#5) for Feb 17:`).
- ~~**LLM serving backend (TBD)**~~ **Done.** Switched from Ollama to llama-swap.
  The LLM client uses `openai.AsyncOpenAI` pointed at any OpenAI-compatible `/v1`
  endpoint — switching backends (vLLM, llama.cpp server, Ollama, etc.) just means
  changing `LLM__BASE_URL` and `LLM__MODEL` in `.env`.
- **Web search for recommendations**: Let Nunzio search the web to give better, more
  contextual workout suggestions instead of just listing exercises from the DB.
- ~~**Personality on log responses.**~~ **Done (v0.5; upgraded v0.8).** Heuristic
  one-liners (new PR, first time, back after gap, weight increase, pain warning), now
  hybrid: when the heuristic fires, an LLM writes a numbers-grounded one-liner via
  `LLMClient.generate_log_comment()`, falling back to the heuristic on any failure.
  Future: tone configuration (encouraging/blunt/sarcastic).
- ~~**Proactive check-ins.**~~ **Done (v0.8).** `checkin.py` runs as an in-process PTB
  JobQueue job (hourly). Per user, in their local timezone, it picks the top-priority
  trigger — fresh PR > streak milestone > inactivity nudge (with a lagging-group focus
  suggestion) — and sends one Telegram message, deduped via the `proactive_log` table.
  Future: richer tone/personality, volume-trend congratulations, per-user check-in hour.
- ~~**Extract equipment/variant modifiers into set notes.**~~ **Done (v0.4).** Extraction
  prompt now tells the LLM to put subjective observations (pain, effort, mood) and
  equipment modifiers (band color, grip width, tempo) into `notes`, keeping exercise
  names clean. Notes also surface in coaching context history lines.
- **Workout notes.** Set-level notes now pass through from extraction to DB and appear
  in coaching context. Session-level notes from freeform text (e.g. "shoulder hurt")
  aren't extracted separately — the raw message is stored as session notes, which is
  a rough approximation.
- ~~**Body weight tracking.**~~ **Done.** `log_weight` intent + `body_weight` table
  (`user_id`, `weight`, `unit`, `recorded_at`, `notes`). Weigh-in delta vs. previous
  reading is shown on log ("↓ 2.3 lbs from last weigh-in on Mar 21"). View via
  `view_stats` with `stats_type="weight"`.
- **Per-user settings — weight_unit + `set_preference`.** *Partially done (v0.7).* The
  `user_settings` table now exists and timezone is wired through a `set_timezone` intent.
  Still open: `weight_unit` remains per-set (`workout_sets.weight_unit`), not a user
  preference, and there's no general `set_preference` intent. The Apr 21 "Store as lb,
  not kg" message hit the coaching path and the LLM hallucinated compliance — but the
  next log was still in kg. Needs a `weight_unit` column on `user_settings` plus a
  `set_preference` intent so unit/preference statements stop falling through to coaching.
- ~~**Bare "Edit" with no target.**~~ **Partially done (v0.8).** A bare "edit" now
  defaults to the most recent set and echoes it ("Editing Lat Pulldown 10×40 in #135 —
  what should I change?") instead of dead-ending. Supplying the value in a follow-up
  still needs conversation state (not yet built).
- ~~Richer stats (PRs, volume trends, per-exercise history)~~ **Done (v0.5).** `view_stats`
  sub-routes by `stats_type`. PRs, exercise history, weekly volume by muscle group,
  consistency metrics (streak, avg gap, 30/90-day counts).
- Conversation context / multi-turn workout logging
- Proper test coverage with mocked LLM/DB (current tests hit real services)
