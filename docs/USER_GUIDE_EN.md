# English user guide

## Getting started

After deployment, send `/start` or `/menu`, then upload a PDF, DOCX/XLSX/PPTX, or JPEG/PNG/TIFF image. The bot checks file contents rather than trusting the extension or Telegram's declared MIME type. It displays only actions relevant to the detected file.

## Available operations

- PDFs: lossless object/stream optimization (no image downsampling), text extraction, first-page PNG preview, searchable OCR when language packs are installed, sample watermark overlay, and page rotation through the processing engine.
- Images: one uploaded image into a one-page PDF.
- Office: DOCX/XLSX/PPTX to PDF through LibreOffice. Complex layouts can change.
- Processing is queued. The result is sent as a new file; your original is not overwritten.

## Commands

`/start` and `/menu` show the menu, `/help` explains the workflow, `/settings` and `/language` switch Persian/English, `/history` lists recent jobs, `/cancel` requests abort of your newest active job, `/privacy` summarizes retention, and `/about` describes the service.

## Limits and privacy

Defaults: 20 MiB upload, 500 PDF pages, 100 OCR pages and 24-hour retention. Results larger than the configured Telegram delivery cap are not sent. Encrypted PDFs are rejected. Do not upload highly sensitive documents. OCR and conversion fidelity depend on document quality, fonts and installed system tools.

The Telegram UI does not currently expose multi-PDF merge, original-text editing, comparisons, cryptographic signatures, forms, batch workflows or AI Q&A. See `FEATURE_COVERAGE.md` and `LIMITATIONS.md` for the full verified scope.
