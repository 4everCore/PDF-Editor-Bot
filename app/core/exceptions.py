"""Typed application errors safe to surface to users."""


class AppError(Exception):
    """Base error with user-safe message."""

    def __init__(self, message: str, *, code: str = "processing_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ValidationError(AppError):
    """Invalid or unsupported input document."""


class ProcessingError(AppError):
    """A document operation could not complete."""


class ResourceLimitError(AppError):
    """Input exceeds configured resource limits."""
