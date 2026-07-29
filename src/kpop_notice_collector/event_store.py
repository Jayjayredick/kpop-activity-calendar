from __future__ import annotations

import csv
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Notice


EVENT_FIELDS = [
    "event_key",
    "company",
    "label",
    "artist_id",
    "artist",
    "activity_type",
    "event_name",
    "event_dates",
    "cities",
    "venues",
    "first_seen",
    "last_seen",
    "status",
    "primary_url",
    "source_type",
    "official_verified",
    "score",
    "supporting_article_count",
    "related_urls",
]


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def corroborate(news: list[Notice], official: list[Notice]) -> None:
    for article in news:
        for notice in official:
            if article.artist_id != notice.artist_id:
                continue
            type_match = article.activity_type == notice.activity_type
            date_match = bool(set(article.event_dates) & set(notice.event_dates))
            name_match = _similar(article.event_name, notice.event_name) >= 0.48
            if type_match and (date_match or name_match):
                article.official_verified = True
                article.score += 25
                article.previous_event_keys.append(notice.event_key)
                break


def upsert_event_history(
    path: str | Path, notices: list[Notice], *, now: datetime | None = None
) -> list[dict]:
    path = Path(path)
    now = now or datetime.now(ZoneInfo("Asia/Seoul"))
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            existing = {row["event_key"]: row for row in csv.DictReader(f)}

    for notice in notices:
        current = existing.get(notice.event_key, {})
        current_official = current.get("official_verified") == "Y"
        if current and current_official and not notice.official_verified:
            current["last_seen"] = now.isoformat()
            current["score"] = str(
                max(int(current.get("score") or 0), notice.score)
            )
            existing[notice.event_key] = current
            continue
        existing[notice.event_key] = {
            "event_key": notice.event_key,
            "company": notice.company,
            "label": notice.label,
            "artist_id": notice.artist_id,
            "artist": notice.artist,
            "activity_type": notice.activity_type,
            "event_name": notice.event_name or notice.title,
            "event_dates": "|".join(notice.event_dates),
            "cities": "|".join(notice.cities),
            "venues": "|".join(notice.venues),
            "first_seen": current.get("first_seen") or now.isoformat(),
            "last_seen": now.isoformat(),
            "status": notice.schedule_status,
            "primary_url": notice.url,
            "source_type": notice.source_type,
            "official_verified": "N/A",
            "score": str(notice.score),
            "supporting_article_count": str(notice.supporting_article_count),
            "related_urls": "|".join(notice.related_urls),
        }
    rows = sorted(
        existing.values(),
        key=lambda row: (
            row.get("event_dates") or "9999-99-99",
            row.get("company", ""),
            row.get("artist", ""),
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def append_daily_rows(path: str | Path, notices: list[Notice]) -> None:
    from .pipeline import notice_to_row

    path = Path(path)
    rows = [notice_to_row(n) for n in notices]
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
