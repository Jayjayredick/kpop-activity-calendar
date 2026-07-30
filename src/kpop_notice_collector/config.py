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


def load_activity_entities(path: str | Path | None = None) -> list[Artist]:
    """그룹 멤버 솔로·유닛을 부모 59팀과 별도 검색 대상으로 불러온다."""
    path = (
        Path(path)
        if path
        else project_root() / "config" / "activity_entities.json"
    )
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        Artist(
            artist_id=row["artist_id"],
            company=row["company"],
            label=row["label"],
            name=row["name"],
            aliases=row.get("aliases", []),
            official_url=row.get("official_url", ""),
            source_ids=row.get("source_ids", []),
        )
        for row in rows
        if row.get("enabled", True)
    ]


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
