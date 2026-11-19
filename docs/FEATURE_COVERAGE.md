# Feature coverage (verified scope, not roadmap promises)

Legend: **Working** = implementation and automated output assertions exist; **Partial** = code exists but not fully integrated or external requirements prevent verification; **Not implemented** = no user-facing working implementation.

| Area | Status | Evidence / limits |
|---|---|---|
| Telegram commands: start/help/menu/settings/language/history/privacy/about/cancel | Partial | Handler code and keyboard tests; no real Telegram token/network E2E. Cancel uses Arq abort. |
| Persian/English menus | Working | Both reply keyboards and language switch UI; translations are concise, not full localization. |
| Upload validation | Working | Signature/size checks, isolated PDF parse/encryption/page preflight, and isolated bounded OOXML central-directory inspection; automated handler tests cover download-to-storage flow, ownership, spoofed input and traversal. Real Telegram network flow remains untested. |
| PDF text extraction | Working | PyMuPDF output contains expected fixture text; async isolated worker tested. Scanned PDFs need OCR first. |
| PDF lossless compression | Working | Output opens and retains extracted content; does not downsample images. May increase size; reports source/result sizes. |
| Rotate pages | Working | Rotation metadata and content validated in tests. |
| Watermark overlay | Working | Overlay is explicitly reported; underlying text is retained and not falsely described as edited. |
| Render page preview | Working | PNG generated and verified with Pillow. UI sends it as an image-format document, not inline photo. |
| Extract selected pages | Working | pypdf output opens and contains expected page text; page range parser/UI not exposed. |
| Merge | Partial | Plugin validates 2–10 PDFs in the same private user directory and merges; Telegram multi-file selection flow is not wired. |
| Image to PDF | Partial | One JPEG/PNG/TIFF to one-page PDF is implemented. Pixel-limit and multi-image workflows need more coverage. |
| DOCX/XLSX/PPTX to PDF | Partial | LibreOffice adapter and OOXML validation are implemented; not verified here because LibreOffice/Docker are unavailable. |
| OCR to searchable PDF | Partial | OCRmyPDF adapter with language option and 100-page limit; Tesseract binary/language packs and OCR samples unavailable locally; no Persian/Arabic quality verification. |
| AI retrieval | Partial | Provider interface, excerpt retrieval, page-number prompts and explicit no-hit handling exist; no bot question flow, answer-citation validator or live provider test. Not exposed in Telegram. |
| PostgreSQL schema | Partial | Models and initial Alembic revision; SQLite `create_all` is tested. PostgreSQL migrations/concurrency/backups not run (no service). |
| Redis rate limiting/Arq jobs | Partial | Enqueue/worker code exists; real Redis task/retry/restart/backpressure integration is not run. |
| FastAPI health | Partial | Live/ready routes; real service checks need PostgreSQL/Redis. No document API. |
| Storage privacy | Partial | Local per-user paths; no S3/MinIO adapter, distributed storage, backup/restore test or secure erase. |
| PDF editing, OCR intelligence, security scan, digital signing, forms, conversion catalogue, comparison, batch/presets | Not implemented | No UI buttons claim these features. See `docs/LIMITATIONS.md`. |
| Docker deployment | Not verified | Docker/Compose binaries are absent in the execution environment; files are supplied but image build/health/startup must be run by deployer. |

The current test suite validates actual file contents and openability for implemented PDF operations; it does not prove visual fidelity for every font/language or production service reliability.
