# Ultimate PDF Telegram Assistant

A Persian-first, English-capable Telegram document assistant built with aiogram 3, FastAPI, SQLAlchemy 2, PostgreSQL, Redis/Arq, PyMuPDF, pypdf, and isolated worker subprocesses.

> **Scope note:** this is a functional integrated foundation, not a claim that every feature in the original wish-list is implemented. See `docs/FEATURE_COVERAGE.md` and `docs/SECURITY.md` for exactly what is and is not present.

## Quick start

Requirements: Docker Compose v2 and a Telegram bot token from BotFather.

```bash
cp .env.example .env
# Set BOT_TOKEN, POSTGRES_PASSWORD, and use the same password in DATABASE_URL.
# Example: POSTGRES_PASSWORD=local-dev-secret
# DATABASE_URL=postgresql+asyncpg://pdfbot:local-dev-secret@postgres:5432/pdfbot
docker compose up --build
```

The stack starts PostgreSQL, Redis, one-shot Alembic migrations, the Telegram bot, an Arq worker, and a loopback-bound health API at `http://127.0.0.1:8000/health/ready`. The Telegram bot/worker require a valid `BOT_TOKEN`. Keep API_BIND on `127.0.0.1` unless intentionally placing the API behind a trusted reverse proxy.

## Local development

Python 3.12+ is required (3.13 is also supported by declared package ranges). PostgreSQL and Redis are needed for full application integration; the PDF unit suite runs locally without them.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test,ocr]'
ruff check .
pytest -q
```

Useful commands: `make test`, `make lint`, `make typecheck`, `make security`, `make migrate`, `make up`, `make down`.

## User journey

Send a PDF to the bot; it checks actual file content, size, encryption, and page count, then shows applicable actions. Implemented processing happens in an Arq worker, not in the update handler; results are returned as a separate file. Originals are not overwritten. `/settings` changes Persian/English, `/history` shows recent job states, `/cancel` asks Arq to abort the user's newest active job, `/privacy` and `/help` describe the service.

## Important limits

Defaults cap uploads at 20 MiB and PDFs at 500 pages; OCR caps at 100 pages; file expiry defaults to 24 hours; outputs above 49 MiB cannot be delivered through this Bot API workflow. Configure carefully for Telegram's currently applicable Bot API limits and your deployment. Local storage is appropriate for one host; use private object storage and a shared job/storage adapter before horizontal scaling workers across hosts. External conversion/OCR is best-effort; ensure fonts and Tesseract language packs are installed. See `docs/`.
