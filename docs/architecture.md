# Architecture and request flow

## Layers

- `app/bot`: aiogram 3 Telegram handlers, inline/reply keyboards and Redis-based rate limiting.
- `app/api`: optional FastAPI liveness/readiness endpoints; no public document endpoints.
- `app/services`: Arq queue submission and opt-in provider-independent AI retrieval abstraction.
- `app/domain`: SQLAlchemy entities and the `Operation` plugin contract.
- `app/processors/pdf`: allowlisted PDF, image, OCR and LibreOffice operation adapters.
- `app/storage`: content validation and per-user local file isolation. The adapter boundary is where private S3/MinIO storage can be added.
- `app/workers`: Arq job runner; each document transform is launched as a child Python process with Linux CPU/address-space/file-descriptor/file-size/core limits. OCR is single-job and the Compose worker has a PID ceiling.
- `migrations`: Alembic schema revisions.

## PDF upload → result path

1. Telegram message handler checks the advertised size, downloads to a random temporary file, and performs cheap signature/size checks off the event loop. PDF parsing/page-count/encryption checks and OOXML central-directory parsing/classification run in a resource-limited child subprocess during preflight; the bot process does not parse untrusted PDF or ZIP container structures.
2. It moves the input to `/data/files/<Telegram-user-id>/<random-uuid>.<validated-extension>`, saves metadata/expiry in PostgreSQL, and displays only the operations compatible with the detected type.
3. Callback authorization re-queries the file by both opaque file ID and owner ID, persists a job, and enqueues an allowlisted Arq function in Redis.
4. The worker marks the job running, launches a subprocess with an argument array (never a shell), an operation name from a fixed registry, and JSON options. The subprocess applies POSIX limits and returns metadata through a one-use sidecar.
5. The worker sends a separate output with `FSInputFile`, records the result and expiry, and updates job status. Inputs are never overwritten. Expiry cleanup excludes queued/running/cancelling source files; isolated child processes receive a private per-job `HOME`/`TMPDIR`, and operation-specific scratch artifacts are cleaned after normal completion, failure, timeout, or cancellation.

## Persistence

PostgreSQL stores users, user language, file metadata/storage references, jobs, result metadata, history, saved-workflow/favorite definitions and daily usage stats. It does not store document bytes. Alembic revisions create/upgrade the schema. Redis coordinates Arq jobs and per-user rate counters.

## Operation interface

Each plugin implements `validate(source, options)`, `execute(source, destination, options)`, and inherits metadata/estimate/cleanup hooks. The worker process imposes hard resource limits; operation adapters are synchronous and never run on the bot update loop.

## Dependency-analysis note

`deptry` DEP002 is ignored only for a named set of non-imported dependencies: Uvicorn and OCRmyPDF are command-line entry points; `asyncpg` and `aiosqlite` are dynamically selected by SQLAlchemy URL schemes; pytest and the lint/type/security tools are invoked by the Make/CI commands. These exact exceptions are listed under `tool.deptry.per_rule_ignores` in `pyproject.toml`; other unused dependencies remain reportable. Revisit the list when deployment, database URLs, OCR invocation, or test tooling changes.

## Deliberate boundaries

The currently wired Telegram UI is a narrow vertical slice, not all of the originally requested tool catalogue. In particular, no object-store backend, multi-upload merge conversation, durable workflow engine, or AI question-answering Telegram flow is wired yet. See `FEATURE_COVERAGE.md`. Redis/PostgreSQL must be reachable for end-to-end bot processing. Local SQLite is intended only for tests/local experimentation, not the documented Compose deployment.
