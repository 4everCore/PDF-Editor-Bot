# Known limitations and next work

## Current functional limits

- Telegram supports one uploaded file at a time. Merge plugin works only when source PDFs already share one user's private directory; there is no upload-collection UI. No batch workflow chaining or user-saved workflow execution is exposed.
- Only lossless PDF object/stream cleanup is implemented for compression; image downsampling, grayscale, linearization, margin removal and deskew are not implemented.
- PDF editing is overlay-oriented: watermark and rotation only. There is no original text replacement, redaction, annotation, signatures, metadata/bookmark editing or page-number/header tooling.
- OCR does not include a local OCR acceptance corpus. Language-pack availability varies. OCR quality for Persian/Arabic is unverified; automatic language detection is not implemented.
- LibreOffice conversion supports only DOCX/XLSX/PPTX from Telegram. It is best-effort and may alter layout. Upload validation inspects ZIP metadata without decompressing members; actual Office content/CRC validation occurs only during worker conversion. No PDF-to-Office or legacy DOC/XLS/PPT exports.
- Image-to-PDF currently handles a single image page. No photo crop/deskew workflow.
- AI provider adapter and lexical page retrieval exist, but bot Q&A is not wired, citations are prompted rather than programmatically verified, and there is no vector store or translation/summarization orchestration. Provider use may transmit document excerpts.
- Security reporting, attachment/JavaScript inspection, encryption/decryption, permissions, signature verification, fillable forms and repair are not implemented.
- No object storage, external download links, subscription plans, favorite editor, document history retrieval, status/progress UI or backup automation.
- `API_TOKEN` is reserved but currently unused; only health endpoints exist.

## Validation limits in this workspace

- Docker/Compose and system OCR/LibreOffice/Tesseract/qpdf binaries are unavailable. Therefore Docker build/up, PostgreSQL migrations, Redis worker integration, real Telegram traffic, office conversion and OCR languages were not exercised.
- No secret credentials or connected external service were provided. AI/Telegram full-flow tests are intentionally not fabricated.
- The initial Alembic revision is tested with SQLite dialect locally; run it against a clean PostgreSQL instance before deployment.
- Stress testing with large real-world files and concurrent users has not been performed.

These are transparent scope boundaries, not hidden green checks.
