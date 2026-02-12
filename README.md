# Nunzio - Local Workout Assistant

A conversational workout tracking assistant that runs locally, using local LLMs for natural language understanding and MySQL for persistence. Tell Nunzio what you did in plain English, and he'll log it. Ask for advice, and he'll give specific prescriptions based on your actual history.

Two interfaces: interactive CLI for local use, Telegram bot for mobile (at the gym).

## Features

- Natural language workout logging ("I did 3 sets of bench press at 185 lbs")
- Cardio logging with duration and distance ("ran 3 miles in 25 minutes")
- Context-aware coaching based on your actual workout history, exercise guidance, and training principles
- Intent classification with exercise and muscle group extraction in a single LLM call
- Exercise catalog with 29 exercises across 9 muscle groups (including cardio)
- Training principles (progression, deload, rep ranges, volume, etc.) injected into coaching prompts
- Workout statistics and progress tracking
- Telegram bot via long-polling — no port forwarding or dynamic DNS needed
- Podman container for deployment
- Local LLM integration via Ollama + Instructor (JSON mode) for structured extraction
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
You: suggest some leg exercises
```

### Clean slate

To wipe all data and start fresh:

```bash
python scripts/create_tables.py    # drops and recreates all tables
python scripts/seed_exercises.py   # re-populates exercise catalog
python scripts/seed_principles.py  # re-populates training principles
```

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE__URL`: MySQL connection string
- `LLM__BASE_URL`: Ollama server URL
- `LLM__MODEL`: Model to use (e.g. `qwen3:30b-a3b`)
- `TELEGRAM__TOKEN`: Bot token from BotFather
- `TELEGRAM__ALLOWED_USER_IDS`: JSON list of allowed Telegram user IDs (empty = open)

## Architecture

Two interfaces (CLI, Telegram bot) share a common `core.MessageHandler`. Three intents: `log_workout`, `view_stats`, `coaching` (catch-all). The LLM classifies intent and extracts mentioned exercises/muscle groups in one call. Coaching queries go through a context assembly step that pulls the user's actual history, exercise guidance, and training principles before generating a response.

```
src/nunzio/
├── core.py            # Shared message processing (used by CLI and bot)
├── cli.py             # Interactive CLI
├── bot.py             # Telegram bot (long-polling)
├── config.py          # Pydantic settings (.env)
├── main.py            # Thin wrapper for CLI
├── database/
│   ├── connection.py  # Async engine + session manager
│   ├── models.py      # SQLAlchemy models
│   └── repository.py  # Repository pattern CRUD
└── llm/
    ├── client.py      # Ollama/Instructor: classify_intent, extract_workout_data, coaching
    ├── context.py     # Coaching context assembly (history, guidance, principles)
    └── schemas.py     # Pydantic models for LLM I/O

scripts/               # DB management scripts
tests/                 # Integration tests (hit real services)
```

## Development

```bash
pip install -e .[dev]
ruff check src/
pytest tests/
```

Note: current tests hit real Ollama and MySQL instances — no mocks yet.
