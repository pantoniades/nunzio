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

### 3. Apply the schema migration (adds the `user_settings` table)

The database already exists with real data, so **do not** run
`scripts/create_tables.py` (it drops tables). Run the non-destructive migration
instead — it only creates `user_settings` if it's missing:

```bash
# from a venv with the project installed (pip install -e .)
python scripts/migrate_v07.py
```

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

## Updating to a new version

```bash
git pull
podman build --format docker -t localhost/nunzio:latest .
python scripts/migrate_v07.py       # only if a new migration was added
systemctl --user restart nunzio
```

## Notes

- **Logs** go to journald (the bot logs to stdout). There's no bind-mounted log
  directory to manage.
- **Networking**: `Network=host` is what lets the existing `odysseus` hostnames
  resolve. If you ever move the bot off odysseus, drop `Network=host` and point
  the `.env` hostnames at the box running MySQL/the LLM.
- **Healthcheck**: baked into the image (`/app/healthcheck.py`, a `SELECT 1`
  against MySQL), so the unit needs no extra health config.
