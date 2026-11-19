"""Stable interface for processing plugins."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Operation(ABC):
    """A PDF operation with uniform validation, execution, and reporting hooks."""

    name: str
    output_suffix: str = ".pdf"

    @abstractmethod
    def validate(self, source: Path, options: dict[str, Any]) -> None:
        """Validate input and operation options; raise a typed error on failure."""

    @abstractmethod
    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        """Execute synchronously in a worker and return safe operation metadata."""

    def get_metadata(self, source: Path, destination: Path | None = None) -> dict[str, Any]:
        return {
            "input_bytes": source.stat().st_size,
            "output_bytes": destination.stat().st_size
            if destination and destination.exists()
            else None,
        }

    def estimate_output(self, source: Path, options: dict[str, Any]) -> int:
        return source.stat().st_size

    def cleanup(self, paths: list[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)

    def cleanup_workspace(self, destination: Path) -> None:
        """Remove operation-specific scratch artifacts after success, failure or cancellation."""
        return None
