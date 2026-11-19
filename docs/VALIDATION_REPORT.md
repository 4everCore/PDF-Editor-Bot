# Deep QA report — 2026-11-13

## Executive decision

**Not production-ready.** A clean Python environment install succeeded and the local regression/static/security/dependency checks pass. The latest suite has **58 passing tests and 61% statement coverage**. However, Docker deployment, PostgreSQL, live Redis/Arq, Telegram, OCR system binaries/language quality, and LibreOffice are not available for end-to-end verification. Several requested product areas remain explicitly partial or unimplemented. The application must not be represented as fully integrated or production-ready until the release gates in `ISSUE_LOG.md` are closed.

## Initial project condition

The existing repository was a foundation with a deliberately limited user-facing feature set, not the complete PDF product catalogue. At the beginning of this QA pass, the prior local baseline was **42 passing tests with 43% statement coverage**; the project virtual environment was absent from the restored workspace, and no Git repository, `.env`, or database file was found. I installed the declared `.[test,ocr]` extras into a newly created Python 3.13 virtual environment before re-running checks.

## Repository discovery and architecture

- Inspected **73 project files** after excluding `.venv`, interpreter/test/lint caches, bytecode, and `.coverage`; this includes **53 Python files** across `app`, `tests`, `migrations`, and type stubs, plus deployment/configuration and documentation.
- Reviewed all Python modules, tests, migrations, guides, deployment files, and docs. No separate git repository or production data/configuration was present. No `.env` or database file was found.
- Architecture map: `docs/architecture.md`; feature boundaries: `docs/FEATURE_COVERAGE.md` and `docs/LIMITATIONS.md`; issue-by-issue evidence: `docs/ISSUE_LOG.md`.

### Request path

1. aiogram receives private-chat document/photo; handler checks advertised size, downloads to a random file in a private app-owned temp directory, and performs cheap signature/size checks.
2. PDF parsing/encryption/page checks and OOXML central-directory inspection/classification run in an isolated child with CPU, address-space, descriptor, file-size and core limits, a unique `HOME`/`TMPDIR`, and a parent-enforced timeout/process-group kill.
3. Validated content is placed under an owner-specific opaque storage key and metadata/expiry is stored in SQLAlchemy/PostgreSQL.
4. Owner-checked operation callback writes a queued job and enqueues the allowlisted Arq function through Redis.
5. Worker uses a bounded semaphore, runs the operation in an isolated child, validates generated output, sends the output as a new Telegram document, records job/result metadata, and cleans operation-specific scratch space. Expiry cleanup skips files referenced by queued/running/cancelling jobs.

## Issues found and disposition

The issue ledger contains **9 issues**: 6 reliability/security defects with local regression tests, and 3 deployment/resource/configuration hardening changes whose container behavior is not verified. The fixes cover deferred OOXML parsing into the constrained child, active-job file-expiry races, parallel LibreOffice output collisions, cancellation while waiting for a worker slot, watermark overflow falsely reporting success, subprocess CWD/scratch cleanup, duplicate OCRmyPDF installations, output-size/OCR/PID limits, and a known non-empty database password example.

No production data or external service was modified. See `docs/ISSUE_LOG.md` for severity, cause, reproduction, fix, and evidence per issue.

## Issue summary and disposition

`docs/ISSUE_LOG.md` records **9 code/configuration issues** (4 HIGH, 4 MEDIUM, 1 LOW) and **8 unresolved release gates** (5 HIGH). No locally reproducible CRITICAL issue remains. Fixes for BUG-001 through BUG-006 have passing regression tests. BUG-007 through BUG-009 have implementation/static/unit evidence where applicable, but Docker/Linux enforcement and real Compose startup are still unverified. These counts are an audit log, not a proof that unavailable integrations contain no defects.

## Files changed in this QA pass

Application/resource handling: `app/storage/files.py`, `app/bot/handlers/files.py`, `app/processors/pdf/basic.py`, `app/processors/pdf/registry.py`, `app/processors/pdf/external.py`, `app/processors/pdf/images.py`, `app/domain/operations.py`, `app/services/isolation.py`, `app/workers/run_operation.py`, `app/workers/worker.py`.

Deployment/configuration: `Dockerfile`, `docker-compose.yml`, `.env.example`.

Tests added or expanded: `tests/unit/test_bot_handlers.py` (new), `tests/unit/test_worker_control.py` (new), `tests/unit/test_bot_ui.py`, `tests/unit/test_optional_adapters.py`, `tests/unit/test_pdf_operations.py`, `tests/unit/test_storage.py`, `tests/integration/test_database.py`, `tests/integration/test_isolated_worker.py`.

Documentation: `docs/architecture.md`, `docs/SECURITY.md`, `docs/FEATURE_COVERAGE.md`, `docs/ISSUE_LOG.md`, and this report.

## Validation results

The Python environment was created from scratch using Python 3.13.18 and `pip install -e '.[test,ocr]'`; installation and editable wheel build succeeded. Python 3.12 is not installed in this workspace, even though the Dockerfile targets 3.12, so that exact runtime remains untested.

Latest local validation (after the last application-code change):

| Check | Reproduction command | Result |
|---|---|---|
| Ruff | `.venv/bin/ruff check . --fix && .venv/bin/ruff format . && .venv/bin/ruff check .` | Passed. |
| Tests/coverage | `.venv/bin/pytest -q --cov=app --cov-report=term-missing` | **58 passed**, **61% statement coverage**. |
| Mypy | `.venv/bin/mypy app --show-error-codes` | Passed; no issues in 37 source files. |
| Bandit | `.venv/bin/bandit -r app -q` | Passed; no findings reported. |
| pip-audit | `.venv/bin/pip-audit --skip-editable` | No known vulnerabilities reported; editable application distribution is skipped by this option. |
| Deptry | `.venv/bin/deptry .` | Passed. DEP002 exceptions are named individually in `pyproject.toml`; not globally ignored. |
| Dependency consistency | `.venv/bin/pip check` | Passed. |
| Syntax/bytecode | `.venv/bin/python -m compileall -q app tests migrations typings` | Passed. |
| Migration | Included in `pytest`: clean SQLite Alembic upgrade and downgrade. | Passed; PostgreSQL-specific behavior not established. |
| Handler-level flow | Included in `pytest`: simulated download → isolated PDF preflight → owner-private storage; spoofed upload rejection; callback ownership and enqueue behavior. | Passed without Telegram network access. |

The tested dependency resolution included aiogram 3.32.0, FastAPI 0.163.2, Pydantic 2.14.3, SQLAlchemy 2.1.9, Alembic 1.20.1, asyncpg 0.32.0, Redis 5.3.1, Arq 0.28.0, PyMuPDF 1.28.2, pypdf 6.21.4, Pillow 13.0.0, and OCRmyPDF 17.14.2. This is a successful install/test on Python 3.13.18, not proof of the unavailable system-level tools or Python 3.12 deployment image. `pdfplumber`, ReportLab, and Celery are neither declared nor imported: current PDF text/editing uses PyMuPDF/pypdf and background tasks use Arq, so adding unused alternatives would weaken dependency hygiene rather than validate compatibility. OCRmyPDF is an optional Python extra; its external Tesseract executable and language packs are separate system dependencies.

## Performance sample

Generated a synthetic 500-page PDF and concurrently ran four isolated text extractions; all returned 500-page metadata, produced readable-size outputs, and left no child scratch directories. Observed elapsed time: **0.71 seconds** in this workspace. This is a small synthetic smoke/performance sample only—not representative OCR, large-image, memory-peak, disk, production concurrency, or load evidence. No CPU/memory telemetry or production corpus was available.

## Feature coverage and known limitations

### Verified locally (tests assert actual outputs/behavior)

- PDF text extraction, lossless object/stream compression at low/balanced/high levels, page rotation, overlay watermark (including rejection when it cannot fit), PNG render, selected-page extraction, same-user merge plugin, and one-image-to-PDF conversion.
- Signature/size and malformed-PDF checks, PDF encryption/page checks in isolated subprocess, OOXML archive bounds/traversal handling in isolated preflight, owner-scoped storage and callbacks, child timeout/process-group cleanup, worker-slot cancellation status, SQLite schema/migration behavior, API liveness, and menu/button response maps.

### Implemented but not fully verified

- PostgreSQL deployment/migration/concurrency, Redis rate limiter and Arq production pipeline, real Telegram update/callback/network delivery, OCR and Persian/Arabic language quality, LibreOffice output fidelity, AI provider/live behavior, and all Docker/Compose startup/health/restart/security behavior.
- Several API, app lifecycle, job/worker and service branches have little or no direct test coverage. Total coverage is 61%; passing tests should not be read as broad production reliability evidence.

### Partial or not implemented

- Multi-file Telegram merge workflow, page-range selection UI, broad PDF editing/redaction/signatures/forms, PDF-to-Office and broad conversion directions, OCR acceptance/quality suite, AI Q&A Telegram workflow/citation validator, object storage, backups/restore automation, and load/recovery workflows. See `FEATURE_COVERAGE.md` and `LIMITATIONS.md`.

## Blockers and production gates

The following tools were absent from the host: Docker, Podman, PostgreSQL client/server, Redis server, Tesseract, LibreOffice, and OCRmyPDF system executable. The Python OCRmyPDF package installed, but cannot substitute for Tesseract and system conversion binaries. No Telegram token, PostgreSQL/Redis service, or AI credential was provided. Repeated attempts against these unavailable external dependencies were not made.

Required before production: clean Docker build/start/restart, PostgreSQL migration and backup/restore/concurrency testing, live Redis/Arq retries/abort/recovery/backpressure, Telegram end-to-end journeys, representative OCR and Office conversion content tests, controlled load/resource tests, review of worker egress/hostile native document parsing, and product-owner acceptance of reduced scope.

## Three-cycle acceptance status

**Three consecutive complete local validation cycles passed after the final application-code/configuration change.** Each cycle independently ran format check, Ruff lint, the full coverage suite, mypy, Bandit, pip-audit, deptry, pip check, and compileall. Each had 58 passing tests and 61% statement coverage; all static/dependency/security checks passed. Cycle durations were approximately 6 seconds for pytest and 29 seconds total for all three cycles. Docker/PostgreSQL/Redis/Telegram/OCR/LibreOffice validation remains blocked and is not counted as passing.

## Reproducible commands

```bash
cd /home/user/pdf_telegram_bot
python3 -m venv .venv
.venv/bin/pip install -e '.[test,ocr]'
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest -q --cov=app --cov-report=term-missing
.venv/bin/mypy app --show-error-codes
.venv/bin/bandit -r app -q
.venv/bin/pip-audit --skip-editable
.venv/bin/deptry .
.venv/bin/pip check
.venv/bin/python -m compileall -q app tests migrations typings
```

Do not promote to production until integration gates are passed in a representative staging deployment, and do not describe unimplemented features as working.
