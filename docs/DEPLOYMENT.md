# Deployment and operations

## Docker Compose (recommended starting point)

1. Install Docker Engine and Docker Compose v2 on a Linux host.
2. `cp .env.example .env`; set `BOT_TOKEN` and replace `POSTGRES_PASSWORD` with a long random password. Use the exact same password in `DATABASE_URL` (`postgresql+asyncpg://pdfbot:<password>@postgres:5432/pdfbot`). Use URL-encoded credentials if the password contains URL-reserved characters.
3. Keep `API_BIND=127.0.0.1` unless a trusted reverse proxy is configured. The API exposes only liveness/readiness checks.
4. Start with `docker compose up --build -d`, inspect `docker compose ps`, and tail logs using `docker compose logs -f bot worker api migrate`.
5. Verify `curl http://127.0.0.1:8000/health/ready`, then send `/start` to the bot.

The compose file starts PostgreSQL and Redis, runs Alembic once, then starts bot, worker and the health API. Bot and worker are non-root, have dropped capabilities, a read-only root filesystem and resource limits. `deploy.resources` support depends on the Compose implementation; configure host/container quotas independently for your environment. Docker build and runtime have not been executed in this workspace because Docker is unavailable here.

## Local validation

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e '.[test,ocr]'
ruff format --check .
ruff check .
mypy app
pytest -q --cov=app
bandit -r app -q
pip-audit --skip-editable
deptry .
```

To run the bot outside Compose, point `DATABASE_URL` to PostgreSQL, `REDIS_URL` to Redis, `STORAGE_ROOT` and `TEMP_ROOT` to private writable directories, and install `BOT_TOKEN`. Run `alembic upgrade head` first, then in separate processes `python -m app.main` and `arq app.workers.worker.WorkerSettings`. Start API if needed with `uvicorn app.api.main:app --host 127.0.0.1 --port 8000`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `BOT_TOKEN` | empty (required) | Telegram bot token; never log/commit it. |
| `POSTGRES_PASSWORD` | sample only | Compose database password; set a strong secret and synchronize with `DATABASE_URL`. |
| `DATABASE_URL` | local SQLite | Async SQLAlchemy URL; Compose uses PostgreSQL service hostname. |
| `REDIS_URL` | local Redis | Arq queue and rate-limit backend. |
| `STORAGE_ROOT` | `./data/files` | Private local file store; use shared object storage before scaling across hosts. |
| `TEMP_ROOT` | `./tmp` | Private temporary download space. |
| `MAX_UPLOAD_BYTES` | 20 MiB | Post-download upload limit. |
| `MAX_PDF_PAGES` | 500 | Maximum accepted PDF page count. |
| `MAX_CONCURRENT_JOBS` | 2 | In-process worker semaphore; not a distributed per-user limit. |
| `JOB_TIMEOUT_SECONDS` | 180 | Parent-process deadline; child process group is killed on expiry/cancellation. |
| `FILE_TTL_HOURS` | 24 | File expiry; worker cleanup runs hourly. |
| `RATE_LIMIT_PER_MINUTE` | 10 | Per-user Redis message/callback rate. It fails open when Redis is down. |
| `API_BIND` | `127.0.0.1` | Host bind address for optional health API port in Compose. |
| `API_PORT` | 8000 | Host port mapped to the API container. |
| `LOG_LEVEL` | `INFO` | Structured log level. |
| `DEFAULT_LANGUAGE` | `fa` | Initial Persian or English preference. |
| `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | empty/default | Reserved opt-in provider config; Q&A is not exposed in Telegram yet. |

## Migrations and backups

Migrations run automatically on a fresh Compose start through the one-shot `migrate` service. For manual work use `alembic upgrade head`; inspect before applying changes to an existing database. Do not use downgrade commands on production data without an approved backup/restore plan.

Example logical PostgreSQL backup (store in an encrypted, access-controlled backup system, not the application host's public web root):

```bash
mkdir -p backups
umask 077
docker compose exec -T postgres pg_dump -U pdfbot -d pdfbot -Fc > backups/pdfbot-$(date -u +%F).dump
```

Back up the private `file_data` volume consistently with metadata snapshots; PostgreSQL backups alone do not contain document bytes. Test restore into an isolated environment on a regular schedule. Redis queue state is not a durable job ledger: PostgreSQL job rows are authoritative, and stale queued-job reconciliation is future work.

## Troubleshooting

- Bot/worker exits immediately: check `BOT_TOKEN`, `docker compose logs bot worker`, then verify PostgreSQL/Redis health.
- Migration fails: confirm PostgreSQL health and that URL credentials match `POSTGRES_PASSWORD`; inspect `docker compose logs migrate`.
- OCR unavailable/language error: the image includes Tesseract English, Persian (`fas`) and Arabic (`ara`) packs; check `tesseract --list-langs` in the worker image.
- Office conversion unavailable: ensure LibreOffice modules were installed in the worker image. Layout changes are possible.
- File rejected: check actual content, upload size, PDF page count and encryption; renaming a file does not change its content type.
- Result too large: Telegram delivery is capped at 49 MiB here; reduce input/page count. External expiring links are not implemented.
- API readiness fails: verify DB/Redis reachability. Do not publish the health API publicly without a private network/reverse-proxy policy.
