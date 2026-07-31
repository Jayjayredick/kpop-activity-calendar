from __future__ import annotations

import csv
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Notice
from .safety import restore_spreadsheet_row, safe_row_for_spreadsheet


EVENT_FIELDS = [
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
    "date_confidence",
    "date_evidence",
    "date_source",
    "date_conflict",
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
    "approval_status",
    "article_title",
    "reviewed_at",
    "review_source",
]


def load_event_rows(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        # v3.0 날짜 병합 결과는 v3.1 신뢰도 필드가 없어 안전하게 폐기한다.
        if "date_confidence" not in (reader.fieldnames or []):
            return []
        return [restore_spreadsheet_row(row) for row in reader]


def write_event_rows(path: str | Path, rows: list[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(
        rows,
        key=lambda row: (
            row.get("event_start_date")
            or row.get("event_dates")
            or "9999-99-99",
            row.get("company", ""),
            row.get("artist", ""),
        ),
    )
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=EVENT_FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(safe_row_for_spreadsheet(row) for row in rows)
    return path


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower(), (b or "").lower()).ratio()


def _matching_history_key(existing: dict[str, dict], notice: Notice) -> str:
    if notice.event_key in existing:
        return notice.event_key
    for key, row in existing.items():
        if row.get("artist_id") != notice.artist_id:
            continue
        if row.get("activity_type") != notice.activity_type:
            continue
        row_start = row.get("event_start_date") or (
            (row.get("event_dates") or "").split("|")[0]
        )
        same_start = bool(
            row_start
            and notice.event_start_date
            and row_start == notice.event_start_date
        )
        name_similarity = _similar(
            row.get("event_name", ""),
            notice.event_name or notice.title,
        )
        if (same_start and name_similarity >= 0.25) or name_similarity >= 0.72:
            return key
    return notice.event_key


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
    existing = {
        row["event_key"]: row
        for row in load_event_rows(path)
        if row.get("event_key")
    }

    for notice in notices:
        history_key = _matching_history_key(existing, notice)
        current = existing.get(history_key, {})
        if current.get("approval_status") == "MANUAL_CONFIRMED":
            current["last_seen"] = now.isoformat()
            current["score"] = str(
                max(int(current.get("score") or 0), notice.score)
            )
            existing[history_key] = current
            continue
        current_official = current.get("official_verified") == "Y"
        if current and current_official and not notice.official_verified:
            current["last_seen"] = now.isoformat()
            current["score"] = str(
                max(int(current.get("score") or 0), notice.score)
            )
            existing[history_key] = current
            continue
        all_urls = []
        for value in [
            current.get("primary_url", ""),
            *(current.get("related_urls", "") or "").split("|"),
            notice.url,
            *notice.related_urls,
        ]:
            if value and value not in all_urls:
                all_urls.append(value)
        primary_url = current.get("primary_url") or notice.url
        related_urls = [value for value in all_urls if value != primary_url]
        existing[history_key] = {
            "event_key": history_key,
            "company": notice.company,
            "label": notice.label,
            "artist_id": notice.artist_id,
            "artist": notice.artist,
            "activity_type": notice.activity_type,
            "event_name": notice.event_name or notice.title,
            "event_start_date": notice.event_start_date,
            "event_end_date": notice.event_end_date,
            "event_dates": "|".join(notice.event_dates),
            "date_confidence": notice.date_confidence,
            "date_evidence": notice.date_evidence,
            "date_source": notice.date_source,
            "date_conflict": "Y" if notice.date_conflict else "N",
            "cities": "|".join(notice.cities),
            "venues": "|".join(notice.venues),
            "first_seen": current.get("first_seen") or now.isoformat(),
            "last_seen": now.isoformat(),
            "status": notice.schedule_status,
            "primary_url": primary_url,
            "source_type": notice.source_type,
            "official_verified": "N/A",
            "score": str(notice.score),
            "supporting_article_count": str(max(1, len(all_urls))),
            "related_urls": "|".join(related_urls),
            "approval_status": current.get("approval_status") or "AUTO_CONFIRMED",
            "article_title": notice.title,
            "reviewed_at": current.get("reviewed_at", ""),
            "review_source": current.get("review_source", ""),
        }
    rows = sorted(
        existing.values(),
        key=lambda row: (
            row.get("event_start_date")
            or row.get("event_dates")
            or "9999-99-99",
            row.get("company", ""),
            row.get("artist", ""),
        ),
    )
    write_event_rows(path, rows)
    return rows


def append_daily_rows(path: str | Path, notices: list[Notice]) -> None:
    from .pipeline import notice_to_row

    path = Path(path)
    rows = [notice_to_row(n) for n in notices]
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    if exists:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            old_fields = csv.DictReader(handle).fieldnames or []
        if old_fields != list(rows[0]):
            # 스키마가 달라진 v3.0 일일 이력은 새 헤더로 초기화한다.
            exists = False
    with path.open("a" if exists else "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(safe_row_for_spreadsheet(row) for row in rows)
