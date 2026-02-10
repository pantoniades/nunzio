# Nunzio - Local Workout Assistant

## What This Is

A CLI workout tracker that uses local LLM (Ollama) for natural language understanding and a MySQL database for persistence. You say what you did in plain English, the LLM extracts structured data, and it gets saved to the database.

## Current State

Working end-to-end CLI prototype. The pipeline is: user input → LLM intent classification → LLM workout extraction → DB persistence → formatted response.

What works:
- Natural language workout logging via Ollama/Instructor structured extraction
- Exercise catalog seeded in DB (29 exercises across 8 muscle groups)
- Workout session + set persistence with Float weight + unit tracking
- Stats view (recent sessions, total volume, set counts)
- Exercise recommendations from DB by muscle group
- `nunzio` entry point via pyproject.toml

## Infrastructure

- **LLM**: Ollama on `odysseus:11434`, model `qwen3:30b-a3b` (configurable via .env)
- **DB**: MySQL on `odysseus:3306`, database `nunzio_workouts`
- **Structured extraction**: Instructor library wrapping Ollama for Pydantic model output

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
