# Deploying Nunzio full-time on odysseus

This runs the Telegram bot as a rootless **Podman Quadlet** service managed by
systemd — it starts on boot, restarts on crash, and logs to journald. MySQL and
the LLM (llama-swap) already run on `odysseus`; the container uses host
networking so it reaches them at the same `odysseus:3306` / `odysseus:11500`
hostnames the rest of the system uses.

## One-time setup

Run these on odysseus, from a checkout of this repo, as the user that will own
the service (not root).

### 1. Build the image

```bash
podman build --format docker -t localhost/nunzio:latest .
```

`--format docker` is required for the image's `HEALTHCHECK` to be honored
(podman's default OCI format silently ignores it).

### 2. Prepare config

The unit reads `~/Deploy/nunzio/.env` (the canonical deployment config, alongside
the other services under `~/Deploy`). Make sure it exists and is filled in.

`~/Deploy/nunzio/.env` must have at least:
- `DATABASE__URL=mysql+aiomysql://nunzio:<pw>@odysseus:3306/nunzio_workouts`
- `LLM__BASE_URL=http://odysseus:11500`
- `LLM__MODEL=<model>`
- `TELEGRAM__TOKEN=<bot token>`
- `TELEGRAM__ALLOWED_USER_IDS=[<your id>]` (recommended)
- `ENVIRONMENT=production`

### 3. Apply the schema migrations

The database already exists with real data, so **do not** run
`scripts/create_tables.py` (it drops tables). Run the non-destructive migrations
instead — each only creates its table if missing and is safe to re-run:

```bash
# from a venv with the project installed (uv pip install -e ".[dev]")
python scripts/migrate_v07.py   # user_settings (per-user timezone)
python scripts/migrate_v08.py   # proactive_log (proactive check-in dedup)
```

> **v0.8 needs the JobQueue extra.** Proactive check-ins run on
> `python-telegram-bot[job-queue]`, which is now in `pyproject.toml`, so a fresh
> `uv pip install -e .` / rebuilt image picks it up automatically. If the bot logs
> "JobQueue unavailable", the extra didn't install.

### 4. Install and start the service

```bash
# survive logout / reboot without an active session
loginctl enable-linger "$USER"

cp deploy/nunzio.container ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start nunzio
```

> **One poller at a time.** Telegram rejects a second `getUpdates` poller on the
> same token (HTTP 409). If the bot is currently running by hand (e.g. in a
> `tmux` session), stop that first, then start the service.

## Operating it

```bash
systemctl --user status nunzio      # is it running?
journalctl --user -u nunzio -f      # live logs
podman ps                           # health column shows the image healthcheck
systemctl --user restart nunzio     # restart
```

## Redeploying after continued development

There are two clones of this repo on odysseus, both on `master`:

- **`~/Projects/nunzio`** — where development happens.
- **`~/Deploy/nunzio`** — the deployment checkout. Holds the live `.env` (which
  the Quadlet unit reads) and is where the image is built from.

Both track the same GitHub remote, so the flow is: commit in Projects → push →
pull in Deploy → rebuild → restart.

```bash
# 1. In the dev clone: commit your work and push.
cd ~/Projects/nunzio
git add -A && git commit -m "..."
git push origin master

# 2. In the deploy clone: pull the new code.
cd ~/Deploy/nunzio
git pull --ff-only

# 3. Rebuild the image (--format docker is required for HEALTHCHECK).
podman build --format docker -t localhost/nunzio:latest .

# 4. Run any new DB migration (see "migrations" note below).
venv/bin/python scripts/migrate_v08.py    # latest; idempotent, safe to re-run

# 5. Restart the service onto the new image.
systemctl --user restart nunzio
systemctl --user status nunzio            # confirm active + healthy
journalctl --user -u nunzio -n 30         # confirm "Application started"
```

### Gotchas specific to this host

- **Use `uv`, not `pip`.** A middlebox on this network truncates HTTPS responses
  whose User-Agent is `requests`, which corrupts PyPI index pages and breaks
  `pip install` (and any `podman build` that shells out to pip). The Containerfile
  already installs deps with `uv`, so `podman build` works. For the host venvs
  (used to run migrations/tests), install with uv too:
  `uv pip install -e ".[dev]"` — `pip install` will fail. Install uv once with
  `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **`--format docker`** on every build — podman's default OCI format silently
  drops the `HEALTHCHECK`.
- **Migrations run from a host venv, not the container.** `scripts/` is not copied
  into the image, so run migrations from `~/Deploy/nunzio` with its venv
  (which needs `cryptography` for MySQL 8 auth — it's a project dependency, so a
  fresh `uv pip install -e .` covers it). Migrations are idempotent and
  non-destructive; safe to re-run.
- **One Telegram poller at a time** — don't run the bot by hand (CLI/tmux) while
  the service is up; the second `getUpdates` gets a 409.

## Notes

- **Logs** go to journald (the bot logs to stdout). There's no bind-mounted log
  directory to manage.
- **Networking**: `Network=host` is what lets the existing `odysseus` hostnames
  resolve. If you ever move the bot off odysseus, drop `Network=host` and point
  the `.env` hostnames at the box running MySQL/the LLM.
- **Healthcheck**: baked into the image (`/app/healthcheck.py`, a `SELECT 1`
  against MySQL), so the unit needs no extra health config.
