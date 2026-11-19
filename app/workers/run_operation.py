"""One-operation subprocess with POSIX resource limits; invoke only with server-generated paths."""

import json
import os
import sys
from pathlib import Path


def _verify_output(path: Path) -> None:
    """Reopen every generated artifact before the worker publishes it."""
    if path.suffix.lower() == ".pdf":
        import pymupdf

        with pymupdf.open(path) as document:
            if document.is_encrypted or document.page_count < 1:
                raise RuntimeError("invalid generated PDF")
    elif path.suffix.lower() == ".png":
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    elif path.suffix.lower() == ".txt":
        path.read_text(encoding="utf-8")
    else:
        raise RuntimeError("unexpected output type")



def main() -> int:
    if os.name == "posix":
        import resource

        setrlimit_name = "setrlimit"
        setrlimit = getattr(resource, setrlimit_name)

        limit_names = (
            ("RLIMIT_CPU", 300),
            ("RLIMIT_AS", 1536 * 1024 * 1024),
            ("RLIMIT_NOFILE", 128),
            ("RLIMIT_FSIZE", 49 * 1024 * 1024),
            ("RLIMIT_CORE", 0),
        )

        for limit_name, value in limit_names:
            limit = getattr(resource, limit_name)
            setrlimit(limit, (value, value))

    os.umask(0o077)
    operation_name, source_text, destination_text, options_text, metadata_text = sys.argv[1:]
    source, destination, metadata_path = (
        Path(source_text),
        Path(destination_text),
        Path(metadata_text),
    )

    from app.core.exceptions import AppError
    from app.processors.pdf.registry import get_operation

    try:
        options = json.loads(options_text)
        if not isinstance(options, dict):
            raise ValueError("options must be an object")
        plugin = get_operation(operation_name)
        plugin.validate(source, options)
        metadata = plugin.execute(source, destination, options)

        if not destination.is_file() or destination.stat().st_size == 0:
            raise RuntimeError("processor produced no output")
        if destination.stat().st_size > 49 * 1024 * 1024:
            raise RuntimeError("processor output exceeds the delivery limit")

        _verify_output(destination)
        payload = {"ok": True, "metadata": metadata}
        code = 0

    except AppError as exc:
        payload = {"ok": False, "code": exc.code, "message": exc.message}
        code = 2

    except Exception:
        payload = {
            "ok": False,
            "code": "processing_failed",
            "message": "The document could not be processed.",
        }
        code = 3

    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(metadata_path)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
