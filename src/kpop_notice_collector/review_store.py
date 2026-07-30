from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .models import Notice


REVIEW_FIELDS = [
    "candidate_id",
    "event_key",
    "company",
    "label",
    "artist_id",
    "artist",
    "activity_type",
    "event_name",
    "event_start_date",
    "event_end_date",
    "event_dates",
    "cities",
    "venues",
    "article_title",
    "published_at",
    "score",
    "review_reason",
    "primary_url",
    "naver_url",
    "related_urls",
    "supporting_article_count",
    "clipped_text",
    "first_seen",
    "last_seen",
    "review_status",
]

REVIEW_LOG_FIELDS = [
    "reviewed_at",
    "action",
    "candidate_id",
    "event_key",
    "artist",
    "activity_type",
    "event_name",
    "note",
]


def _read_rows(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: str | Path, rows: list[dict], fields: list[str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def notice_to_review_row(notice: Notice, now: datetime) -> dict:
    return {
        "candidate_id": notice.candidate_id,
        "event_key": notice.event_key,
        "company": notice.company,
        "label": notice.label,
        "artist_id": notice.artist_id,
        "artist": notice.artist,
        "activity_type": notice.activity_type,
        "event_name": notice.event_name or notice.title,
        "event_start_date": notice.event_start_date,
        "event_end_date": notice.event_end_date,
        "event_dates": "|".join(notice.event_dates),
        "cities": "|".join(notice.cities),
        "venues": "|".join(notice.venues),
        "article_title": notice.title,
        "published_at": (
            notice.published_at.isoformat() if notice.published_at else ""
        ),
        "score": str(notice.score),
        "review_reason": notice.review_reason or "MANUAL_REVIEW",
        "primary_url": notice.url,
        "naver_url": notice.naver_url,
        "related_urls": "|".join(notice.related_urls),
        "supporting_article_count": str(notice.supporting_article_count),
        "clipped_text": notice.clipped_text,
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "review_status": "PENDING",
    }


def load_review_queue(path: str | Path) -> list[dict]:
    return _read_rows(path)


def upsert_review_queue(
    path: str | Path,
    notices: list[Notice],
    *,
    now: datetime,
    review_log_path: str | Path | None = None,
) -> list[dict]:
    existing_rows = _read_rows(path)
    rejected_event_keys = {
        row.get("event_key", "")
        for row in (_read_rows(review_log_path) if review_log_path else [])
        if row.get("action") == "REJECT"
    }
    by_candidate = {
        row.get("candidate_id", ""): row
        for row in existing_rows
        if row.get("candidate_id")
    }
    by_event = {
        row.get("event_key", ""): row
        for row in existing_rows
        if row.get("event_key")
    }

    for notice in notices:
        if notice.event_key in rejected_event_keys:
            continue
        new_row = notice_to_review_row(notice, now)
        current = (
            by_candidate.get(new_row["candidate_id"])
            or by_event.get(new_row["event_key"])
            or {}
        )
        if current:
            new_row["candidate_id"] = current.get("candidate_id") or new_row["candidate_id"]
            new_row["first_seen"] = current.get("first_seen") or new_row["first_seen"]
        by_candidate[new_row["candidate_id"]] = new_row
        by_event[new_row["event_key"]] = new_row

    rows = sorted(
        by_candidate.values(),
        key=lambda row: (
            row.get("event_start_date") or "9999-99-99",
            row.get("company", ""),
            row.get("artist", ""),
            row.get("event_name", ""),
        ),
    )
    _write_rows(path, rows, REVIEW_FIELDS)
    return rows


def write_review_queue(path: str | Path, rows: list[dict]) -> Path:
    return _write_rows(path, rows, REVIEW_FIELDS)


def append_review_log(path: str | Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=REVIEW_LOG_FIELDS,
            extrasaction="ignore",
        )
        if not exists:
            writer.writeheader()
        writer.writerows(rows)

