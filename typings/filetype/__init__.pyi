"""Minimal local typing contract for filetype's public signature guesser."""

from typing import Protocol

class Type(Protocol):
    mime: str
    extension: str

def guess(filename: str) -> Type | None: ...
