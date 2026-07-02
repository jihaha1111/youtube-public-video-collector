from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CollectorError(Exception):
    """Base exception for collector failures."""


class UrlParseError(ValueError):
    """Raised when a YouTube video URL cannot be parsed."""


@dataclass(slots=True)
class YouTubeApiError(CollectorError):
    """Structured error raised for YouTube Data API failures."""

    code: str
    message: str
    status_code: int | None = None
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        prefix = f"HTTP {self.status_code}: " if self.status_code is not None else ""
        return f"{prefix}{self.code}: {self.message}"

    def as_problem(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details,
        }
