# Nunzio - Local Workout Assistant

A conversational workout tracking assistant that runs locally, using local LLMs for natural language understanding and MySQL for persistence.

## Features

- Natural language workout logging ("I did 3 sets of bench press at 185 lbs")
- Local LLM integration via Ollama + Instructor for structured extraction
- Exercise catalog with 29 exercises across 8 muscle groups
- Workout statistics and progress tracking
- Complete privacy - everything runs locally

## Quick Start

### Prerequisites

- Python 3.12+
- MySQL 8.4+
- Ollama running with a model available

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

Then create tables and seed the exercise catalog:

```bash
python scripts/create_tables.py
python scripts/seed_exercises.py
```

### Run the CLI

```bash
nunzio
```

Then try:

```
You: I did 3 sets of bench press at 185 lbs, 10 reps
You: show my stats
You: suggest some leg exercises
You: help
You: exit
```

### Clean slate

To wipe all data and start fresh:

```bash
python scripts/create_tables.py    # drops and recreates all tables
python scripts/seed_exercises.py   # re-populates exercise catalog
```

## Configuration

Key environment variables (see `.env.example`):

- `DATABASE__URL`: MySQL connection string
- `LLM__BASE_URL`: Ollama server URL
- `LLM__MODEL`: Model to use (e.g. `qwen3:30b-a3b`)

## Architecture

```
src/nunzio/
├── cli.py             # Interactive CLI (entry point)
├── config.py          # Pydantic settings (.env)
├── main.py            # Thin wrapper for CLI
├── database/
│   ├── connection.py  # Async engine + session manager
│   ├── models.py      # SQLAlchemy models
│   └── repository.py  # Repository pattern CRUD
└── llm/
    ├── client.py      # Ollama/Instructor: classify_intent, extract_workout_data
    └── schemas.py     # Pydantic models for LLM I/O

scripts/               # DB management scripts
tests/                 # pytest tests
```

## Development

```bash
pip install -e .[dev]
ruff check src/
pytest tests/
```
