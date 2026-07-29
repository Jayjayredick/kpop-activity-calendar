from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from .models import Artist, Source


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_artists(path: str | Path | None = None) -> list[Artist]:
    path = Path(path) if path else project_root() / "config" / "artists.json"
    return [Artist(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def load_sources(path: str | Path | None = None) -> list[Source]:
    path = Path(path) if path else project_root() / "config" / "sources.json"
    return [Source(**row) for row in json.loads(path.read_text(encoding="utf-8"))]


def assert_official_url(source: Source) -> None:
    host = (urlparse(source.url).hostname or "").lower()
    allowed = source.official_domain.lower().lstrip(".")
    if host != allowed and not host.endswith("." + allowed):
        raise ValueError(
            f"공식 도메인 불일치: {source.source_id}: {host} != {allowed}"
        )

