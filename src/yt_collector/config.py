from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    youtube_api_key: str | None = None
    api_base_url: str = "https://www.googleapis.com/youtube/v3"
    timeout_seconds: float = 20.0


def load_settings(env_file: str | Path = ".env") -> Settings:
    values = _read_env_file(Path(env_file))
    return Settings(
        youtube_api_key=os.getenv("YOUTUBE_API_KEY") or values.get("YOUTUBE_API_KEY") or None,
        api_base_url=os.getenv("YOUTUBE_API_BASE_URL") or values.get("YOUTUBE_API_BASE_URL") or Settings().api_base_url,
        timeout_seconds=float(os.getenv("YOUTUBE_API_TIMEOUT_SECONDS") or values.get("YOUTUBE_API_TIMEOUT_SECONDS") or 20.0),
    )


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values
