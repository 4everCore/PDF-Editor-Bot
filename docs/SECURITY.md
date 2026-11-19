# Security review and deployment checklist

## Implemented controls

- [x] Uploaded names are reduced to display-safe basenames; storage paths are opaque UUIDs under a per-user directory.
- [x] PDF parsing, page counting and encryption preflight run in a resource-limited child process, not in the Telegram handler process.
- [x] Uploads are accepted only in private chats; scratch files are created in a private app-owned directory and a periodic janitor removes aged upload/preflight scratch files without following symlinks.
- [x] Content signatures are checked; size and PDF page limits are enforced after download; PDF encryption is rejected.
- [x] OOXML packages are checked in the resource-limited child without extracting/decompressing members for required paths, symlinks/traversal, entry counts, declared expansion size, duplicate names and suspicious compression ratios.
- [x] Callbacks require both stored-file ID and Telegram owner ID. Original files are not overwritten.
- [x] Redis per-user fixed-window limiter; sensitive payloads/passwords are not logged. Redis outage currently fails open for the limiter (queueing still fails closed).
- [x] Worker operation names are allowlisted. No user-controlled shell is constructed; subprocesses use argument arrays and bounded timeouts.
- [x] Linux child process limits CPU time, virtual address space, open descriptors, per-file output size and core dumps; OCR parallelism is fixed to one process, and Compose limits worker container PIDs. Each child gets a private per-job HOME/TMPDIR, and parent/operation cleanup removes isolated scratch and converter/image work directories after completion, error, timeout or cancellation. Worker/API containers use a non-root UID, read-only root filesystem, dropped capabilities and `no-new-privileges` in Compose.
- [x] OCR/LibreOffice subprocess output is discarded; PDF scripts/attachments are never executed by this application.
- [x] Configurable upload/page/job limits, Telegram result-size cap, 24-hour default expiry and hourly metadata-driven cleanup.
- [x] API docs are disabled and only health endpoints are implemented; Compose binds host port to loopback by default.

## Required before public production

- [ ] Set strong unique `POSTGRES_PASSWORD` and matching URL in `.env`; protect `.env` and backups. Do not use sample values.
- [ ] Configure a private object store and storage lifecycle/backup policy before horizontally scaling workers.
- [ ] Put the health API behind an authenticated/private network or disable its published port if not needed.
- [ ] Establish egress controls for workers. LibreOffice/OCR children run in the worker container, which must reach Telegram/Redis; Compose cannot network-isolate only the converter child. Use a separate no-egress sandbox worker service/container if hostile-input isolation is a hard requirement.
- [ ] Add observability/error reporting that redacts user IDs where required and never records document text, tokens, or passwords.
- [ ] Review Telegram Bot API download/send limits for the deployment region and use a private expiring download-link service for larger results.
- [ ] Pin/audit base-image digests and rebuild on OS/Python security updates. Image build and runtime were not verified in this workspace because Docker is absent.
- [ ] Run a threat model and penetration review before processing confidential or regulated records.

## Known risks / accepted constraints

- Native PDF engines and LibreOffice process attacker-controlled files. A subprocess plus resource limits is defense-in-depth, not a kernel/container security boundary. The worker container still has network access for Telegram and Redis.
- Fixed-window rate limiting is best-effort during Redis failures and does not enforce a per-user concurrent-job quota across worker hosts. Arq has global worker backpressure; a distributed user concurrency lease is future work.
- The configured API token is not used because no private API endpoints exist; do not expose this health-only service publicly.
- Expiration job deletes file rows/files hourly; it is not a secure-erasure guarantee on SSDs, copy-on-write filesystems, backups or object stores.
- Local storage is single-host only; multiple replicas require a shared private storage adapter.
- AI calls, when explicitly integrated and configured, send retrieved document excerpts to the configured provider. The current Telegram bot does not expose AI Q&A.
